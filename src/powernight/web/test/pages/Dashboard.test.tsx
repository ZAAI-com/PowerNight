import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import { StrictMode } from 'react';
import Dashboard from '../../src/pages/Dashboard';
import api from '../../src/utils/api';


vi.mock('../../src/utils/api', () => ({
  default: {
    authenticatedFetch: vi.fn(),
  },
}));


describe('Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    vi.mocked(api.authenticatedFetch).mockResolvedValue({
      json: vi.fn().mockResolvedValue({
        success: true,
        data: { site_name: 'Home' },
      }),
    } as unknown as Response);
  });

  it('loads site details through the authenticated request helper', async () => {
    const { unmount } = render(<Dashboard />);

    await waitFor(() => {
      expect(api.authenticatedFetch).toHaveBeenCalledWith('/api/auth/site-details');
    });

    unmount();
  });

  it('shows Tesla setup instructions and preserves cached site data', async () => {
    localStorage.setItem('powernight_site_details', JSON.stringify({ site_name: 'Cached Home' }));
    vi.mocked(api.authenticatedFetch).mockResolvedValue(new Response(JSON.stringify({
      success: false,
      error: 'No valid authentication token available',
      code: 'TESLA_AUTH_REQUIRED',
      message: 'Connect or reconnect your Tesla account in Settings.',
    }), { status: 503 }));

    render(<Dashboard />);

    expect(await screen.findByText('Connect or reconnect your Tesla account in Settings.')).toBeVisible();
    expect(screen.getByText('Cached Home')).toBeVisible();
    expect(JSON.parse(localStorage.getItem('powernight_site_details')!)).toEqual({ site_name: 'Cached Home' });
    expect(screen.getByRole('button', { name: 'Update Data' })).toBeEnabled();
  });
  it('finishes the initial request under StrictMode', async () => {
    let finish!: (response: Response) => void;
    vi.mocked(api.authenticatedFetch).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    render(<StrictMode><Dashboard /></StrictMode>);
    await act(async () => {
      finish(new Response(JSON.stringify({ success: true, data: { site_name: 'Strict Home' } })));
    });
    expect(await screen.findByText('Strict Home')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Update Data' })).toBeEnabled();
    expect(api.authenticatedFetch).toHaveBeenCalledTimes(1);
  });

  it('keeps the existing error visible until a retry succeeds', async () => {
    vi.mocked(api.authenticatedFetch).mockResolvedValueOnce(new Response(JSON.stringify({
      success: false, message: 'Cloud unavailable',
    })));
    render(<Dashboard />);
    await screen.findByText('Cloud unavailable');
    let finish!: (response: Response) => void;
    vi.mocked(api.authenticatedFetch).mockReturnValueOnce(new Promise(resolve => { finish = resolve; }));
    fireEvent.click(screen.getByRole('button', { name: 'Update Data' }));
    expect(screen.getByText('Cloud unavailable')).toBeVisible();
    await act(async () => {
      finish(new Response(JSON.stringify({ success: true, data: { site_name: 'Home' } })));
    });
    expect(screen.queryByText('Cloud unavailable')).not.toBeInTheDocument();
  });

  it('refreshes every 20 seconds without exposing an interval dropdown', async () => {
    vi.useFakeTimers();
    const { unmount } = render(<Dashboard />);
    try {
      await act(async () => { await vi.advanceTimersByTimeAsync(0); });
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
      expect(api.authenticatedFetch).toHaveBeenCalledTimes(1);
      await act(async () => { await vi.advanceTimersByTimeAsync(19999); });
      expect(api.authenticatedFetch).toHaveBeenCalledTimes(1);
      await act(async () => { await vi.advanceTimersByTimeAsync(1); });
      expect(api.authenticatedFetch).toHaveBeenCalledTimes(2);
    } finally {
      unmount();
      vi.useRealTimers();
    }
  });

});

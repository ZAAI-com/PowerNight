import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
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
});

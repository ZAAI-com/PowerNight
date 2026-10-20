import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { vi } from 'vitest';
import Settings from '../../src/pages/Settings';
import api from '../../src/utils/api';


vi.mock('../../src/contexts/TimezoneContext', () => ({
  useTimezone: () => ({
    timezoneInfo: { timezone: 'UTC' },
    currentTime: '2026-07-14 12:00:00 UTC',
    isLoading: false,
    refreshTimezone: vi.fn(),
  }),
}));

vi.mock('../../src/contexts/ToastContext', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

vi.mock('../../src/utils/api', () => ({
  default: {
    authenticatedFetch: vi.fn(),
    getAvailableTimezones: vi.fn(),
    getTimezone: vi.fn(),
    updateTimezone: vi.fn(),
    reloadAllTasks: vi.fn(),
  },
}));

const authenticatedFetch = vi.mocked(api.authenticatedFetch);

describe('Settings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    authenticatedFetch.mockImplementation(async (input) => {
      const url = input.toString();
      if (url.endsWith('/api/auth/tesla/info')) {
        return {
          ok: true,
          json: async () => ({ success: true, data: { authenticated: false } }),
        } as Response;
      }
      return {
        ok: true,
        json: async () => ({
          application: 'PowerNight',
          version: '2.0.0',
          backend_dependencies: {},
          frontend_dependencies: {},
        }),
      } as Response;
    });
    vi.mocked(api.getTimezone).mockResolvedValue({
      timezone: 'UTC',
      offset: '+00:00',
      name: 'UTC',
      current_time: null,
    });
    vi.mocked(api.getAvailableTimezones).mockResolvedValue({ timezones: [], count: 0 });
  });

  it('loads protected settings data through the authenticated request helper', async () => {
    render(<Settings />);

    await waitFor(() => {
      expect(authenticatedFetch).toHaveBeenCalledWith('/api/auth/tesla/info');
      expect(authenticatedFetch).toHaveBeenCalledWith('/api/v1/version-info.json');
    });
  });

  it('renders the no-credentials state', async () => {
    render(<Settings />);

    expect(await screen.findByLabelText('Tesla Account Email')).toBeInTheDocument();
    expect(screen.queryByText('✅ Tesla cloud connected')).not.toBeInTheDocument();
  });

  it.each([
    {
      name: 'valid token with disconnected cloud',
      data: { authenticated: true, email: 'owner@example.com', token_expired: false, connected: false, connection_status: 'disconnected', connection_error: 'Tesla cloud is unreachable.' },
      expected: ['Valid', 'Disconnected', 'Tesla cloud is unreachable.'],
    },
    {
      name: 'expired token',
      data: { authenticated: true, email: 'owner@example.com', token_expired: true, connected: false, connection_status: 'unknown' },
      expected: ['Expired', 'Unknown'],
    },
    {
      name: 'connected cloud',
      data: { authenticated: true, email: 'owner@example.com', token_expired: false, connected: true, connection_status: 'connected' },
      expected: ['Valid', 'Connected', '✅ Tesla cloud connected'],
    },
  ])('renders $name separately from token state', async ({ data, expected }) => {
    authenticatedFetch.mockImplementation(async (input) => {
      const url = input.toString();
      return {
        ok: true,
        json: async () => url.endsWith('/api/auth/tesla/info')
          ? { success: true, data }
          : { application: 'PowerNight', version: '2.0.0', backend_dependencies: {}, frontend_dependencies: {} },
      } as Response;
    });

    render(<Settings />);

    for (const label of expected) {
      if (label === 'Unknown') {
        const heading = await screen.findByText('Live Connection');
        expect(heading.parentElement).toHaveTextContent('Unknown');
      } else {
        expect((await screen.findAllByText(label)).length).toBeGreaterThan(0);
      }
    }
  });

  it.each([
    {
      name: 'success',
      result: { success: true, data: { connected: true, connection_status: 'connected', connection_error: null } },
      expected: 'Connected',
    },
    {
      name: 'failure',
      result: { success: false, error: 'Tesla cloud is unreachable.', data: { connected: false, connection_status: 'disconnected', connection_error: 'Tesla cloud is unreachable.' } },
      expected: 'Tesla cloud is unreachable.',
    },
  ])('reports retry $name', async ({ result, expected }) => {
    authenticatedFetch.mockImplementation(async (input) => {
      const url = input.toString();
      if (url.endsWith('/api/auth/tesla/info')) {
        return { ok: true, json: async () => ({ success: true, data: {
          authenticated: true,
          email: 'owner@example.com',
          token_expired: false,
          connected: false,
          connection_status: 'disconnected',
        } }) } as Response;
      }
      if (url.endsWith('/api/auth/tesla/test-connection')) {
        return { ok: result.success, json: async () => result } as Response;
      }
      return { ok: true, json: async () => ({ application: 'PowerNight', version: '2.0.0', backend_dependencies: {}, frontend_dependencies: {} }) } as Response;
    });

    render(<Settings />);
    fireEvent.click(await screen.findByRole('button', { name: 'Retry Connection' }));

    expect((await screen.findAllByText(expected)).length).toBeGreaterThan(0);
    expect(authenticatedFetch).toHaveBeenCalledWith('/api/auth/tesla/test-connection', { method: 'POST' });
  });

  it('signs out of Tesla after confirmation and returns to the sign-in form', async () => {
    let signedIn = true;
    authenticatedFetch.mockImplementation(async (input) => {
      const url = input.toString();
      if (url.endsWith('/api/auth/tesla/info')) {
        return { ok: true, json: async () => ({ success: true, data: signedIn
          ? { authenticated: true, email: 'owner@example.com', token_expired: false, connected: false, connection_status: 'disconnected' }
          : { authenticated: false } }) } as Response;
      }
      if (url.endsWith('/api/auth/tesla/logout')) {
        signedIn = false;
        return { ok: true, json: async () => ({ success: true }) } as Response;
      }
      return { ok: true, json: async () => ({ application: 'PowerNight', version: '2.0.0', backend_dependencies: {}, frontend_dependencies: {} }) } as Response;
    });

    render(<Settings />);
    fireEvent.click(await screen.findByRole('button', { name: 'Sign Out of Tesla' }));
    expect(authenticatedFetch).not.toHaveBeenCalledWith('/api/auth/tesla/logout', { method: 'POST' });

    fireEvent.click(screen.getByRole('button', { name: 'Confirm Sign Out' }));

    expect(await screen.findByLabelText('Tesla Account Email')).toBeInTheDocument();
    expect(authenticatedFetch).toHaveBeenCalledWith('/api/auth/tesla/logout', { method: 'POST' });
  });

  it('signs in with tokens from pypowerwall and completes setup with the first site', async () => {
    authenticatedFetch.mockImplementation(async (input) => {
      const url = input.toString();
      if (url.endsWith('/api/auth/tesla/info')) {
        return { ok: true, json: async () => ({ success: true, data: { authenticated: false } }) } as Response;
      }
      if (url.endsWith('/api/auth/setup/tokens')) {
        return { ok: true, json: async () => ({ success: true, session_id: 'session-9', sites: [{ id: '42', name: 'Home', type: 'battery', state: 'online' }] }) } as Response;
      }
      if (url.endsWith('/api/auth/setup/complete')) {
        return { ok: true, json: async () => ({ success: true }) } as Response;
      }
      return { ok: true, json: async () => ({ application: 'PowerNight', version: '2.0.0', backend_dependencies: {}, frontend_dependencies: {} }) } as Response;
    });

    render(<Settings />);
    fireEvent.change(await screen.findByLabelText('Tesla Account Email'), { target: { value: 'owner@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Or sign in with tokens from pypowerwall' }));
    fireEvent.change(screen.getByLabelText('Refresh Token'), { target: { value: ' rt ' } });
    fireEvent.change(screen.getByLabelText('Access Token'), { target: { value: 'at' } });
    fireEvent.click(screen.getByRole('button', { name: 'Save Tokens' }));

    await waitFor(() => {
      expect(authenticatedFetch).toHaveBeenCalledWith('/api/auth/setup/complete', expect.objectContaining({
        body: JSON.stringify({ session_id: 'session-9', site_id: '42' }),
      }));
    });
    expect(authenticatedFetch).toHaveBeenCalledWith('/api/auth/setup/tokens', expect.objectContaining({
      body: JSON.stringify({ email: 'owner@example.com', refresh_token: 'rt', access_token: 'at' }),
    }));
  });
});

import React from 'react';
import { render, waitFor } from '@testing-library/react';
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
    vi.mocked(api.getAvailableTimezones).mockResolvedValue({ timezones: [] });
  });

  it('loads protected settings data through the authenticated request helper', async () => {
    render(<Settings />);

    await waitFor(() => {
      expect(authenticatedFetch).toHaveBeenCalledWith('/api/auth/tesla/info');
      expect(authenticatedFetch).toHaveBeenCalledWith('/api/v1/version-info.json');
    });
  });
});

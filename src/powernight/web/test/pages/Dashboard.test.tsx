import React from 'react';
import { render, waitFor } from '@testing-library/react';
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
});

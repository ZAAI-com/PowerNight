import { vi, type Mocked } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useAuth } from '../../src/hooks/useAuth';
import { api } from '../../src/utils/api';

// Mock the API
vi.mock('../../src/utils/api', () => ({
  api: {
    isAuthenticated: vi.fn(),
    authenticate: vi.fn(),
    logout: vi.fn(),
    checkAuthRequired: vi.fn(),
  },
}));

const mockApi = api as Mocked<typeof api>;

describe('useAuth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApi.isAuthenticated.mockReturnValue(false);
    // Default: auth is required and no API key present -> unauthenticated.
    mockApi.checkAuthRequired.mockResolvedValue(true);
  });

  it('should initialize to unauthenticated when auth is required and no key is set', async () => {
    const { result } = renderHook(() => useAuth());

    // The mount effect resolves checkAuthRequired asynchronously; wait for it.
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.error).toBe('Authentication required');
  });

  it('should handle successful login', async () => {
    mockApi.authenticate.mockResolvedValue(true);
    mockApi.isAuthenticated.mockReturnValue(true);

    const { result } = renderHook(() => useAuth());

    await act(async () => {
      const success = await result.current.login('test-api-key');
      expect(success).toBe(true);
    });

    expect(result.current.isAuthenticated).toBe(true);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeUndefined();
  });

  it('should handle failed login', async () => {
    mockApi.authenticate.mockRejectedValue(new Error('Invalid API key'));

    const { result } = renderHook(() => useAuth());

    await act(async () => {
      const success = await result.current.login('invalid-key');
      expect(success).toBe(false);
    });

    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBe('Invalid API key');
  });

  it('should handle logout', () => {
    const { result } = renderHook(() => useAuth());

    act(() => {
      result.current.logout();
    });

    expect(mockApi.logout).toHaveBeenCalled();
    expect(result.current.isAuthenticated).toBe(false);
    expect(result.current.error).toBeUndefined();
  });

  it('should clear error', () => {
    const { result } = renderHook(() => useAuth());

    // First set an error
    act(() => {
      result.current.login('invalid-key');
    });

    // Then clear it
    act(() => {
      result.current.clearError();
    });

    expect(result.current.error).toBeUndefined();
  });
});

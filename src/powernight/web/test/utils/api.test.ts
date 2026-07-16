import { vi, type Mocked } from 'vitest';
import { api } from '../../src/utils/api';

// Mock axios. The `api` singleton is constructed at import time and calls
// axios.create().interceptors.* in its constructor, so the mock must return a
// client with an interceptors shape. create() returns the same object so that
// `this.client === mockedAxios` and the per-test get/post stubs take effect.
vi.mock('axios', () => {
  const client = {
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    create: vi.fn(),
  };
  client.create.mockReturnValue(client);
  return { default: client };
});
import axios from 'axios';
const mockedAxios = axios as unknown as Mocked<typeof axios>;

describe('PowerNightAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    // `api` is a module singleton; reset its in-memory key so state does not
    // bleed between tests.
    api.clearApiKey();
  });

  describe('API Key management', () => {
    it('should set and get API key', () => {
      api.setApiKey('test-key');
      expect(api.isAuthenticated()).toBe(true);
    });

    it('should clear API key', () => {
      api.setApiKey('test-key');
      api.clearApiKey();
      expect(api.isAuthenticated()).toBe(false);
    });

    it('should load API key from localStorage on initialization', () => {
      localStorage.setItem('powernight_api_key', 'stored-key');
      const newApi = new (api.constructor as new () => typeof api)();
      expect(newApi.isAuthenticated()).toBe(true);
    });
  });


  describe('API calls', () => {
    beforeEach(() => {
      mockedAxios.create.mockReturnValue(mockedAxios);
    });

    it('should make GET request to health endpoint', async () => {
      const mockResponse = { data: { status: 'healthy' } };
      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getHealth();
      expect(result).toEqual({ status: 'healthy' });
      expect(mockedAxios.get).toHaveBeenCalledWith('/health');
    });

    it('should make GET request to status endpoint', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: { status: 'healthy', timestamp: '2023-01-01T00:00:00Z' }
        }
      };
      mockedAxios.get.mockResolvedValue(mockResponse);

      const result = await api.getStatus();
      expect(result).toEqual({ status: 'healthy', timestamp: '2023-01-01T00:00:00Z' });
      expect(mockedAxios.get).toHaveBeenCalledWith('/status');
    });

    it('should handle API errors', async () => {
      const mockError = new Error('Network Error');
      mockedAxios.get.mockRejectedValue(mockError);

      await expect(api.getHealth()).rejects.toThrow('Network Error');
    });

    it('should set backup reserve', async () => {
      const mockResponse = {
        data: {
          success: true,
          data: { backup_reserve_percentage: 20, connected: true }
        }
      };
      mockedAxios.post.mockResolvedValue(mockResponse);

      const result = await api.setPowerwallReserve({ percentage: 20, reason: 'Test' });
      expect(result).toEqual({ backup_reserve_percentage: 20, connected: true });
      expect(mockedAxios.post).toHaveBeenCalledWith('/backup-reserve', {
        percentage: 20,
        reason: 'Test'
      });
    });
  });

  describe('Authentication', () => {
    it('should detect when authentication is required', async () => {
      vi.mocked(fetch).mockResolvedValue({ status: 401 } as Response);

      await expect(api.checkAuthRequired()).resolves.toBe(true);
      expect(fetch).toHaveBeenCalledWith('/api/v1/auth/check', expect.any(Object));
    });

    it('should attach the API key to authenticated fetch requests', async () => {
      api.setApiKey('valid-key');
      vi.mocked(fetch).mockResolvedValue({ status: 200 } as Response);

      await api.authenticatedFetch('/api/auth/site-details');

      const init = vi.mocked(fetch).mock.calls[0][1];
      expect(new Headers(init?.headers).get('X-API-Key')).toBe('valid-key');
    });

    it('should clear a rejected key from authenticated fetch requests', async () => {
      api.setApiKey('invalid-key');
      vi.mocked(fetch).mockResolvedValue({ status: 401 } as Response);

      await api.authenticatedFetch('/api/auth/site-details');

      expect(api.isAuthenticated()).toBe(false);
    });

    it('should authenticate with valid API key', async () => {
      mockedAxios.get.mockResolvedValue({ data: { status: 'healthy' } });

      const result = await api.authenticate('valid-key');
      expect(result).toBe(true);
      expect(api.isAuthenticated()).toBe(true);
      expect(mockedAxios.get).toHaveBeenCalledWith('/auth/check');
    });

    it('should fail authentication with invalid API key', async () => {
      mockedAxios.get.mockRejectedValue(new Error('Unauthorized'));

      // authenticate() re-throws on failure; the useAuth hook catches it.
      await expect(api.authenticate('invalid-key')).rejects.toThrow('Unauthorized');
      expect(api.isAuthenticated()).toBe(false);
    });
  });

  describe('Polling', () => {
    beforeEach(() => {
      vi.useFakeTimers();
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('should start and stop polling', () => {
      const mockResponse = { data: { success: true, data: { status: 'healthy' } } };
      mockedAxios.get.mockResolvedValue(mockResponse);

      api.startPolling(1000);
      expect(api['pollingInterval']).toBeTruthy();

      api.stopPolling();
      expect(api['pollingInterval']).toBeNull();
    });
  });
});

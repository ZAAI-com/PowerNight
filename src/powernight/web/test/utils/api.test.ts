import { vi, type Mocked } from 'vitest';
import { api } from '../../src/utils/api';

// Mock axios
vi.mock('axios');
import axios from 'axios';
const mockedAxios = axios as Mocked<typeof axios>;

describe('PowerNightAPI', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
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
      const newApi = new (api.constructor as any)();
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
    it('should authenticate with valid API key', async () => {
      mockedAxios.get.mockResolvedValue({ data: { status: 'healthy' } });

      const result = await api.authenticate('valid-key');
      expect(result).toBe(true);
      expect(api.isAuthenticated()).toBe(true);
    });

    it('should fail authentication with invalid API key', async () => {
      mockedAxios.get.mockRejectedValue(new Error('Unauthorized'));

      const result = await api.authenticate('invalid-key');
      expect(result).toBe(false);
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

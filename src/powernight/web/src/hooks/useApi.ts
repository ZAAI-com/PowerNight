import { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';
import { LoadingState } from '../types';

export interface UseApiOptions {
  immediate?: boolean;
  onSuccess?: (data: unknown) => void;
  onError?: (error: Error) => void;
}

export function useApi<T>(
  apiCall: () => Promise<T>,
  options: UseApiOptions = {}
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<LoadingState>({ isLoading: false });
  const { immediate = true, onSuccess, onError } = options;

  const execute = useCallback(async () => {
    setLoading({ isLoading: true, error: undefined });
    
    try {
      const result = await apiCall();
      setData(result);
      setLoading({ isLoading: false });
      onSuccess?.(result);
      return result;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'An unknown error occurred';
      setLoading({ isLoading: false, error: errorMessage });
      onError?.(error as Error);
      throw error;
    }
  }, [apiCall, onSuccess, onError]);

  useEffect(() => {
    if (immediate) {
      execute();
    }
  }, [execute, immediate]);

  return {
    data,
    loading,
    execute,
    refetch: execute
  };
}

export function usePolling<T>(
  apiCall: () => Promise<T>,
  interval: number = 30000,
  options: UseApiOptions = {}
) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<LoadingState>({ isLoading: false });
  const [error, setError] = useState<string | undefined>();
  const { onSuccess, onError } = options;

  const execute = useCallback(async () => {
    try {
      const result = await apiCall();
      setData(result);
      setError(undefined);
      onSuccess?.(result);
      return result;
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : 'An unknown error occurred';
      setError(errorMessage);
      onError?.(err as Error);
      throw err;
    }
  }, [apiCall, onSuccess, onError]);

  useEffect(() => {
    let intervalId: NodeJS.Timeout;

    const startPolling = () => {
      setLoading({ isLoading: true });
      execute().finally(() => {
        setLoading({ isLoading: false });
        intervalId = setInterval(execute, interval);
      });
    };

    startPolling();

    return () => {
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [execute, interval]);

  return {
    data,
    loading: { isLoading: loading.isLoading, error },
    refetch: execute
  };
}

export function useStatusPolling() {
  return usePolling(
    () => api.getStatus(),
    30000, // Poll every 30 seconds
    {
      onError: (error) => {
        console.warn('Status polling error:', error.message);
      }
    }
  );
}

export function usePowerwallStatus() {
  return usePolling(
    () => api.getPowerwallStatus(),
    10000, // Poll every 10 seconds
    {
      onError: (error) => {
        console.warn('Powerwall status polling error:', error.message);
      }
    }
  );
}

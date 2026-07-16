import { useState, useEffect, useCallback } from 'react';
import { api } from '../utils/api';

export interface AuthState {
  isAuthenticated: boolean;
  isLoading: boolean;
  error?: string;
}

export function useAuth() {
  const [authState, setAuthState] = useState<AuthState>({
    isAuthenticated: false, // Will be determined after checking auth requirements
    isLoading: true // Start with loading to check auth requirements
  });

  const login = useCallback(async (apiKey: string) => {
    setAuthState(prev => ({ ...prev, isLoading: true, error: undefined }));
    
    try {
      await api.authenticate(apiKey);
      setAuthState({
        isAuthenticated: true,
        isLoading: false
      });
      return true;
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Authentication failed';
      setAuthState({
        isAuthenticated: false,
        isLoading: false,
        error: errorMessage
      });
      return false;
    }
  }, []);

  const logout = useCallback(() => {
    api.logout();
    setAuthState({
      isAuthenticated: false,
      isLoading: false,
      error: undefined
    });
  }, []);

  const clearError = useCallback(() => {
    setAuthState(prev => ({ ...prev, error: undefined }));
  }, []);

  // Check authentication requirements on mount
  useEffect(() => {
    // Ignore stale results: if the component unmounts (or the effect
    // re-runs) before the request resolves, a slow response must not
    // clobber auth state set elsewhere (e.g. by a faster login()).
    let cancelled = false;

    const checkAuthRequirements = async () => {
      try {
        const authRequired = await api.checkAuthRequired();
        if (cancelled) return;

        const hasApiKey = api.isAuthenticated();

        if (!authRequired) {
          // Authentication is disabled, we're always "authenticated"
          setAuthState({
            isAuthenticated: true,
            isLoading: false
          });
        } else if (hasApiKey) {
          // Auth is required and we have an API key
          setAuthState({
            isAuthenticated: true,
            isLoading: false
          });
        } else {
          // Auth is required but we don't have an API key
          setAuthState({
            isAuthenticated: false,
            isLoading: false,
            error: 'Authentication required'
          });
        }
      } catch {
        if (cancelled) return;

        // If we can't check auth requirements, assume auth is required
        setAuthState({
          isAuthenticated: false,
          isLoading: false,
          error: 'Failed to check authentication requirements'
        });
      }
    };

    checkAuthRequirements();

    return () => {
      cancelled = true;
    };
  }, []);

  // Listen for auth events
  useEffect(() => {
    const handleAuthRequired = () => {
      setAuthState({
        isAuthenticated: false,
        isLoading: false,
        error: 'Authentication required'
      });
    };

    const handleConnectionError = (_event: CustomEvent) => {
      setAuthState(prev => ({
        ...prev,
        error: 'Connection error. Please check your network connection.'
      }));
    };

    const handleApiError = (event: CustomEvent) => {
      const { error } = event.detail;
      if (error.message?.includes('401') || error.message?.includes('Unauthorized')) {
        setAuthState({
          isAuthenticated: false,
          isLoading: false,
          error: 'Session expired. Please log in again.'
        });
      }
    };

    window.addEventListener('powernight:auth-required', handleAuthRequired);
    window.addEventListener('powernight:connection-error', handleConnectionError as EventListener);
    window.addEventListener('powernight:api-error', handleApiError as EventListener);

    return () => {
      window.removeEventListener('powernight:auth-required', handleAuthRequired);
      window.removeEventListener('powernight:connection-error', handleConnectionError as EventListener);
      window.removeEventListener('powernight:api-error', handleApiError as EventListener);
    };
  }, []);

  return {
    ...authState,
    login,
    logout,
    clearError
  };
}

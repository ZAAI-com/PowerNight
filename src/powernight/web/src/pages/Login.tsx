import React, { useState } from 'react';
import { LoadingSpinner } from '../components/LoadingSpinner';
import { cn } from '../utils/helpers';

interface LoginProps {
  error?: string;
  onLogin: (apiKey: string) => Promise<boolean>;
  onClearError: () => void;
}

const Login: React.FC<LoginProps> = ({ error, onLogin, onClearError }) => {
  const [apiKey, setApiKey] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    const key = apiKey.trim();
    if (!key) return;

    setIsLoading(true);
    onClearError();

    try {
      await onLogin(key);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50 py-12 px-4 sm:px-6 lg:px-8">
      <div className="max-w-md w-full space-y-8">
        <div>
          <div className="mx-auto h-12 w-12 flex items-center justify-center rounded-full bg-blue-100">
            <svg
              className="h-8 w-8 text-blue-600"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 10V3L4 14h7v7l9-11h-7z"
              />
            </svg>
          </div>
          <h2 className="mt-6 text-center text-3xl font-extrabold text-gray-900">
            PowerNight
          </h2>
          <p className="mt-2 text-center text-sm text-gray-600">
            Enter the API key configured for this PowerNight server
          </p>
        </div>

        <form className="mt-8 space-y-6" onSubmit={handleLogin}>
          <div>
            <label htmlFor="api-key" className="sr-only">
              API key
            </label>
            <input
              id="api-key"
              name="api-key"
              type="password"
              required
              autoComplete="current-password"
              className="appearance-none rounded-md relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-blue-500 focus:border-blue-500 focus:z-10 sm:text-sm"
              placeholder="Enter your API key"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              disabled={isLoading}
            />
          </div>

          {error && (
            <div className="rounded-md bg-red-50 p-4">
              <div className="flex">
                <div className="flex-shrink-0">
                  <svg
                    className="h-5 w-5 text-red-400"
                    viewBox="0 0 20 20"
                    fill="currentColor"
                  >
                    <path
                      fillRule="evenodd"
                      d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                      clipRule="evenodd"
                    />
                  </svg>
                </div>
                <div className="ml-3">
                  <h3 className="text-sm font-medium text-red-800">
                    Authentication Error
                  </h3>
                  <div className="mt-2 text-sm text-red-700">
                    <p>{error}</p>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div>
            <button
              type="submit"
              disabled={isLoading || !apiKey.trim()}
              className={cn(
                'group relative w-full flex justify-center py-2 px-4 border border-transparent text-sm font-medium rounded-md text-white focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500',
                isLoading || !apiKey.trim()
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-blue-600 hover:bg-blue-700'
              )}
            >
              {isLoading ? (
                <LoadingSpinner size="sm" />
              ) : (
                'Sign In'
              )}
            </button>
          </div>

          <div className="text-center">
            <p className="text-xs text-gray-500">
              Tesla account authorization is managed separately in Settings.
            </p>
          </div>
        </form>
      </div>
    </div>
  );
};

export default Login;

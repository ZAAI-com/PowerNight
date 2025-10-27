import React, { useState, useEffect } from 'react';
import { formatDateTimeWithTimezone } from '../utils/dateTimeFormatter';
import { useTimezone } from '../contexts/TimezoneContext';
import api from '../utils/api';
import { getAllCommonTimezones } from '../utils/timezones';

interface Site {
  id: string;
  name: string;
  type: string;
  state: string;
}

interface AuthInfo {
  authenticated: boolean;
  email?: string;
  site_id?: string;
  token_type?: string;
  expires_at?: string;
  expires_in_seconds?: number;
  token_expired?: boolean;
  storage_path?: string;
  file_size?: number;
  modified_at?: string;
  access_token_masked?: string;
  refresh_token_masked?: string;
  message?: string;
}

interface VersionInfo {
  application: string;
  version: string;
  build_timestamp: string;
  python_version: string;
  node_version: string;
  npm_version: string;
  backend_dependencies: Record<string, string>;
  frontend_dependencies: Record<string, string>;
}


interface TimezoneOption {
  value: string;
  label: string;
  region: string;
  offset?: string; // Optional to match Timezone interface
}

type FlowStep = 'initial' | 'awaiting_login' | 'awaiting_callback' | 'selecting_site' | 'complete';

const Settings: React.FC = () => {
  // Get timezone context
  const { timezoneInfo, currentTime, isLoading: timezoneLoading, refreshTimezone } = useTimezone();

  // OAuth Flow State
  const [currentStep, setCurrentStep] = useState<FlowStep>('initial');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [callbackUrl, setCallbackUrl] = useState('');
  const [sites, setSites] = useState<Site[]>([]);

  // Auth Info State
  const [authInfo, setAuthInfo] = useState<AuthInfo | null>(null);
  const [authInfoLoading, setAuthInfoLoading] = useState(false);

  // Version Info State
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [versionLoading, setVersionLoading] = useState(false);

  // Timezone State
  const [availableTimezones, setAvailableTimezones] = useState<TimezoneOption[]>(getAllCommonTimezones()); // Initialize with local timezones
  const [selectedTimezone, setSelectedTimezone] = useState<string>('Europe/Berlin'); // Default to Berlin
  const [timezoneSaving, setTimezoneSaving] = useState(false);
  const [timezoneSuccess, setTimezoneSuccess] = useState<string | null>(null);
  const [isEditingTimezone, setIsEditingTimezone] = useState(false);

  // UI State
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const validateEmail = (email: string): boolean => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  };

  const validateCallbackUrl = (url: string): boolean => {
    try {
      const urlObj = new URL(url);
      return urlObj.searchParams.has('code') && urlObj.searchParams.has('state');
    } catch {
      return false;
    }
  };

  const handleConnect = async () => {
    setError(null);

    // Validate email
    if (!validateEmail(email)) {
      setError('Please enter a valid email address');
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch('/api/auth/setup/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email }),
      });

      const data = await response.json();

      if (data.success) {
        setSessionId(data.session_id);
        setCurrentStep('awaiting_login');

        // Open Tesla auth in NEW browser tab
        window.open(data.auth_url, '_blank');
      } else {
        setError(data.error || 'Failed to start authentication');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setIsLoading(false);
    }
  };

  const handleVerify = async () => {
    setError(null);

    // Validate callback URL
    if (!validateCallbackUrl(callbackUrl)) {
      setError('Invalid callback URL. Please copy the complete URL from the Tesla authorization page that contains "code=" and "state=" parameters.');
      return;
    }

    if (!sessionId) {
      setError('Session expired. Please start over');
      return;
    }

    setIsLoading(true);

    try {
      const response = await fetch('/api/auth/setup/callback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, callback_url: callbackUrl }),
      });

      const data = await response.json();

      if (data.success) {
        setSites(data.sites);
        setCurrentStep('selecting_site');

        // Auto-select first site and complete setup
        if (data.sites && data.sites.length > 0) {
          const firstSite = data.sites[0];
          await completeSetup(firstSite.id);
        }
      } else {
        setError(data.error || 'Failed to verify callback URL');
      }
    } catch (err) {
      setError('Failed to connect to server');
    } finally {
      setIsLoading(false);
    }
  };

  const completeSetup = async (siteId: string) => {
    if (!sessionId) return;

    try {
      const response = await fetch('/api/auth/setup/complete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, site_id: siteId }),
      });

      const data = await response.json();

      if (data.success) {
        setCurrentStep('complete');
      } else {
        setError(data.error || 'Failed to complete setup');
      }
    } catch (err) {
      setError('Failed to complete setup');
    }
  };

  const fetchAuthInfo = async () => {
    setAuthInfoLoading(true);
    try {
      const response = await fetch('/api/auth/tesla/info');
      const data = await response.json();

      if (data.success) {
        setAuthInfo(data.data);
        // If we have auth info, update the email and step
        if (data.data.authenticated && data.data.email) {
          setEmail(data.data.email);
          setCurrentStep('complete');
        }
      }
    } catch (err) {
      console.error('Failed to fetch auth info:', err);
    } finally {
      setAuthInfoLoading(false);
    }
  };

  const fetchVersionInfo = async () => {
    setVersionLoading(true);
    try {
      const response = await fetch('/api/v1/version-info.json');

      if (!response.ok) {
        console.error(`Failed to fetch version info: HTTP ${response.status} ${response.statusText}`);
        console.error('Make sure to run ./build.sh to generate version-info.json');
        return;
      }

      const data = await response.json();
      console.log('Version info loaded:', data);
      setVersionInfo(data);
    } catch (err) {
      console.error('Failed to fetch version info:', err);
      console.error('Error details:', {
        message: err instanceof Error ? err.message : String(err),
        url: window.location.origin + '/api/v1/version-info.json'
      });
    } finally {
      setVersionLoading(false);
    }
  };

  const fetchAvailableTimezones = async () => {
    try {
      const data = await api.getAvailableTimezones();
      setAvailableTimezones(data.timezones);
    } catch (err) {
      console.error('Failed to fetch available timezones from API, using local fallback:', err);
      // Use local timezone list as fallback
      const localTimezones = getAllCommonTimezones();
      setAvailableTimezones(localTimezones);
    }
  };

  const handleTimezoneChange = (newTimezone: string) => {
    setSelectedTimezone(newTimezone);
  };

  const handleEditTimezone = () => {
    setIsEditingTimezone(true);
  };

  const handleSaveAndReloadTimezone = async () => {
    setTimezoneSaving(true);
    setTimezoneSuccess(null);
    setError(null);

    try {
      // Save timezone
      await api.updateTimezone(selectedTimezone);
      
      // Reload all tasks with new timezone
      const reloadResult = await api.reloadAllTasks();
      setTimezoneSuccess(reloadResult.message);

      // Refresh timezone info
      refreshTimezone();
      
      // Exit edit mode
      setIsEditingTimezone(false);
      
      // Clear success message after 5 seconds
      setTimeout(() => {
        setTimezoneSuccess(null);
      }, 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save timezone');
    } finally {
      setTimezoneSaving(false);
    }
  };

  // Load auth info, version info, and available timezones on component mount
  useEffect(() => {
    fetchAuthInfo();
    fetchVersionInfo();
    fetchAvailableTimezones();
  }, []);

  // Update selected timezone when timezone info changes
  useEffect(() => {
    if (timezoneInfo?.timezone) {
      setSelectedTimezone(timezoneInfo.timezone);
    }
  }, [timezoneInfo]);

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          <h1 className="text-3xl font-bold text-gray-900 mb-6">Settings</h1>

          {/* Error Display */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-800 text-sm">{error}</p>
            </div>
          )}

          {/* Tesla Account Section */}
          <div className="bg-white shadow rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Tesla Account</h2>

            {currentStep === 'initial' && (
              <div className="space-y-4">
                <div>
                  <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
                    Tesla Account Email
                  </label>
                  <div className="flex gap-3">
                    <input
                      type="email"
                      id="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="your-email@example.com"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                      onClick={handleConnect}
                      disabled={isLoading}
                      className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isLoading ? 'Connecting...' : 'Connect'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {(currentStep === 'awaiting_login' || currentStep === 'awaiting_callback') && (
              <div className="space-y-4">
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-md">
                  <p className="text-blue-800 text-sm">
                    ✅ Tesla authorization page opened in new tab. Please log in and authorize PowerNight.
                  </p>
                </div>

                <div>
                  <label htmlFor="callbackUrl" className="block text-sm font-medium text-gray-700 mb-2">
                    URL of the Tesla Not-Found Page
                  </label>
                  <div className="flex gap-3">
                    <input
                      type="text"
                      id="callbackUrl"
                      value={callbackUrl}
                      onChange={(e) => setCallbackUrl(e.target.value)}
                      placeholder="https://auth.tesla.com/void/callback?code=abc123&state=xyz789"
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                    <button
                      onClick={handleVerify}
                      disabled={isLoading}
                      className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {isLoading ? 'Verifying...' : 'Verify'}
                    </button>
                  </div>
                </div>
              </div>
            )}

            {(currentStep === 'selecting_site' || currentStep === 'complete') && (
              <div className="space-y-4">
                <div className="p-4 bg-green-50 border border-green-200 rounded-md">
                  <p className="text-green-800 font-medium">✅ Tesla Account connected</p>
                  <p className="text-green-700 text-sm mt-1">Email: {email}</p>
                </div>
              </div>
            )}
          </div>

          {/* Energy Sites Section */}
          {sites.length > 0 && (
            <div className="bg-white shadow rounded-lg p-6 mb-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">Energy Sites</h2>

              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Site Name
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                        Selection
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white divide-y divide-gray-200">
                    {sites.map((site, index) => (
                      <tr key={site.id} className={index === 0 ? 'bg-green-50' : ''}>
                        <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                          {site.name}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {site.type}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                          {site.state}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          {index === 0 ? (
                            <span className="px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                              Selected
                            </span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* PyPowerwall Auth Info Section */}
          {authInfo && (
            <div className="bg-white shadow rounded-lg p-6 mb-6">
              <h2 className="text-xl font-semibold text-gray-900 mb-4">PyPowerwall Authentication</h2>

              {authInfoLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                  <span className="ml-2 text-gray-600">Loading authentication info...</span>
                </div>
              ) : authInfo.authenticated ? (
                <div className="space-y-4">
                  <div className="p-4 bg-green-50 border border-green-200 rounded-md">
                    <p className="text-green-800 font-medium">✅ PyPowerwall authentication file found</p>
                    <p className="text-green-700 text-sm mt-1">Authentication data is available and ready to use</p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <h3 className="text-lg font-medium text-gray-900 mb-3">Account Information</h3>
                      <dl className="space-y-2">
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Email</dt>
                          <dd className="text-sm text-gray-900">{authInfo.email || 'Unknown'}</dd>
                        </div>
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Site ID</dt>
                          <dd className="text-sm text-gray-900">{authInfo.site_id || 'Not set'}</dd>
                        </div>
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Token Type</dt>
                          <dd className="text-sm text-gray-900">{authInfo.token_type || 'Unknown'}</dd>
                        </div>
                      </dl>
                    </div>

                    <div>
                      <h3 className="text-lg font-medium text-gray-900 mb-3">Token Status</h3>
                      <dl className="space-y-2">
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Status</dt>
                          <dd className="text-sm">
                            <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                              authInfo.token_expired
                                ? 'bg-red-100 text-red-800'
                                : 'bg-green-100 text-green-800'
                            }`}>
                              {authInfo.token_expired ? 'Expired' : 'Valid'}
                            </span>
                          </dd>
                        </div>
                        {authInfo.expires_at && (
                          <div>
                            <dt className="text-sm font-medium text-gray-500">Expires</dt>
                            <dd className="text-sm text-gray-900 font-mono">
                              {formatDateTimeWithTimezone(authInfo.expires_at, timezoneInfo?.timezone)}
                            </dd>
                          </div>
                        )}
                        {authInfo.expires_in_seconds !== undefined && (
                          <div>
                            <dt className="text-sm font-medium text-gray-500">Time Remaining</dt>
                            <dd className="text-sm text-gray-900">
                              {authInfo.expires_in_seconds > 0
                                ? `${Math.floor(authInfo.expires_in_seconds / 3600)}h ${Math.floor((authInfo.expires_in_seconds % 3600) / 60)}m`
                                : 'Expired'
                              }
                            </dd>
                          </div>
                        )}
                      </dl>
                    </div>
                  </div>

                  <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Token Information</h3>
                    <dl className="space-y-2">
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Access Token</dt>
                        <dd className="text-sm text-gray-900 font-mono bg-gray-100 px-2 py-1 rounded">
                          {authInfo.access_token_masked || 'Not available'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Refresh Token</dt>
                        <dd className="text-sm text-gray-900 font-mono bg-gray-100 px-2 py-1 rounded">
                          {authInfo.refresh_token_masked || 'Not available'}
                        </dd>
                      </div>
                    </dl>
                  </div>

                  <div>
                    <h3 className="text-lg font-medium text-gray-900 mb-3">File Information</h3>
                    <dl className="space-y-2">
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Storage Path</dt>
                        <dd className="text-sm text-gray-900 font-mono bg-gray-100 px-2 py-1 rounded">
                          {authInfo.storage_path || 'Unknown'}
                        </dd>
                      </div>
                      {authInfo.file_size && (
                        <div>
                          <dt className="text-sm font-medium text-gray-500">File Size</dt>
                          <dd className="text-sm text-gray-900">{authInfo.file_size} bytes</dd>
                        </div>
                      )}
                      {authInfo.modified_at && (
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Last Modified</dt>
                          <dd className="text-sm text-gray-900 font-mono">
                            {formatDateTimeWithTimezone(authInfo.modified_at, timezoneInfo?.timezone)}
                          </dd>
                        </div>
                      )}
                    </dl>
                  </div>

                  <div className="pt-4 border-t border-gray-200">
                    <button
                      onClick={fetchAuthInfo}
                      className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors text-sm"
                    >
                      Refresh Auth Info
                    </button>
                  </div>
                </div>
              ) : (
                <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-md">
                  <p className="text-yellow-800 text-sm">
                    {authInfo.message || 'No PyPowerwall authentication file found in the data folder.'}
                  </p>
                  <p className="text-yellow-700 text-sm mt-1">
                    If you have a .pypowerwall.auth file, make sure it's placed in the correct data/tokens directory.
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Timezone Configuration Section */}
          <div className="bg-white shadow rounded-lg p-6 mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Timezone Configuration</h2>

            {timezoneLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-2 text-gray-600">Loading timezone settings...</span>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <label htmlFor="timezone" className="block text-sm font-medium text-gray-700 mb-2">
                    Timezone
                  </label>
                  <div className="flex gap-2">
                    <select
                      id="timezone"
                      value={selectedTimezone}
                      onChange={(e) => handleTimezoneChange(e.target.value)}
                      disabled={!isEditingTimezone}
                      className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed disabled:bg-gray-100"
                    >
                      {availableTimezones.length === 0 && (
                        <option value="Europe/Berlin">Europe/Berlin (Germany)</option>
                      )}
                      {availableTimezones.map((tz) => (
                        <option key={tz.value} value={tz.value}>
                          {tz.label}
                        </option>
                      ))}
                    </select>
                    <button
                      onClick={isEditingTimezone ? handleSaveAndReloadTimezone : handleEditTimezone}
                      disabled={timezoneSaving}
                      className="bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
                    >
                      {timezoneSaving ? 'Saving...' : (isEditingTimezone ? 'Save' : 'Edit')}
                    </button>
                  </div>
                </div>

                {currentTime && (
                  <div className="p-4 bg-blue-50 border border-blue-200 rounded-md">
                    <p className="text-sm font-medium text-gray-700">Current time:</p>
                    <p className="text-2xl font-mono font-bold text-blue-900 mt-1">
                      {currentTime}
                    </p>
                  </div>
                )}

                <div className="p-4 bg-gray-50 border border-gray-200 rounded-md">
                  <p className="text-sm text-gray-600">
                    <span className="font-medium">ℹ️ Note:</span> All scheduled tasks will execute using this timezone.
                    Click 'Edit' to change the timezone, then 'Save' to apply changes and reload all tasks automatically.
                  </p>
                </div>

                {timezoneSuccess && (
                  <div className="p-4 bg-green-50 border border-green-200 rounded-md">
                    <p className="text-green-800 text-sm">✅ {timezoneSuccess}</p>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Version Information Section */}
          <div className="bg-white shadow rounded-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">Version Information</h2>

            {versionLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-2 text-gray-600">Loading version info...</span>
              </div>
            ) : versionInfo ? (
              <div className="space-y-6">
                {/* Application Info */}
                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 p-4 rounded-lg border border-blue-200">
                  <h3 className="text-lg font-medium text-gray-900 mb-3">Application</h3>
                  <dl className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Version</dt>
                      <dd className="text-lg font-bold text-blue-900 font-mono">
                        {versionInfo.version}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Build Date</dt>
                      <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                        {formatDateTimeWithTimezone(versionInfo.build_timestamp, timezoneInfo?.timezone)}
                      </dd>
                    </div>
                  </dl>
                </div>

                {/* Runtime Environment */}
                <div className="bg-gray-50 p-4 rounded-lg">
                  <h3 className="text-lg font-medium text-gray-900 mb-3">Runtime Environment</h3>
                  <dl className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Python</dt>
                      <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                        {versionInfo.python_version}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm font-medium text-gray-500">Node.js</dt>
                      <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                        {versionInfo.node_version}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-sm font-medium text-gray-500">npm</dt>
                      <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                        {versionInfo.npm_version}
                      </dd>
                    </div>
                  </dl>
                </div>

                {/* Backend and Frontend Components Side by Side */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Backend Components */}
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Backend Components</h3>
                    <dl className="space-y-2">
                      {Object.entries(versionInfo.backend_dependencies).map(([name, version]) => (
                        <div key={name} className="flex justify-between items-center bg-white px-3 py-2 rounded">
                          <dt className="text-sm font-medium text-gray-600">{name}</dt>
                          <dd className="text-sm text-gray-900 font-mono">{version}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>

                  {/* Frontend Components */}
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Frontend Components</h3>
                    <dl className="space-y-2">
                      {Object.entries(versionInfo.frontend_dependencies).map(([name, version]) => (
                        <div key={name} className="flex justify-between items-center bg-white px-3 py-2 rounded">
                          <dt className="text-sm font-medium text-gray-600">{name}</dt>
                          <dd className="text-sm text-gray-900 font-mono">{version}</dd>
                        </div>
                      ))}
                    </dl>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500 mb-4">Version information not available</p>
                <button
                  onClick={fetchVersionInfo}
                  className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors text-sm"
                >
                  Load Version Info
                </button>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Settings;

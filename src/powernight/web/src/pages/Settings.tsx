import React, { useCallback, useEffect, useState } from 'react';
import { formatDateTimeWithTimezone } from '../utils/dateTimeFormatter';
import { useTimezone } from '../contexts/TimezoneContext';
import { useToast } from '../contexts/ToastContext';
import { useTeslaSetup } from '../hooks/useTeslaSetup';
import api from '../utils/api';
import { getAllCommonTimezones } from '../utils/timezones';
import { TeslaConnectionStatus } from '../components/tesla/TeslaConnectionStatus';
import { TeslaSetupWizard } from '../components/tesla/TeslaSetupWizard';
import type { TeslaAuthInfo, TeslaEnergySite, TeslaSetupResponse } from '../types';

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

const Settings: React.FC = () => {
  // Get timezone context
  const { timezoneInfo, currentTime, isLoading: timezoneLoading, refreshTimezone } = useTimezone();
  const { showToast } = useToast();

  // Tesla account state
  const [confirmSignOut, setConfirmSignOut] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [reconnectOpen, setReconnectOpen] = useState(false);
  const [savedSites, setSavedSites] = useState<TeslaEnergySite[]>([]);

  // Auth Info State
  const [authInfo, setAuthInfo] = useState<TeslaAuthInfo | null>(null);
  const [authInfoLoading, setAuthInfoLoading] = useState(false);
  const [connectionTesting, setConnectionTesting] = useState(false);

  // Version Info State
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [versionLoading, setVersionLoading] = useState(false);

  // Timezone State
  const [availableTimezones, setAvailableTimezones] = useState<TimezoneOption[]>(getAllCommonTimezones()); // Initialize with local timezones
  const [selectedTimezone, setSelectedTimezone] = useState<string>('Europe/Berlin'); // Pre-load placeholder only; replaced by the configured timezone on mount
  const [timezoneSaving, setTimezoneSaving] = useState(false);
  const [isEditingTimezone, setIsEditingTimezone] = useState(false);

  // UI State
  const [error, setError] = useState<string | null>(null);

  const fetchAuthInfo = useCallback(async () => {
    setAuthInfoLoading(true);
    try {
      const response = await api.authenticatedFetch('/api/auth/tesla/info');
      const data = await response.json();

      if (data.success) {
        setAuthInfo(data.data);
      }
    } catch (err) {
      console.error('Failed to fetch auth info:', err);
    } finally {
      setAuthInfoLoading(false);
    }
  }, []);

  const handleSetupCompleted = useCallback(async (result: TeslaSetupResponse) => {
    const sites = result.setup?.sites;
    if (sites) setSavedSites(sites);
    setReconnectOpen(false);
    setError(null);
    if (result.success) {
      showToast('Tesla account connected', 'success');
    } else {
      setError(result.connection_error || result.message || 'Tesla credentials were saved, but the live connection failed.');
    }
    await fetchAuthInfo();
  }, [fetchAuthInfo, showToast]);

  const teslaSetup = useTeslaSetup({ onCompleted: handleSetupCompleted });
  const setupInProgress = teslaSetup.state.phase === 'attempt';

  const handleSignOut = async () => {
    setError(null);
    setSigningOut(true);
    try {
      const response = await api.authenticatedFetch('/api/auth/tesla/logout', { method: 'POST' });
      const data = await response.json();
      if (data.success) {
        setConfirmSignOut(false);
        setReconnectOpen(false);
        setSavedSites([]);
        teslaSetup.dismiss();
        showToast('Signed out of Tesla. Sign in again to reconnect.', 'success');
        await fetchAuthInfo();
      } else {
        setError(data.error || 'Failed to sign out of Tesla');
      }
    } catch {
      setError('Failed to sign out of Tesla');
    } finally {
      setSigningOut(false);
    }
  };

  const handleReconnect = () => {
    setConfirmSignOut(false);
    teslaSetup.dismiss();
    setReconnectOpen(true);
  };

  const closeReconnect = () => {
    setReconnectOpen(false);
    teslaSetup.dismiss();
  };

  const fetchVersionInfo = async () => {
    setVersionLoading(true);
    try {
      const response = await api.authenticatedFetch('/api/v1/version-info.json');

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

  const testTeslaConnection = async () => {
    setConnectionTesting(true);
    setError(null);
    try {
      const response = await api.authenticatedFetch('/api/auth/tesla/test-connection', {
        method: 'POST',
      });
      const data = await response.json();
      if (data.success) {
        setAuthInfo((current) => current ? { ...current, ...data.data } : current);
        showToast('Tesla cloud connection successful', 'success');
      } else {
        setAuthInfo((current) => current ? { ...current, ...data.data, connected: false } : current);
        setError(data.error || 'Tesla cloud connection failed');
        showToast(data.error || 'Tesla cloud connection failed', 'error');
      }
    } catch {
      setError('Failed to test Tesla cloud connection');
      showToast('Failed to test Tesla cloud connection', 'error');
    } finally {
      setConnectionTesting(false);
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
    setError(null);

    try {
      // Save timezone
      await api.updateTimezone(selectedTimezone);

      // Reload all tasks with new timezone
      const reloadResult = await api.reloadAllTasks();
      showToast(reloadResult.message || 'Timezone saved and tasks reloaded', 'success');

      // Refresh timezone info
      refreshTimezone();

      // Exit edit mode
      setIsEditingTimezone(false);
    } catch (err) {
      showToast(err instanceof Error ? err.message : 'Failed to save timezone', 'error');
    } finally {
      setTimezoneSaving(false);
    }
  };

  const fetchCurrentTimezone = async () => {
    try {
      const data = await api.getTimezone();
      setSelectedTimezone(data.timezone);
    } catch (err) {
      console.error('Failed to fetch current timezone:', err);
      // Keep the pre-load placeholder; the timezoneInfo effect below will
      // correct it once the context loads.
    }
  };

  // Load auth info, version info, timezone, and available timezones on component mount
  useEffect(() => {
    fetchAuthInfo();
    fetchVersionInfo();
    fetchCurrentTimezone();
    fetchAvailableTimezones();
    // Mount-only loads
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Update selected timezone when timezone info changes
  useEffect(() => {
    if (timezoneInfo?.timezone) {
      setSelectedTimezone(timezoneInfo.timezone);
    }
  }, [timezoneInfo]);

  const signedIn = Boolean(authInfo?.authenticated);
  const showWizard = !signedIn || reconnectOpen || setupInProgress;
  const savedSiteId = authInfo?.site_id ?? null;

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
          <div className="bg-white shadow rounded-lg p-6 mb-6 space-y-6">
            <h2 className="text-xl font-semibold text-gray-900">Tesla Account</h2>

            {signedIn && authInfo && (
              <TeslaConnectionStatus
                authInfo={authInfo}
                testing={connectionTesting}
                reconnecting={showWizard}
                confirmSignOut={confirmSignOut}
                signingOut={signingOut}
                onTest={testTeslaConnection}
                onReconnect={handleReconnect}
                onRequestSignOut={() => setConfirmSignOut(true)}
                onConfirmSignOut={handleSignOut}
                onCancelSignOut={() => setConfirmSignOut(false)}
              />
            )}

            {showWizard && (
              <div className={signedIn ? 'pt-6 border-t border-gray-200' : ''}>
                {signedIn && <h3 className="text-lg font-medium text-gray-900 mb-4">Reconnect Tesla</h3>}
                <TeslaSetupWizard
                  controller={teslaSetup}
                  mode={signedIn ? 'reconnect' : 'connect'}
                  initialEmail={authInfo?.email ?? ''}
                  currentSiteId={savedSiteId}
                  onClose={signedIn ? closeReconnect : undefined}
                />
              </div>
            )}
          </div>

          {/* Energy Sites Section */}
          {savedSites.length > 0 && (
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
                    {savedSites.map((site) => {
                      const selected = savedSiteId !== null && String(site.id) === String(savedSiteId);
                      return (
                        <tr key={String(site.id)} className={selected ? 'bg-green-50' : ''}>
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
                            {selected ? (
                              <span className="px-3 py-1 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                Selected
                              </span>
                            ) : (
                              <span className="text-gray-400">-</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
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
                  <div className="p-4 bg-blue-50 border border-blue-200 rounded-md">
                    <p className="text-blue-800 font-medium">Tesla credentials stored</p>
                    <p className="text-blue-700 text-sm mt-1">Token validity and live Tesla cloud connectivity are shown separately below.</p>
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
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Live Connection</h3>
                    <dl className="space-y-2">
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Status</dt>
                        <dd className="text-sm">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            authInfo.connected
                              ? 'bg-green-100 text-green-800'
                              : authInfo.connection_status === 'disconnected'
                                ? 'bg-red-100 text-red-800'
                                : 'bg-gray-100 text-gray-800'
                          }`}>
                            {authInfo.connected ? 'Connected' : authInfo.connection_status === 'disconnected' ? 'Disconnected' : 'Unknown'}
                          </span>
                        </dd>
                      </div>
                      {authInfo.last_connection_attempt && (
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Last Attempt</dt>
                          <dd className="text-sm text-gray-900 font-mono">
                            {formatDateTimeWithTimezone(authInfo.last_connection_attempt, timezoneInfo?.timezone)}
                          </dd>
                        </div>
                      )}
                      {authInfo.connection_error && (
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Connection Error</dt>
                          <dd className="text-sm text-red-700">{authInfo.connection_error}</dd>
                        </div>
                      )}
                    </dl>
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

                  <div className="pt-4 border-t border-gray-200 flex flex-wrap gap-3">
                    <button
                      onClick={fetchAuthInfo}
                      disabled={authInfoLoading}
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
                  <div className="flex flex-wrap gap-2">
                    <select
                      id="timezone"
                      value={selectedTimezone}
                      onChange={(e) => handleTimezoneChange(e.target.value)}
                      disabled={!isEditingTimezone}
                      className="flex-1 min-w-0 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-60 disabled:cursor-not-allowed disabled:bg-gray-100"
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
                      className="w-full sm:w-auto bg-blue-600 text-white px-6 py-2 rounded-md hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
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

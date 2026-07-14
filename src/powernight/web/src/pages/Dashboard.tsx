import React, { useState, useEffect, useCallback, useRef } from 'react';
import { formatDate } from '../utils/helpers';

interface SiteDetails {
  [key: string]: unknown;
}

const STORAGE_KEY = 'powernight_site_details';
const AUTO_REFRESH_INTERVAL_MS = 30000;

const Dashboard: React.FC = () => {
  // Load initial data from localStorage
  const [siteDetails, setSiteDetails] = useState<SiteDetails | null>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return stored ? JSON.parse(stored) : null;
    } catch (err) {
      console.error('Failed to load cached site details:', err);
      return null;
    }
  });
  const [siteDetailsLoading, setSiteDetailsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Prevent state updates from in-flight requests after unmount
  const isMountedRef = useRef(true);

  const fetchSiteDetails = useCallback(async () => {
    setSiteDetailsLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/auth/site-details');
      const data = await response.json();

      if (!isMountedRef.current) return;

      if (data.success) {
        setSiteDetails(data.data);
        // Persist to localStorage
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data.data));
      } else {
        setError(data.error || 'Failed to fetch site details');
      }
    } catch (err) {
      console.error('Failed to fetch site details:', err);
      if (!isMountedRef.current) return;
      setError('Failed to fetch site details from server');
    } finally {
      if (isMountedRef.current) {
        setSiteDetailsLoading(false);
      }
    }
  }, []);

  // Fetch on mount (localStorage cache is shown immediately as initial
  // state) and auto-refresh every 30 seconds. The manual "Update Data"
  // button remains available for on-demand refreshes.
  useEffect(() => {
    isMountedRef.current = true;
    fetchSiteDetails();

    const intervalId = window.setInterval(fetchSiteDetails, AUTO_REFRESH_INTERVAL_MS);

    return () => {
      isMountedRef.current = false;
      window.clearInterval(intervalId);
    };
  }, [fetchSiteDetails]);

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-7xl mx-auto py-6 sm:px-6 lg:px-8">
        <div className="px-4 py-6 sm:px-0">
          <h1 className="text-3xl font-bold text-gray-900 mb-6">Dashboard</h1>

          {/* Error Display */}
          {error && (
            <div className="mb-6 p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-800 text-sm">{error}</p>
            </div>
          )}

          {/* Powerwall System Status Section */}
          <div className="bg-white shadow rounded-lg p-6 mb-6">
            <div className="flex flex-wrap gap-3 justify-between items-start mb-4">
              <h2 className="text-xl font-semibold text-gray-900">Powerwall System Status</h2>
              <div className="flex flex-wrap items-center gap-3">
                {siteDetails?.timestamp && (
                  <span className="text-sm text-gray-500">
                    Last Updated: {formatDate(siteDetails.timestamp)}
                  </span>
                )}
                <button
                  onClick={fetchSiteDetails}
                  disabled={siteDetailsLoading}
                  className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {siteDetailsLoading ? 'Updating...' : 'Update Data'}
                </button>
              </div>
            </div>

            {siteDetailsLoading && !siteDetails ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-2 text-gray-600">Loading Powerwall data...</span>
              </div>
            ) : siteDetails ? (
              <div className="space-y-6">
                {/* Top Row: System Information and Power Data */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* Left Column: System Information and Grid Settings */}
                  <div className="space-y-6">
                    <div className="bg-gray-50 p-4 rounded-lg">
                      <h3 className="text-lg font-medium text-gray-900 mb-3">Site Details</h3>
                      <dl className="space-y-2">
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Site Name</dt>
                          <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                            {siteDetails.site_name || 'Unknown'}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Site ID</dt>
                          <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                            {siteDetails.site_id || 'Unknown'}
                          </dd>
                        </div>
                      </dl>
                    </div>

                    <div className="bg-gray-50 p-4 rounded-lg">
                      <h3 className="text-lg font-medium text-gray-900 mb-3">Powerwall Settings</h3>
                      <dl className="space-y-2">
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Backup Reserve</dt>
                          <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                            {siteDetails.reserve !== undefined ? `${Number(siteDetails.reserve).toFixed(2)}%` : 'Unknown'}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Grid Charging</dt>
                          <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                            {siteDetails.grid_charging !== undefined ? (siteDetails.grid_charging ? 'Enabled' : 'Disabled') : 'Unknown'}
                          </dd>
                        </div>
                        <div>
                          <dt className="text-sm font-medium text-gray-500">Grid Export Mode</dt>
                          <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                            {siteDetails.grid_export_mode || 'Unknown'}
                          </dd>
                        </div>
                      </dl>
                    </div>
                  </div>

                  {/* Right Column: Power Data */}
                  <div className="bg-gray-50 p-4 rounded-lg">
                    <h3 className="text-lg font-medium text-gray-900 mb-3">Power Data</h3>
                    <dl className="space-y-2">
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Battery Level</dt>
                        <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                          {siteDetails.battery_level !== undefined ? `${Number(siteDetails.battery_level).toFixed(2)}%` : 'Unknown'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Battery Power</dt>
                        <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                          {siteDetails.battery !== undefined ? `${siteDetails.battery} W` : 'Unknown'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Solar Power</dt>
                        <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                          {siteDetails.solar !== undefined ? `${siteDetails.solar} W` : 'Unknown'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Load Power</dt>
                        <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                          {siteDetails.load !== undefined ? `${siteDetails.load} W` : 'Unknown'}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-sm font-medium text-gray-500">Site Power</dt>
                        <dd className="text-sm text-gray-900 font-mono bg-white px-2 py-1 rounded">
                          {siteDetails.site !== undefined ? `${siteDetails.site} W` : 'Unknown'}
                        </dd>
                      </div>
                    </dl>
                  </div>
                </div>

                {/* Raw Data Section (Collapsible) */}
                <details className="bg-gray-50 p-4 rounded-lg">
                  <summary className="text-lg font-medium text-gray-900 cursor-pointer hover:text-blue-600">
                    Raw Powerwall Data
                  </summary>
                  <div className="mt-4">
                    <pre className="bg-white p-4 rounded text-xs overflow-x-auto border">
                      {JSON.stringify(siteDetails, null, 2)}
                    </pre>
                  </div>
                </details>
              </div>
            ) : (
              <div className="text-center py-8">
                <p className="text-gray-500 mb-2">No Powerwall data available</p>
                <p className="text-gray-400 text-sm mb-4">Click "Update Data" to fetch the latest information</p>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;

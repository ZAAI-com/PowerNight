import React, { useState } from 'react';
import { formatDate } from '../utils/helpers';

interface SiteDetails {
  [key: string]: any;
}

const STORAGE_KEY = 'powernight_site_details';

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

  const fetchSiteDetails = async () => {
    setSiteDetailsLoading(true);
    setError(null);
    try {
      const response = await fetch('/api/auth/site-details');
      const data = await response.json();

      if (data.success) {
        setSiteDetails(data.data);
        // Persist to localStorage
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data.data));
      } else {
        setError(data.error || 'Failed to fetch site details');
      }
    } catch (err) {
      console.error('Failed to fetch site details:', err);
      setError('Failed to fetch site details from server');
    } finally {
      setSiteDetailsLoading(false);
    }
  };

  // Do NOT auto-fetch on mount - only show last available data from localStorage
  // User must click "Update Data" button to refresh

  return (
    <div className="min-h-screen bg-gray-50">
      <main className="max-w-7xl mx-auto py-4 sm:py-6 px-3 sm:px-4 md:px-6 lg:px-8">
        <div className="space-y-4 sm:space-y-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">Dashboard</h1>

          {/* Error Display */}
          {error && (
            <div className="p-3 sm:p-4 bg-red-50 border border-red-200 rounded-md">
              <p className="text-red-800 text-sm">{error}</p>
            </div>
          )}

          {/* Powerwall System Status Section */}
          <div className="bg-white shadow rounded-lg p-4 sm:p-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 sm:gap-4 mb-4 sm:mb-6">
              <h2 className="text-lg sm:text-xl font-semibold text-gray-900">Powerwall System Status</h2>
              <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
                {siteDetails?.timestamp && (
                  <span className="text-xs sm:text-sm text-gray-500">
                    Last Updated: {formatDate(siteDetails.timestamp)}
                  </span>
                )}
                <button
                  onClick={fetchSiteDetails}
                  disabled={siteDetailsLoading}
                  className="w-full sm:w-auto bg-blue-600 text-white px-4 py-3 sm:py-2 rounded-md hover:bg-blue-700 transition-colors text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed min-h-[44px] sm:min-h-0"
                >
                  {siteDetailsLoading ? 'Updating...' : 'Update Data'}
                </button>
              </div>
            </div>

            {siteDetailsLoading ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
                <span className="ml-2 text-gray-600">Loading Powerwall data...</span>
              </div>
            ) : siteDetails ? (
              <div className="space-y-4 sm:space-y-6">
                {/* Top Row: System Information and Power Data */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
                  {/* Left Column: System Information and Grid Settings */}
                  <div className="space-y-4 sm:space-y-6">
                    <div className="bg-gray-50 p-3 sm:p-4 rounded-lg">
                      <h3 className="text-base sm:text-lg font-medium text-gray-900 mb-3">Site Details</h3>
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

                    <div className="bg-gray-50 p-3 sm:p-4 rounded-lg">
                      <h3 className="text-base sm:text-lg font-medium text-gray-900 mb-3">Powerwall Settings</h3>
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
                  <div className="bg-gray-50 p-3 sm:p-4 rounded-lg">
                    <h3 className="text-base sm:text-lg font-medium text-gray-900 mb-3">Power Data</h3>
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
                <details className="bg-gray-50 p-3 sm:p-4 rounded-lg">
                  <summary className="text-base sm:text-lg font-medium text-gray-900 cursor-pointer hover:text-blue-600">
                    Raw Powerwall Data
                  </summary>
                  <div className="mt-3 sm:mt-4">
                    <pre className="bg-white p-3 sm:p-4 rounded text-xs overflow-x-auto border">
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

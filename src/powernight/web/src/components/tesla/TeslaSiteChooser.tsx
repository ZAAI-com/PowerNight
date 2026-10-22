import React, { useState } from 'react';
import type { TeslaEnergySite, TeslaSetupErrorCode } from '../../types';

interface TeslaSiteChooserProps {
  sites: TeslaEnergySite[] | null;
  currentSiteId?: string | number | null;
  errorCode: TeslaSetupErrorCode | null;
  saving: boolean;
  retrying: boolean;
  onChoose: (siteId: string) => void;
  onRetry: () => void;
  onRestart: () => void;
}

/**
 * Choose the energy site to control. A single site is chosen automatically
 * after a fresh sign-in; several require an explicit choice, never the first.
 */
export const TeslaSiteChooser: React.FC<TeslaSiteChooserProps> = ({
  sites, currentSiteId, errorCode, saving, retrying, onChoose, onRetry, onRestart,
}) => {
  const [choice, setChoice] = useState<string | null>(null);
  const currentId = currentSiteId === undefined || currentSiteId === null ? null : String(currentSiteId);

  if (sites === null || sites.length === 0) {
    const unavailable = sites === null || errorCode === 'SITE_DISCOVERY_UNAVAILABLE';
    return (
      <div className="space-y-3">
        <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-md text-sm text-yellow-800 space-y-1">
          {unavailable ? (
            <p>PowerNight signed in to Tesla but could not load your energy sites yet. Try again in a moment.</p>
          ) : (
            <>
              <p className="font-medium">No Powerwall energy sites were found for this Tesla account.</p>
              <p>
                Check that you signed in with the Tesla account that owns the Powerwall. Sites shared with you
                by another owner can take a while to appear.
              </p>
            </>
          )}
        </div>
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={onRetry}
            disabled={retrying}
            className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors text-sm disabled:opacity-50"
          >
            {retrying ? 'Finding Sites...' : 'Retry Finding Sites'}
          </button>
          <button
            type="button"
            onClick={onRestart}
            className="bg-gray-100 text-gray-800 px-4 py-2 rounded-md hover:bg-gray-200 transition-colors text-sm"
          >
            Sign In with a Different Account
          </button>
        </div>
      </div>
    );
  }

  if (sites.length === 1) {
    const site = sites[0];
    return (
      <div className="space-y-3">
        <p className="text-sm text-gray-700">
          Found one energy site: <span className="font-medium">{site.name}</span>.
        </p>
        <button
          type="button"
          onClick={() => onChoose(String(site.id))}
          disabled={saving}
          className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors text-sm disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Use This Site'}
        </button>
      </div>
    );
  }

  return (
    <fieldset className="space-y-3">
      <legend className="text-sm text-gray-700 mb-2">
        This Tesla account has several energy sites. Choose the one PowerNight should control.
      </legend>
      {sites.map((site) => {
        const id = String(site.id);
        return (
          <label
            key={id}
            className={`flex items-center gap-3 p-3 border rounded-md cursor-pointer ${
              choice === id ? 'border-blue-500 bg-blue-50' : 'border-gray-200'
            }`}
          >
            <input
              type="radio"
              name="tesla-site"
              value={id}
              checked={choice === id}
              onChange={() => setChoice(id)}
            />
            <span className="flex-1">
              <span className="block text-sm font-medium text-gray-900">{site.name}</span>
              <span className="block text-xs text-gray-500">Site ID {id} · {site.state}</span>
            </span>
            {currentId === id && (
              <span className="px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                Currently used
              </span>
            )}
          </label>
        );
      })}
      <button
        type="button"
        onClick={() => choice && onChoose(choice)}
        disabled={!choice || saving}
        className="bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700 transition-colors text-sm disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {saving ? 'Saving...' : 'Use This Site'}
      </button>
    </fieldset>
  );
};

export default TeslaSiteChooser;

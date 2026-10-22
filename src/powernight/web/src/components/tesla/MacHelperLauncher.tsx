import React, { useEffect, useState } from 'react';
import type { TeslaHelperState } from '../../types';

const MAC_HELPER_STORAGE_KEY = 'powernight_mac_helper';
const HELPER_TIMEOUT_MS = 15000;

interface MacHelperLauncherProps {
  helperState: TeslaHelperState;
  launchedAt: number | null;
  launching: boolean;
  onLaunch: () => void;
}

function readOptIn(): boolean {
  try {
    return window.localStorage.getItem(MAC_HELPER_STORAGE_KEY) === 'on';
  } catch {
    return false;
  }
}

/**
 * Experimental: the PowerNight Login Mac app signs in to Tesla in its own
 * window and sends the result back here, so nothing has to be copied. The
 * manual steps below keep working for the same attempt either way.
 */
export const MacHelperLauncher: React.FC<MacHelperLauncherProps> = ({
  helperState, launchedAt, launching, onLaunch,
}) => {
  const [optedIn, setOptedIn] = useState(readOptIn);
  const [timedOut, setTimedOut] = useState(false);

  useEffect(() => {
    if (!launchedAt || helperState !== 'pending') {
      setTimedOut(false);
      return;
    }
    const remaining = HELPER_TIMEOUT_MS - (Date.now() - launchedAt);
    if (remaining <= 0) {
      setTimedOut(true);
      return;
    }
    const timer = window.setTimeout(() => setTimedOut(true), remaining);
    return () => window.clearTimeout(timer);
  }, [launchedAt, helperState]);

  const toggle = (value: boolean) => {
    setOptedIn(value);
    try {
      window.localStorage.setItem(MAC_HELPER_STORAGE_KEY, value ? 'on' : 'off');
    } catch {
      // The choice then lasts only for this page
    }
  };

  const insecure = typeof window !== 'undefined' && window.location.protocol === 'http:';

  return (
    <div className="p-4 border border-purple-200 bg-purple-50 rounded-md space-y-3 text-sm">
      <label className="flex items-center gap-2 text-purple-900">
        <input type="checkbox" checked={optedIn} onChange={(event) => toggle(event.target.checked)} />
        Try the experimental Mac helper (PowerNight Login app)
      </label>
      {optedIn && (
        <div className="space-y-2 text-purple-900">
          <p>
            The helper opens Tesla sign-in in its own window and returns the result to PowerNight by itself.
            It never receives your PowerNight API key or Tesla tokens.
          </p>
          {insecure && (
            <p className="text-purple-800">
              This page uses plain HTTP. The helper only connects over HTTP when you allow it for this local
              server in the helper itself.
            </p>
          )}
          <button
            type="button"
            onClick={onLaunch}
            disabled={launching}
            className="bg-purple-700 text-white px-4 py-2 rounded-md hover:bg-purple-800 transition-colors disabled:opacity-50"
          >
            {launching ? 'Opening Helper...' : 'Sign In with the Mac Helper'}
          </button>
          {helperState === 'opened' && (
            <p role="status">The helper is open. Finish signing in to Tesla in its window.</p>
          )}
          {timedOut && (
            <p role="status" className="text-purple-800">
              The helper did not respond. It may not be installed. Continue manually below.
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export default MacHelperLauncher;

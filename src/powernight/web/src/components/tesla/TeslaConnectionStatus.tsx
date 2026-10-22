import React from 'react';
import type { TeslaAuthInfo, TeslaConnectionState } from '../../types';

interface TeslaConnectionStatusProps {
  authInfo: TeslaAuthInfo;
  testing: boolean;
  reconnecting: boolean;
  confirmSignOut: boolean;
  signingOut: boolean;
  onTest: () => void;
  onReconnect: () => void;
  onRequestSignOut: () => void;
  onConfirmSignOut: () => void;
  onCancelSignOut: () => void;
}

/** Older backends do not report connection_state; derive a cautious one. */
function stateOf(info: TeslaAuthInfo): TeslaConnectionState {
  if (info.connection_state) return info.connection_state;
  if (info.connected) return 'connected';
  return info.connection_status === 'disconnected' ? 'temporarily_unavailable' : 'checking';
}

const BADGES: Record<TeslaConnectionState, { label: string; className: string }> = {
  connected: { label: 'Connected', className: 'bg-green-100 text-green-800' },
  sign_in_required: { label: 'Sign-in required', className: 'bg-red-100 text-red-800' },
  temporarily_unavailable: {
    label: 'Connection temporarily unavailable',
    className: 'bg-yellow-100 text-yellow-800',
  },
  checking: { label: 'Checking connection', className: 'bg-gray-100 text-gray-800' },
};

const SIGN_IN_REASONS: Record<string, string> = {
  no_credentials: 'No Tesla sign-in is stored.',
  credentials_unreadable: 'The stored Tesla sign-in could not be read. Reconnect Tesla to replace it.',
  tesla_rejected_sign_in: 'Tesla rejected the stored sign-in. Reconnect Tesla to sign in again.',
  access_token_expired:
    'The stored Tesla sign-in has expired and PowerNight could not open a new connection with it. ' +
    'This happens when PowerNight restarts more than about 8 hours after signing in. Reconnect Tesla to continue.',
};

function describe(state: TeslaConnectionState, info: TeslaAuthInfo): string {
  switch (state) {
    case 'connected':
      return 'PowerNight is connected to your Tesla account.';
    case 'sign_in_required':
      return SIGN_IN_REASONS[info.connection_state_reason ?? ''] ?? 'Tesla needs you to sign in again.';
    case 'temporarily_unavailable':
      return 'Tesla could not be reached just now. Your saved Tesla sign-in is kept, and PowerNight keeps retrying.';
    default:
      return 'PowerNight has not contacted Tesla yet.';
  }
}

const primary = 'px-4 py-2 rounded-md text-sm transition-colors disabled:opacity-50 disabled:cursor-not-allowed';

/** Tesla account summary with the actions that fit its connection state. */
export const TeslaConnectionStatus: React.FC<TeslaConnectionStatusProps> = ({
  authInfo, testing, reconnecting, confirmSignOut, signingOut,
  onTest, onReconnect, onRequestSignOut, onConfirmSignOut, onCancelSignOut,
}) => {
  const state = stateOf(authInfo);
  const badge = BADGES[state];
  const reconnectFirst = state === 'sign_in_required';

  const reconnectButton = (
    <button
      type="button"
      onClick={onReconnect}
      disabled={reconnecting}
      className={`${primary} ${reconnectFirst
        ? 'bg-blue-600 text-white hover:bg-blue-700'
        : 'bg-white text-blue-700 border border-blue-300 hover:bg-blue-50'}`}
    >
      Reconnect Tesla
    </button>
  );
  const testButton = (
    <button
      type="button"
      onClick={onTest}
      disabled={testing}
      className={`${primary} ${reconnectFirst
        ? 'bg-white text-green-700 border border-green-300 hover:bg-green-50'
        : 'bg-green-600 text-white hover:bg-green-700'}`}
    >
      {testing ? 'Testing Connection...' : authInfo.connected ? 'Test Connection' : 'Retry Connection'}
    </button>
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <span role="status" className={`px-3 py-1 rounded-full text-sm font-medium ${badge.className}`}>
          {badge.label}
        </span>
        {authInfo.email && <span className="text-sm text-gray-700">{authInfo.email}</span>}
        {authInfo.site_id !== undefined && authInfo.site_id !== null && (
          <span className="text-sm text-gray-500">Site {String(authInfo.site_id)}</span>
        )}
      </div>
      <p className="text-sm text-gray-700">{describe(state, authInfo)}</p>
      {state === 'temporarily_unavailable' && authInfo.connection_error && (
        <p className="text-sm text-yellow-800">{authInfo.connection_error}</p>
      )}

      <div className="flex flex-wrap gap-3">
        {reconnectFirst ? <>{reconnectButton}{testButton}</> : <>{testButton}{reconnectButton}</>}
        {confirmSignOut ? (
          <>
            <button
              type="button"
              onClick={onConfirmSignOut}
              disabled={signingOut}
              className={`${primary} bg-red-600 text-white hover:bg-red-700`}
            >
              {signingOut ? 'Signing Out...' : 'Confirm Sign Out'}
            </button>
            <button
              type="button"
              onClick={onCancelSignOut}
              disabled={signingOut}
              className={`${primary} bg-gray-100 text-gray-800 hover:bg-gray-200`}
            >
              Cancel
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={onRequestSignOut}
            className={`${primary} bg-white text-red-700 border border-red-300 hover:bg-red-50`}
          >
            Sign Out of Tesla
          </button>
        )}
      </div>
      {state === 'temporarily_unavailable' && (
        <p className="text-xs text-gray-500">Reconnect only if this keeps happening.</p>
      )}
      {confirmSignOut && (
        <p className="text-sm text-red-700">
          Signing out deletes the stored Tesla login. Scheduled tasks cannot change your Powerwall until you sign
          in again. To switch accounts or refresh the sign-in, use Reconnect Tesla instead.
        </p>
      )}
      <p className="text-xs text-gray-500">
        PowerNight keeps its Tesla connection alive while it runs. If PowerNight restarts more than about 8 hours
        after you signed in, Tesla may require you to reconnect.
      </p>
    </div>
  );
};

export default TeslaConnectionStatus;

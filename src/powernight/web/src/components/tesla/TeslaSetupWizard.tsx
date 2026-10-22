import React, { useEffect, useState } from 'react';
import type { TeslaSetupController } from '../../hooks/useTeslaSetup';
import { formatRemaining, isMacOS, wizardStepFor } from '../../utils/teslaSetup';
import { MacHelperLauncher } from './MacHelperLauncher';
import { TeslaSignInHelp } from './TeslaSignInHelp';
import { TeslaSiteChooser } from './TeslaSiteChooser';

const STEPS = ['Start', 'Sign in to Tesla', 'Finish connection', 'Choose site'];
const SITE_STEPS = new Set(['selecting_site', 'completing']);
const WORKING_STEPS = new Set(['exchanging', 'discovering_sites']);
const SITE_ERRORS = new Set(['SITE_DISCOVERY_UNAVAILABLE', 'NO_ENERGY_SITES']);

const validateEmail = (email: string): boolean => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);

interface TeslaSetupWizardProps {
  controller: TeslaSetupController;
  mode: 'connect' | 'reconnect';
  initialEmail?: string;
  currentSiteId?: string | number | null;
  onClose?: () => void;
}

const button = 'px-6 py-2 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed';

/** Guided Tesla sign-in: Start, Sign in to Tesla, Finish connection, Choose site. */
export const TeslaSetupWizard: React.FC<TeslaSetupWizardProps> = ({
  controller, mode, initialEmail = '', currentSiteId, onClose,
}) => {
  const { state } = controller;
  const setup = state.setup;
  const [email, setEmail] = useState(initialEmail);
  const [emailError, setEmailError] = useState<string | null>(null);
  const [callbackText, setCallbackText] = useState('');
  const [showTokenImport, setShowTokenImport] = useState(false);
  const [refreshToken, setRefreshToken] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (initialEmail) setEmail((current) => current || initialEmail);
  }, [initialEmail]);

  const inAttempt = state.phase === 'attempt' && setup !== null;
  const counting = inAttempt && setup !== null && !['completing', 'complete'].includes(setup.step);
  const remaining = setup
    ? setup.setup_expires_in_seconds - Math.floor((now - state.receivedAt) / 1000)
    : 0;
  const { expire } = controller;

  useEffect(() => {
    if (!counting) return;
    setNow(Date.now());
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [counting]);

  useEffect(() => {
    if (counting && state.receivedAt > 0 && remaining <= 0) expire();
  }, [counting, remaining, state.receivedAt, expire]);

  const currentStep = inAttempt ? wizardStepFor(setup?.step, state.pasteStarted) : 1;
  const busy = state.busy;

  const handleStart = () => {
    setEmailError(null);
    if (!validateEmail(email)) {
      setEmailError('Please enter a valid email address');
      return;
    }
    setCallbackText('');
    // Must run inside the click so the new tab is not blocked
    void controller.start(email.trim());
  };

  const handleImport = () => {
    setEmailError(null);
    if (!validateEmail(email)) {
      setEmailError('Please enter a valid email address');
      return;
    }
    if (!refreshToken.trim() || !accessToken.trim()) {
      setEmailError('Paste both the refresh token and the access token');
      return;
    }
    void controller.importTokens(email.trim(), refreshToken.trim(), accessToken.trim());
    setRefreshToken('');
    setAccessToken('');
  };

  const handleCancel = () => {
    setCallbackText('');
    void controller.cancel();
    onClose?.();
  };

  const showSiteError = state.error && !(state.errorCode && SITE_ERRORS.has(state.errorCode));

  return (
    <div className="space-y-5">
      <ol className="flex flex-wrap gap-2 text-sm" aria-label="Tesla sign-in steps">
        {STEPS.map((label, index) => {
          const number = index + 1;
          const active = number === currentStep;
          const done = number < currentStep;
          return (
            <li
              key={label}
              aria-current={active ? 'step' : undefined}
              className={`flex items-center gap-2 px-3 py-1 rounded-full border ${
                active
                  ? 'border-blue-600 bg-blue-50 text-blue-800 font-medium'
                  : done
                    ? 'border-green-300 bg-green-50 text-green-800'
                    : 'border-gray-200 text-gray-500'
              }`}
            >
              <span aria-hidden="true">{done ? '✓' : number}</span>
              {label}
            </li>
          );
        })}
      </ol>

      {state.notice && (
        <div role="status" className="p-4 bg-yellow-50 border border-yellow-200 rounded-md text-sm text-yellow-800">
          {state.notice}
        </div>
      )}
      {state.phase === 'complete' && (
        <div role="status" className={`p-4 rounded-md text-sm border ${
          state.error ? 'bg-yellow-50 border-yellow-200 text-yellow-800' : 'bg-green-50 border-green-200 text-green-800'
        }`}>
          {state.error ?? 'Tesla account connected.'}
        </div>
      )}

      {!inAttempt && (
        <div className="space-y-4">
          {mode === 'reconnect' && (
            <p className="text-sm text-gray-700">
              Sign in to Tesla again to replace the stored sign-in. Your current connection stays active until the
              new sign-in is saved.
            </p>
          )}
          <div>
            <label htmlFor="email" className="block text-sm font-medium text-gray-700 mb-2">
              Tesla Account Email
            </label>
            <div className="flex flex-wrap gap-3">
              <input
                type="email"
                id="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="your-email@example.com"
                autoComplete="email"
                className="flex-1 min-w-0 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                type="button"
                onClick={handleStart}
                disabled={busy !== null}
                className={`${button} w-full sm:w-auto bg-blue-600 text-white hover:bg-blue-700`}
              >
                {busy === 'starting' ? 'Connecting...' : 'Connect'}
              </button>
              {mode === 'reconnect' && onClose && (
                <button
                  type="button"
                  onClick={onClose}
                  className={`${button} w-full sm:w-auto bg-gray-100 text-gray-800 hover:bg-gray-200`}
                >
                  Keep Current Sign-In
                </button>
              )}
            </div>
            <p className="text-xs text-gray-500 mt-2">
              Connect opens Tesla sign-in in a new tab. You then copy one line back here.
            </p>
          </div>
          {emailError && <p className="text-sm text-red-700">{emailError}</p>}
          {state.error && state.phase !== 'complete' && <p className="text-sm text-red-700">{state.error}</p>}

          <div>
            <button
              type="button"
              onClick={() => setShowTokenImport((value) => !value)}
              className="text-sm text-blue-700 hover:underline"
            >
              {showTokenImport ? 'Hide token import' : 'Or sign in with tokens from pypowerwall'}
            </button>
          </div>
          {showTokenImport && (
            <div className="space-y-3 p-4 bg-gray-50 border border-gray-200 rounded-md">
              <p className="text-sm text-gray-700">
                On a Mac or PC with a screen, run <code className="font-mono">pip install -U pypowerwall</code> and{' '}
                <code className="font-mono">python -m pypowerwall authtoken</code>, log in to Tesla, then paste
                both tokens here. The access token is only valid for about 8 hours, so paste it right away.
              </p>
              <div>
                <label htmlFor="refreshToken" className="block text-sm font-medium text-gray-700 mb-1">
                  Refresh Token
                </label>
                <textarea
                  id="refreshToken"
                  value={refreshToken}
                  onChange={(event) => setRefreshToken(event.target.value)}
                  rows={2}
                  autoComplete="off"
                  spellCheck={false}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md font-mono text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <div>
                <label htmlFor="accessToken" className="block text-sm font-medium text-gray-700 mb-1">
                  Access Token
                </label>
                <textarea
                  id="accessToken"
                  value={accessToken}
                  onChange={(event) => setAccessToken(event.target.value)}
                  rows={3}
                  autoComplete="off"
                  spellCheck={false}
                  className="w-full px-3 py-2 border border-gray-300 rounded-md font-mono text-xs focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              <button
                type="button"
                onClick={handleImport}
                disabled={busy !== null}
                className={`${button} bg-blue-600 text-white hover:bg-blue-700`}
              >
                {busy === 'importing' ? 'Saving...' : 'Save Tokens'}
              </button>
            </div>
          )}
        </div>
      )}

      {inAttempt && setup && (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-600">
            <span>
              Signing in as <span className="font-medium text-gray-900">{setup.email}</span>
            </span>
            {counting && <span aria-live="polite">Time left: {formatRemaining(remaining)}</span>}
          </div>

          {setup.step === 'awaiting_callback' && (
            <>
              <section className="space-y-3" aria-labelledby="tesla-sign-in-heading">
                <h3 id="tesla-sign-in-heading" className="text-lg font-medium text-gray-900">2. Sign in to Tesla</h3>
                {state.popupBlocked ? (
                  <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-md text-sm text-yellow-800 space-y-2">
                    <p>Your browser blocked the new tab. Open Tesla sign-in with this button instead:</p>
                    {setup.auth_url && (
                      <a
                        href={setup.auth_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-block bg-blue-600 text-white px-4 py-2 rounded-md hover:bg-blue-700"
                      >
                        Open Tesla sign-in
                      </a>
                    )}
                  </div>
                ) : (
                  <p className="text-sm text-gray-700">
                    Tesla sign-in opened in a new tab. Closed it by accident?{' '}
                    {setup.auth_url && (
                      <a href={setup.auth_url} target="_blank" rel="noopener noreferrer" className="text-blue-700 underline">
                        Open Tesla sign-in
                      </a>
                    )}
                  </p>
                )}
                {isMacOS(navigator.userAgent, navigator.maxTouchPoints) && setup.source === 'browser' && (
                  <MacHelperLauncher
                    helperState={setup.helper_state}
                    launchedAt={state.helperLaunchedAt}
                    launching={busy === 'launching'}
                    onLaunch={() => void controller.launchHelper()}
                  />
                )}
                <TeslaSignInHelp />
              </section>

              <section className="space-y-3" aria-labelledby="tesla-finish-heading">
                <h3 id="tesla-finish-heading" className="text-lg font-medium text-gray-900">3. Finish connection</h3>
                <label htmlFor="callbackUrl" className="block text-sm font-medium text-gray-700">
                  Tesla Callback Link
                </label>
                <div className="flex flex-wrap gap-3">
                  <input
                    type="text"
                    id="callbackUrl"
                    value={callbackText}
                    onChange={(event) => setCallbackText(event.target.value)}
                    onFocus={controller.notePasteStarted}
                    onPaste={(event) => {
                      const pasted = event.clipboardData.getData('text');
                      if (pasted) void controller.submitCallback(pasted);
                    }}
                    placeholder="tesla://auth/callback?code=...&state=... (or the whole console message)"
                    autoComplete="off"
                    spellCheck={false}
                    className="flex-1 min-w-0 px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                  <button
                    type="button"
                    onClick={() => void controller.submitCallback(callbackText)}
                    disabled={busy !== null}
                    className={`${button} w-full sm:w-auto bg-blue-600 text-white hover:bg-blue-700`}
                  >
                    {busy === 'verifying' ? 'Verifying...' : 'Verify'}
                  </button>
                </div>
                <p className="text-xs text-gray-500">Pasting checks the link automatically. Verify sends it again.</p>
                {state.hint && (
                  <div role="alert" className="p-3 bg-yellow-50 border border-yellow-200 rounded-md text-sm text-yellow-800">
                    {state.hint}
                  </div>
                )}
                {state.error && (
                  <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-800">
                    {state.error}
                  </div>
                )}
              </section>
            </>
          )}

          {WORKING_STEPS.has(setup.step) && (
            <p role="status" className="text-sm text-gray-700">
              {setup.step === 'exchanging' ? 'Finishing the Tesla sign-in...' : 'Loading your energy sites...'}
            </p>
          )}

          {SITE_STEPS.has(setup.step) && (
            <section className="space-y-3" aria-labelledby="tesla-site-heading">
              <h3 id="tesla-site-heading" className="text-lg font-medium text-gray-900">4. Choose site</h3>
              <TeslaSiteChooser
                sites={setup.sites}
                currentSiteId={currentSiteId}
                errorCode={state.errorCode}
                saving={busy === 'completing' || setup.step === 'completing'}
                retrying={busy === 'retrying'}
                onChoose={(siteId) => void controller.completeWithSite(siteId)}
                onRetry={() => void controller.retrySites()}
                onRestart={handleCancel}
              />
              {showSiteError && (
                <div role="alert" className="p-3 bg-red-50 border border-red-200 rounded-md text-sm text-red-800">
                  {state.error}
                </div>
              )}
            </section>
          )}

          <div>
            <button
              type="button"
              onClick={handleCancel}
              disabled={busy === 'completing' || setup.step === 'completing'}
              className={`${button} bg-gray-100 text-gray-800 hover:bg-gray-200`}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default TeslaSetupWizard;

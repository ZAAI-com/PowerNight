import { useCallback, useEffect, useMemo, useReducer, useRef } from 'react';
import type {
  TeslaSetupErrorCode,
  TeslaSetupProgress,
  TeslaSetupResponse,
} from '../types';
import teslaSetupApi, { type SetupApiResult } from '../utils/teslaSetupApi';
import {
  AUTHORIZATION_URL_HINT,
  buildHelperLaunchUrl,
  classifyPastedText,
  clearStoredSetup,
  isSetupExpired,
  loadStoredSetup,
  openHelperLink,
  saveStoredSetup,
} from '../utils/teslaSetup';
import { usePolling } from './usePolling';

const POLL_INTERVAL_MS = 2000;
const BUSY_STEPS = new Set(['exchanging', 'discovering_sites', 'completing']);
const ENDED_STEPS = new Set(['failed', 'cancelled', 'expired']);

export const SETUP_MESSAGES = {
  expired: 'Your Tesla sign-in attempt expired after 10 minutes. Start again.',
  cancelled: 'The Tesla sign-in attempt was cancelled.',
  notFound: 'PowerNight was restarted or this Tesla sign-in attempt is no longer available. Start again.',
  network: 'Failed to connect to server',
  rateLimited: 'Too many sign-in requests. Wait a minute and try again.',
  missingCallback:
    'Paste the tesla://auth/callback link (or the whole console message) that contains "code=" and "state=".',
} as const;

type Busy = 'starting' | 'verifying' | 'completing' | 'retrying' | 'importing' | 'cancelling' | 'launching' | null;

export interface TeslaSetupState {
  phase: 'idle' | 'attempt' | 'complete' | 'ended';
  setup: TeslaSetupProgress | null;
  /** When `setup` arrived (ms), to count down `setup_expires_in_seconds` without clock skew */
  receivedAt: number;
  busy: Busy;
  popupBlocked: boolean;
  pasteStarted: boolean;
  polling: boolean;
  error: string | null;
  errorCode: TeslaSetupErrorCode | null;
  hint: string | null;
  notice: string | null;
  helperLaunchedAt: number | null;
  /** Result of the last completion (connection status, saved site) */
  completion: TeslaSetupResponse | null;
}

type Action =
  | { type: 'busy'; busy: Busy }
  | { type: 'progress'; setup: TeslaSetupProgress; popupBlocked?: boolean }
  | { type: 'polling'; polling: boolean }
  | { type: 'error'; error: string; code?: TeslaSetupErrorCode | null }
  | { type: 'hint'; hint: string }
  | { type: 'pasteStarted' }
  | { type: 'helperLaunched' }
  | { type: 'completed'; setup: TeslaSetupProgress | null; completion: TeslaSetupResponse; warning?: string | null }
  | { type: 'ended'; notice: string; setup?: TeslaSetupProgress | null }
  | { type: 'reset'; notice?: string | null };

const initialState: TeslaSetupState = {
  phase: 'idle',
  setup: null,
  receivedAt: 0,
  busy: null,
  popupBlocked: false,
  pasteStarted: false,
  polling: false,
  error: null,
  errorCode: null,
  hint: null,
  notice: null,
  helperLaunchedAt: null,
  completion: null,
};

function reducer(state: TeslaSetupState, action: Action): TeslaSetupState {
  switch (action.type) {
    case 'busy':
      return { ...state, busy: action.busy, ...(action.busy ? { error: null, errorCode: null, hint: null } : {}) };
    case 'progress':
      return {
        ...state,
        phase: 'attempt',
        setup: action.setup,
        receivedAt: Date.now(),
        notice: null,
        popupBlocked: action.popupBlocked ?? state.popupBlocked,
        error: action.setup.error_code ? action.setup.error : state.error,
        errorCode: action.setup.error_code ?? state.errorCode,
      };
    case 'polling':
      return { ...state, polling: action.polling };
    case 'error':
      return { ...state, error: action.error, errorCode: action.code ?? null, hint: null };
    case 'hint':
      return { ...state, hint: action.hint, error: null, errorCode: null, pasteStarted: true };
    case 'pasteStarted':
      return state.pasteStarted ? state : { ...state, pasteStarted: true };
    case 'helperLaunched':
      return { ...state, helperLaunchedAt: Date.now() };
    case 'completed':
      return {
        ...initialState,
        phase: 'complete',
        setup: action.setup,
        completion: action.completion,
        error: action.warning ?? null,
      };
    case 'ended':
      return { ...initialState, phase: 'ended', notice: action.notice, setup: action.setup ?? null };
    case 'reset':
      return { ...initialState, notice: action.notice ?? null, phase: action.notice ? 'ended' : 'idle' };
    default:
      return state;
  }
}

/** Build progress from a legacy response body that predates the `setup` field. */
function progressFrom(
  body: TeslaSetupResponse,
  fallback: Partial<TeslaSetupProgress> & { session_id: string; email: string },
): TeslaSetupProgress {
  if (body.setup) return body.setup;
  return {
    step: 'selecting_site',
    source: 'browser',
    created_at: '',
    setup_expires_at: body.setup_expires_at ?? '',
    setup_expires_in_seconds: 600,
    auth_url: body.auth_url ?? null,
    token_expires_at: null,
    sites: body.sites ?? null,
    selected_site_id: null,
    error_code: null,
    error: null,
    credentials_saved: false,
    helper_state: 'none',
    ...fallback,
  };
}

function openPlaceholderTab(): Window | null {
  let tab: Window | null;
  try {
    tab = window.open('', '_blank');
  } catch {
    return null;
  }
  if (!tab) return null;
  try {
    // Tesla's page must not be able to reach back into PowerNight
    tab.opener = null;
  } catch {
    // Some browsers do not allow setting opener; the tab still works
  }
  try {
    tab.document.title = 'Opening Tesla sign-in';
    tab.document.body.textContent = 'Opening Tesla sign-in...';
  } catch {
    // Placeholder text is cosmetic
  }
  return tab;
}

function navigateTab(tab: Window, url: string): boolean {
  try {
    if (tab.closed) return false;
    tab.location.href = url;
    return true;
  } catch {
    return false;
  }
}

function endedNotice(code: TeslaSetupErrorCode | null | undefined, fallback?: string | null): string {
  if (code === 'SETUP_EXPIRED') return SETUP_MESSAGES.expired;
  if (code === 'SETUP_CANCELLED') return SETUP_MESSAGES.cancelled;
  if (code === 'SETUP_NOT_FOUND') return SETUP_MESSAGES.notFound;
  return fallback || SETUP_MESSAGES.notFound;
}

export interface UseTeslaSetupOptions {
  /** Called after credentials were saved (also when the live connection then failed). */
  onCompleted?: (result: TeslaSetupResponse) => void | Promise<void>;
}

/**
 * State machine for the Tesla sign-in wizard.
 *
 * Mutations only run from user actions, never from effects (React StrictMode
 * runs effects twice). Paste and the Verify button share one submit that is
 * deduplicated while in flight; the backend also deduplicates.
 */
export function useTeslaSetup({ onCompleted }: UseTeslaSetupOptions = {}) {
  const [state, dispatch] = useReducer(reducer, initialState);
  const setupRef = useRef<TeslaSetupProgress | null>(null);
  const busyRef = useRef(false);
  const inflight = useRef<{ key: string; promise: Promise<void> } | null>(null);
  // Exactly one site is picked automatically only after a fresh sign-in in
  // this tab, never when resuming after a reload
  const autoCompleteArmed = useRef(false);
  const onCompletedRef = useRef(onCompleted);

  useEffect(() => { onCompletedRef.current = onCompleted; }, [onCompleted]);
  useEffect(() => { setupRef.current = state.setup; }, [state.setup]);

  const applyProgress = useCallback((setup: TeslaSetupProgress, popupBlocked?: boolean) => {
    setupRef.current = setup;
    dispatch({ type: 'progress', setup, popupBlocked });
    dispatch({ type: 'polling', polling: BUSY_STEPS.has(setup.step) });
  }, []);

  const finishCompleted = useCallback(async (body: TeslaSetupResponse, setup: TeslaSetupProgress | null) => {
    clearStoredSetup();
    setupRef.current = null;
    autoCompleteArmed.current = false;
    const warning = body.success
      ? null
      : body.connection_error || body.message || 'Tesla credentials were saved, but the live connection failed.';
    dispatch({ type: 'completed', setup: setup ?? body.setup ?? null, completion: body, warning });
    await onCompletedRef.current?.(body);
  }, []);

  const endAttempt = useCallback((notice: string, setup?: TeslaSetupProgress | null) => {
    clearStoredSetup();
    setupRef.current = null;
    autoCompleteArmed.current = false;
    inflight.current = null;
    dispatch({ type: 'ended', notice, setup });
  }, []);

  /** Shared handling for error responses: keep progress in sync, end the attempt when it is over. */
  const handleFailure = useCallback((result: SetupApiResult<TeslaSetupResponse>, fallback: string) => {
    const { body, status } = result;
    if (status === 429) {
      dispatch({ type: 'error', error: SETUP_MESSAGES.rateLimited, code: 'RATE_LIMITED' });
      return;
    }
    const code = body.error_code ?? null;
    if (code === 'SETUP_EXPIRED' || code === 'SETUP_CANCELLED' || code === 'SETUP_NOT_FOUND'
        || (body.setup && ENDED_STEPS.has(body.setup.step))) {
      endAttempt(endedNotice(code, body.error), body.setup ?? null);
      return;
    }
    if (body.setup) applyProgress(body.setup);
    dispatch({ type: 'error', error: body.error || fallback, code });
  }, [applyProgress, endAttempt]);

  const runOnce = useCallback(async (key: string, work: () => Promise<void>) => {
    if (inflight.current?.key === key) return inflight.current.promise;
    const promise = work();
    inflight.current = { key, promise };
    try {
      await promise;
    } finally {
      if (inflight.current?.key === key) inflight.current = null;
    }
  }, []);

  const completeWithSite = useCallback(async (siteId: string) => {
    const setup = setupRef.current;
    if (!setup) return;
    await runOnce(`complete:${setup.session_id}:${siteId}`, async () => {
      dispatch({ type: 'busy', busy: 'completing' });
      try {
        const result = await teslaSetupApi.complete(setup.session_id, siteId);
        if (result.status === 202) {
          if (result.body.setup) applyProgress(result.body.setup);
          dispatch({ type: 'polling', polling: true });
        } else if (result.body.success || result.body.credentials_saved) {
          await finishCompleted(result.body, result.body.setup ?? { ...setup, step: 'complete', selected_site_id: siteId });
        } else {
          handleFailure(result, 'Failed to complete setup');
        }
      } catch {
        dispatch({ type: 'error', error: 'Failed to complete setup' });
      } finally {
        dispatch({ type: 'busy', busy: null });
      }
    });
  }, [applyProgress, finishCompleted, handleFailure, runOnce]);

  /** After a fresh sign-in, a single energy site is used automatically. */
  const maybeAutoComplete = useCallback(async (setup: TeslaSetupProgress) => {
    if (!autoCompleteArmed.current || setup.step !== 'selecting_site') return;
    autoCompleteArmed.current = false;
    if (setup.sites && setup.sites.length === 1) {
      await completeWithSite(String(setup.sites[0].id));
    }
  }, [completeWithSite]);

  const start = useCallback((email: string) => {
    if (busyRef.current) return Promise.resolve();
    // Open the tab synchronously inside the click, before any await, so
    // popup blockers treat it as user initiated
    const tab = openPlaceholderTab();
    busyRef.current = true;
    dispatch({ type: 'busy', busy: 'starting' });
    const previous = loadStoredSetup();
    if (previous) void teslaSetupApi.cancel(previous.session_id).catch(() => undefined);

    return (async () => {
      try {
        const result = await teslaSetupApi.start(email);
        const body = result.body;
        if (result.ok && body.success && body.session_id) {
          const setup = progressFrom(body, {
            session_id: body.session_id,
            email,
            step: 'awaiting_callback',
          });
          saveStoredSetup({ session_id: setup.session_id, email: setup.email, setup_expires_at: setup.setup_expires_at });
          const opened = tab !== null && !!setup.auth_url && navigateTab(tab, setup.auth_url);
          autoCompleteArmed.current = true;
          applyProgress(setup, !opened);
        } else {
          tab?.close();
          handleFailure(result, 'Failed to start authentication');
        }
      } catch {
        tab?.close();
        dispatch({ type: 'error', error: SETUP_MESSAGES.network });
      } finally {
        busyRef.current = false;
        dispatch({ type: 'busy', busy: null });
      }
    })();
  }, [applyProgress, handleFailure]);

  const submitCallback = useCallback(async (text: string) => {
    const setup = setupRef.current;
    if (!setup) return;
    dispatch({ type: 'pasteStarted' });
    const parsed = classifyPastedText(text);
    if (parsed.kind === 'authorization_url') {
      dispatch({ type: 'hint', hint: AUTHORIZATION_URL_HINT });
      return;
    }
    if (parsed.kind === 'tesla_error') {
      dispatch({
        type: 'error',
        error: `Tesla reported "${parsed.error}" instead of a sign-in result. Open Tesla sign-in and try again.`,
        code: 'TESLA_DENIED',
      });
      return;
    }
    if (parsed.kind !== 'callback') {
      dispatch({ type: 'error', error: SETUP_MESSAGES.missingCallback, code: 'INVALID_INPUT' });
      return;
    }

    await runOnce(`callback:${setup.session_id}:${parsed.code}`, async () => {
      dispatch({ type: 'busy', busy: 'verifying' });
      autoCompleteArmed.current = true;
      try {
        const result = await teslaSetupApi.submitCallback(setup.session_id, text.trim());
        if (result.status === 202) {
          if (result.body.setup) applyProgress(result.body.setup);
          dispatch({ type: 'polling', polling: true });
        } else if (result.ok && result.body.success) {
          const next = progressFrom(result.body, { session_id: setup.session_id, email: setup.email });
          applyProgress(next);
          dispatch({ type: 'busy', busy: null });
          await maybeAutoComplete(next);
        } else {
          handleFailure(result, 'Failed to verify callback URL');
        }
      } catch {
        dispatch({ type: 'error', error: SETUP_MESSAGES.network });
      } finally {
        dispatch({ type: 'busy', busy: null });
      }
    });
  }, [applyProgress, handleFailure, maybeAutoComplete, runOnce]);

  const importTokens = useCallback(async (email: string, refreshToken: string, accessToken: string) => {
    await runOnce(`import:${email}`, async () => {
      dispatch({ type: 'busy', busy: 'importing' });
      try {
        const result = await teslaSetupApi.importTokens(email, refreshToken, accessToken);
        const body = result.body;
        if (body.session_id && (body.success || body.setup)) {
          const setup = progressFrom(body, { session_id: body.session_id, email, source: 'token_import' });
          saveStoredSetup({ session_id: setup.session_id, email: setup.email, setup_expires_at: setup.setup_expires_at });
          autoCompleteArmed.current = true;
          applyProgress(setup);
          if (!body.success) {
            dispatch({ type: 'error', error: body.error || 'Failed to import tokens', code: body.error_code ?? null });
            return;
          }
          dispatch({ type: 'busy', busy: null });
          await maybeAutoComplete(setup);
        } else {
          handleFailure(result, 'Failed to import tokens');
        }
      } catch {
        dispatch({ type: 'error', error: SETUP_MESSAGES.network });
      } finally {
        dispatch({ type: 'busy', busy: null });
      }
    });
  }, [applyProgress, handleFailure, maybeAutoComplete, runOnce]);

  const retrySites = useCallback(async () => {
    const setup = setupRef.current;
    if (!setup) return;
    await runOnce(`sites:${setup.session_id}`, async () => {
      dispatch({ type: 'busy', busy: 'retrying' });
      try {
        const result = await teslaSetupApi.retrySites(setup.session_id);
        if (result.status === 202) {
          dispatch({ type: 'polling', polling: true });
        } else if (result.ok && result.body.success && result.body.setup) {
          applyProgress(result.body.setup);
        } else {
          handleFailure(result, 'Could not load your energy sites');
        }
      } catch {
        dispatch({ type: 'error', error: SETUP_MESSAGES.network });
      } finally {
        dispatch({ type: 'busy', busy: null });
      }
    });
  }, [applyProgress, handleFailure, runOnce]);

  /** Abandon the attempt. Stored credentials and the live connection are untouched. */
  const cancel = useCallback(async () => {
    const setup = setupRef.current ?? (() => {
      const stored = loadStoredSetup();
      return stored ? ({ session_id: stored.session_id } as TeslaSetupProgress) : null;
    })();
    clearStoredSetup();
    setupRef.current = null;
    autoCompleteArmed.current = false;
    inflight.current = null;
    dispatch({ type: 'reset' });
    if (setup) {
      try {
        await teslaSetupApi.cancel(setup.session_id);
      } catch {
        // The attempt expires on its own; nothing else depends on it
      }
    }
  }, []);

  /** Clear an ended or completed wizard back to the start step. */
  const dismiss = useCallback(() => {
    dispatch({ type: 'reset' });
  }, []);

  const expire = useCallback(() => {
    endAttempt(SETUP_MESSAGES.expired);
  }, [endAttempt]);

  /** Experimental: hand this attempt to the PowerNight Login Mac helper. */
  const launchHelper = useCallback(async () => {
    const setup = setupRef.current;
    if (!setup) return;
    await runOnce(`helper:${setup.session_id}`, async () => {
      dispatch({ type: 'busy', busy: 'launching' });
      try {
        const result = await teslaSetupApi.createHandoff(setup.session_id);
        if (result.ok && result.body.success && result.body.handoff) {
          if (result.body.setup) applyProgress(result.body.setup);
          autoCompleteArmed.current = true;
          dispatch({ type: 'helperLaunched' });
          dispatch({ type: 'polling', polling: true });
          openHelperLink(buildHelperLaunchUrl(window.location.origin, result.body.handoff));
        } else {
          handleFailure(result, 'Could not start the Mac helper');
        }
      } catch {
        dispatch({ type: 'error', error: SETUP_MESSAGES.network });
      } finally {
        dispatch({ type: 'busy', busy: null });
      }
    });
  }, [applyProgress, handleFailure, runOnce]);

  const pollingRef = useRef(state.polling);
  useEffect(() => { pollingRef.current = state.polling; }, [state.polling]);

  const poll = useCallback(async () => {
    const setup = setupRef.current;
    if (!pollingRef.current || !setup) return;
    const result = await teslaSetupApi.status(setup.session_id);
    const data = result.body.data;
    if (!result.ok || !data) return;
    if (!data.exists || !data.step) {
      endAttempt(endedNotice(data.error_code, data.error));
      return;
    }
    const next = data as TeslaSetupProgress;
    if (next.step === 'complete') {
      await finishCompleted({ success: true, setup: next, credentials_saved: true }, next);
      return;
    }
    applyProgress(next);
    // While the Mac helper is active, keep watching until it submits
    const helperWaiting = next.step === 'awaiting_callback'
      && (next.helper_state === 'pending' || next.helper_state === 'opened');
    dispatch({ type: 'polling', polling: BUSY_STEPS.has(next.step) || helperWaiting });
    await maybeAutoComplete(next);
  }, [applyProgress, endAttempt, finishCompleted, maybeAutoComplete]);

  usePolling(poll, state.polling ? POLL_INTERVAL_MS : 0);

  // Resume an attempt after a reload or after the app's own login screen.
  // Read-only: a status request, never a mutation.
  useEffect(() => {
    const stored = loadStoredSetup();
    if (!stored) return;
    let cancelled = false;
    (async () => {
      try {
        const result = await teslaSetupApi.status(stored.session_id);
        if (cancelled || result.status === 401) return;
        const data = result.body.data;
        if (result.ok && data?.exists && data.step) {
          const setup = data as TeslaSetupProgress;
          if (setup.step === 'complete') {
            clearStoredSetup();
            dispatch({ type: 'completed', setup, completion: { success: true, setup } });
            return;
          }
          setupRef.current = setup;
          dispatch({ type: 'progress', setup });
          dispatch({ type: 'polling', polling: BUSY_STEPS.has(setup.step) });
        } else if (result.ok) {
          clearStoredSetup();
          const code = data?.error_code === 'SETUP_NOT_FOUND' && isSetupExpired(stored.setup_expires_at)
            ? 'SETUP_EXPIRED'
            : data?.error_code;
          dispatch({ type: 'ended', notice: endedNotice(code, data?.error) });
        }
      } catch {
        // Keep the stored attempt; a later reload can still resume it
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const actions = useMemo(() => ({
    start,
    submitCallback,
    completeWithSite,
    retrySites,
    importTokens,
    cancel,
    dismiss,
    expire,
    launchHelper,
    notePasteStarted: () => dispatch({ type: 'pasteStarted' }),
  }), [start, submitCallback, completeWithSite, retrySites, importTokens, cancel, dismiss, expire, launchHelper]);

  return { state, ...actions };
}

export type TeslaSetupController = ReturnType<typeof useTeslaSetup>;

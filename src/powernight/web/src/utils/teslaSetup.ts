import type { StoredTeslaSetup, TeslaSetupStep } from '../types';

/**
 * Pure helpers for the Tesla sign-in wizard. The paste classifier mirrors
 * parse_callback_text in core/auth/setup_attempts.py; both are checked
 * against test/fixtures/tesla-callback-samples.json.
 */

export type PastedTextKind = 'callback' | 'authorization_url' | 'tesla_error' | 'unknown';

export interface PastedText {
  kind: PastedTextKind;
  code?: string;
  state?: string;
  error?: string;
}

export const AUTHORIZATION_URL_HINT =
  'This is the sign-in page, not the returned login result. ' +
  'The embedded redirect address does not contain your authorization code.';

const MAX_CALLBACK_TEXT = 8192;
// Values stop at separators, whitespace, quotes (including curly quotes some
// consoles print) and angle brackets
const STOP = '\\s\'"\u201c\u201d\u2018\u2019<>';
const CALLBACK_SEGMENT = new RegExp(`tesla://auth/callback(\\?[^${STOP}]*)`, 'g');
const PARAM = new RegExp(`[?&#](code|state|error)=([^&#${STOP}]+)`, 'g');
const AUTHORIZE_URL = /auth\.tesla\.(?:com|cn)\/oauth2\/v3\/authorize/i;
const CODE_PARAM = /[?&#]code=/;
const SAFE_ERROR = /^[A-Za-z0-9_.-]{1,64}$/;

function decode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function params(text: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const match of text.matchAll(PARAM)) {
    found[match[1]] = decode(match[2]);
  }
  return found;
}

function callbackSegments(text: string): string[] {
  return Array.from(text.matchAll(CALLBACK_SEGMENT), (match) => match[1]);
}

function isAuthorizationUrl(text: string): boolean {
  if (callbackSegments(text).length > 0) return false;
  return AUTHORIZE_URL.test(text) || (text.includes('code_challenge=') && !CODE_PARAM.test(text));
}

/** Classify pasted text before sending it: a callback result, the sign-in page, a Tesla error, or noise. */
export function classifyPastedText(text: string): PastedText {
  if (typeof text !== 'string' || !text.trim() || text.length > MAX_CALLBACK_TEXT) {
    return { kind: 'unknown' };
  }
  if (isAuthorizationUrl(text)) return { kind: 'authorization_url' };

  const segments = callbackSegments(text);
  const found = params(segments.length > 0 ? segments[segments.length - 1] : text);
  if (found.error) {
    return {
      kind: 'tesla_error',
      state: found.state,
      error: SAFE_ERROR.test(found.error) ? found.error : 'unknown_error',
    };
  }
  if (found.code && found.state) {
    return { kind: 'callback', code: found.code, state: found.state };
  }
  return { kind: 'unknown' };
}

export type HelpBrowser = 'chromium' | 'safari' | 'firefox' | 'other';

/** Pick the browser help tab to open first. Phones and tablets get the token-import advice. */
export function detectBrowser(userAgent: string): HelpBrowser {
  if (/Android|iPhone|iPad|iPod|Mobile/i.test(userAgent)) return 'other';
  if (/Firefox\//.test(userAgent)) return 'firefox';
  if (/Edg\/|Chrome\/|Chromium\//.test(userAgent)) return 'chromium';
  if (/Safari\//.test(userAgent) && /Version\//.test(userAgent)) return 'safari';
  return 'other';
}

/** A Mac desktop browser (iPads also report "Macintosh" but have touch points). */
export function isMacOS(userAgent: string, maxTouchPoints = 0): boolean {
  return /Macintosh|Mac OS X/.test(userAgent) && maxTouchPoints <= 1;
}

export const SETUP_STORAGE_KEY = 'powernight_tesla_setup';

function sessionStore(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/** Read the attempt to resume. Only the session ID, email and setup expiry are ever stored. */
export function loadStoredSetup(storage: Storage | null = sessionStore()): StoredTeslaSetup | null {
  try {
    const raw = storage?.getItem(SETUP_STORAGE_KEY);
    if (!raw) return null;
    const value: unknown = JSON.parse(raw);
    if (!value || typeof value !== 'object') return null;
    const { session_id, email, setup_expires_at } = value as Record<string, unknown>;
    if (typeof session_id !== 'string' || !session_id) return null;
    return {
      session_id,
      email: typeof email === 'string' ? email : '',
      setup_expires_at: typeof setup_expires_at === 'string' ? setup_expires_at : '',
    };
  } catch {
    return null;
  }
}

export function saveStoredSetup(setup: StoredTeslaSetup, storage: Storage | null = sessionStore()): void {
  try {
    storage?.setItem(SETUP_STORAGE_KEY, JSON.stringify({
      session_id: setup.session_id,
      email: setup.email,
      setup_expires_at: setup.setup_expires_at,
    }));
  } catch {
    // Storage can be disabled; resuming after a reload is then unavailable
  }
}

export function clearStoredSetup(storage: Storage | null = sessionStore()): void {
  try {
    storage?.removeItem(SETUP_STORAGE_KEY);
  } catch {
    // Nothing to clear
  }
}

export function isSetupExpired(setupExpiresAt: string, now: number = Date.now()): boolean {
  const deadline = Date.parse(setupExpiresAt);
  return Number.isFinite(deadline) && deadline <= now;
}

export type WizardStep = 1 | 2 | 3 | 4;

/** Which of Start, Sign in, Finish connection, Choose site an attempt is on. */
export function wizardStepFor(step: TeslaSetupStep | null | undefined, pasteStarted = false): WizardStep {
  switch (step) {
    case 'awaiting_callback':
      return pasteStarted ? 3 : 2;
    case 'exchanging':
    case 'discovering_sites':
      return 3;
    case 'selecting_site':
    case 'completing':
    case 'complete':
      return 4;
    default:
      return 1;
  }
}

export function formatRemaining(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${Math.floor(safe / 60)}:${String(safe % 60).padStart(2, '0')}`;
}

/** Launch link for the experimental Mac helper. Carries no API key or Tesla token. */
export function buildHelperLaunchUrl(origin: string, handoff: string): string {
  return `powernight-login://start?v=1&origin=${encodeURIComponent(origin)}&handoff=${encodeURIComponent(handoff)}`;
}

/** Hand the launch link to macOS. If the helper is not installed nothing visible happens. */
export function openHelperLink(url: string): void {
  window.location.assign(url);
}

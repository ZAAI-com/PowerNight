import { describe, expect, it } from 'vitest';
import samples from '../fixtures/tesla-callback-samples.json';
import {
  SETUP_STORAGE_KEY,
  buildHelperLaunchUrl,
  classifyPastedText,
  clearStoredSetup,
  detectBrowser,
  formatRemaining,
  isMacOS,
  isSetupExpired,
  loadStoredSetup,
  saveStoredSetup,
  wizardStepFor,
} from '../../src/utils/teslaSetup';

interface Sample {
  name: string;
  text: string;
  kind: string;
  code?: string;
  state?: string;
  error?: string;
}

describe('classifyPastedText', () => {
  // The same samples drive the backend parser test (test_tesla_setup_attempts.py)
  it.each(samples as Sample[])('$name', (sample) => {
    const parsed = classifyPastedText(sample.text);
    expect(parsed.kind).toBe(sample.kind);
    for (const field of ['code', 'state', 'error'] as const) {
      if (sample[field] !== undefined) expect(parsed[field]).toBe(sample[field]);
    }
  });

  it('rejects oversized input', () => {
    expect(classifyPastedText(`tesla://auth/callback?code=a&state=b${' '.repeat(9000)}`).kind).toBe('unknown');
  });
});

describe('detectBrowser', () => {
  it.each([
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36', 'chromium'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36 Edg/141.0', 'chromium'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15', 'safari'],
    ['Mozilla/5.0 (X11; Linux x86_64; rv:143.0) Gecko/20100101 Firefox/143.0', 'firefox'],
    ['Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 Version/26.0 Mobile Safari/604.1', 'other'],
    ['Mozilla/5.0 (Linux; Android 16) AppleWebKit/537.36 Chrome/141.0 Mobile Safari/537.36', 'other'],
  ])('%s -> %s', (userAgent, expected) => {
    expect(detectBrowser(userAgent)).toBe(expected);
  });
});

describe('isMacOS', () => {
  it('accepts desktop Macs and rejects iPads that report Macintosh', () => {
    const mac = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15';
    expect(isMacOS(mac, 0)).toBe(true);
    expect(isMacOS(mac, 5)).toBe(false);
    expect(isMacOS('Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 0)).toBe(false);
  });
});

describe('stored setup', () => {
  beforeEach(() => sessionStorage.clear());

  it('stores exactly the session ID, email and setup expiry', () => {
    saveStoredSetup({
      session_id: 'session-1',
      email: 'owner@example.com',
      setup_expires_at: '2026-10-21T12:10:00+00:00',
      // Anything else handed in must never be persisted
      ...({ callback_url: 'tesla://auth/callback?code=secret', access_token: 'secret' } as object),
    } as never);

    const raw = JSON.parse(sessionStorage.getItem(SETUP_STORAGE_KEY)!);
    expect(Object.keys(raw).sort()).toEqual(['email', 'session_id', 'setup_expires_at']);
    expect(loadStoredSetup()).toEqual({
      session_id: 'session-1',
      email: 'owner@example.com',
      setup_expires_at: '2026-10-21T12:10:00+00:00',
    });
  });

  it('ignores invalid stored data and clears it', () => {
    sessionStorage.setItem(SETUP_STORAGE_KEY, '{not json');
    expect(loadStoredSetup()).toBeNull();
    sessionStorage.setItem(SETUP_STORAGE_KEY, JSON.stringify({ email: 'x' }));
    expect(loadStoredSetup()).toBeNull();
    clearStoredSetup();
    expect(sessionStorage.getItem(SETUP_STORAGE_KEY)).toBeNull();
  });
});

describe('small helpers', () => {
  it('detects expired setup deadlines', () => {
    const now = Date.parse('2026-10-21T12:00:00Z');
    expect(isSetupExpired('2026-10-21T11:59:59Z', now)).toBe(true);
    expect(isSetupExpired('2026-10-21T12:05:00Z', now)).toBe(false);
    expect(isSetupExpired('', now)).toBe(false);
  });

  it('maps attempt steps to wizard steps', () => {
    expect(wizardStepFor(null)).toBe(1);
    expect(wizardStepFor('awaiting_callback')).toBe(2);
    expect(wizardStepFor('awaiting_callback', true)).toBe(3);
    expect(wizardStepFor('exchanging')).toBe(3);
    expect(wizardStepFor('selecting_site')).toBe(4);
  });

  it('formats the countdown', () => {
    expect(formatRemaining(599.9)).toBe('9:59');
    expect(formatRemaining(-5)).toBe('0:00');
  });

  it('builds a helper link that carries only origin and handoff', () => {
    expect(buildHelperLaunchUrl('https://nas.local:8020', 'hand/off')).toBe(
      'powernight-login://start?v=1&origin=https%3A%2F%2Fnas.local%3A8020&handoff=hand%2Foff',
    );
  });
});

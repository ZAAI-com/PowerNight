import { test, expect, type Page } from '@playwright/test';

/*
 * The Tesla sign-in wizard against a stateful fake backend. The authorize
 * URL points at a local stub page, so no test ever talks to Tesla.
 */

const API_KEY = 'valid-app-key';
const EMAIL = 'owner@example.com';
const SESSION = 'session-abcdefghijklmnopqrstuvwxyz0123';
const STUB_URL = 'http://localhost:3000/__tesla_stub/oauth2/v3/authorize?client_id=ownerapi&state=st-1&code_challenge=xyz';
const CALLBACK = 'tesla://auth/callback?code=code-1&state=st-1';
const CONSOLE_LINE = `Failed to launch '${CALLBACK}' because the scheme does not have a registered handler.`;
const HOME = { id: 111, name: 'Home', type: 'battery', state: 'online' };
const CABIN = { id: 333, name: 'Cabin', type: 'battery', state: 'online' };

interface FakeTesla {
  authenticated: boolean;
  step: string;
  sites: typeof HOME[] | null;
  expiresIn: number;
  calls: Record<string, number>;
  siteResults: (typeof HOME[])[];
}

function progress(state: FakeTesla) {
  return {
    session_id: SESSION,
    step: state.step,
    source: 'browser',
    email: EMAIL,
    created_at: '2026-10-21T12:00:00+00:00',
    setup_expires_at: '2099-01-01T00:00:00+00:00',
    setup_expires_in_seconds: state.expiresIn,
    auth_url: state.step === 'awaiting_callback' ? STUB_URL : null,
    token_expires_at: null,
    sites: state.sites,
    selected_site_id: null,
    error_code: state.sites && state.sites.length === 0 ? 'NO_ENERGY_SITES' : null,
    error: state.sites && state.sites.length === 0 ? 'No energy sites' : null,
    credentials_saved: state.step === 'complete',
    helper_state: 'none',
  };
}

async function fakeBackend(page: Page, authEnabled: boolean, overrides: Partial<FakeTesla> = {}) {
  const state: FakeTesla = {
    authenticated: false,
    step: 'awaiting_callback',
    sites: null,
    expiresIn: 600,
    calls: {},
    siteResults: [[HOME, CABIN]],
    ...overrides,
  };
  if (authEnabled) {
    await page.addInitScript((key) => localStorage.setItem('powernight_api_key', key), API_KEY);
  }
  await page.context().route('**/__tesla_stub/**', (route) =>
    route.fulfill({ contentType: 'text/html', body: '<html><body>Tesla sign-in stub</body></html>' }));

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    state.calls[path] = (state.calls[path] ?? 0) + 1;
    if (authEnabled && request.headers()['x-api-key'] !== API_KEY) {
      await route.fulfill({ status: 401, json: { success: false, error: 'Authentication required' } });
      return;
    }
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });

    if (path === '/api/auth/tesla/info') {
      return json({ success: true, data: state.authenticated
        ? { authenticated: true, email: EMAIL, site_id: 333, connected: true, connection_state: 'connected' }
        : { authenticated: false, connection_state: 'sign_in_required' } });
    }
    if (path === '/api/auth/setup/start') {
      state.step = 'awaiting_callback';
      state.sites = null;
      return json({ success: true, auth_url: STUB_URL, session_id: SESSION, setup_expires_at: '2099-01-01T00:00:00+00:00', setup: progress(state) });
    }
    if (path === '/api/auth/setup/callback') {
      const body = request.postDataJSON() as { callback_url: string };
      if (!body.callback_url.includes('state=st-1')) {
        return json({ success: false, error_code: 'STATE_MISMATCH', error: 'Invalid state parameter', setup: progress(state) }, 400);
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
      state.step = 'selecting_site';
      state.sites = state.siteResults.shift() ?? [HOME, CABIN];
      return json({ success: true, sites: state.sites, setup: progress(state) });
    }
    if (path === '/api/auth/setup/sites') {
      state.sites = state.siteResults.shift() ?? [HOME, CABIN];
      return json({ success: true, sites: state.sites, setup: progress(state) });
    }
    if (path === '/api/auth/setup/complete') {
      state.step = 'complete';
      state.authenticated = true;
      return json({ success: true, credentials_saved: true, connected: true, connection_state: 'connected', setup: progress(state) });
    }
    if (path === '/api/auth/setup/cancel') {
      state.step = 'cancelled';
      return json({ success: true, setup: progress(state) });
    }
    if (path.startsWith('/api/auth/setup/status/')) {
      return json({ success: true, data: { exists: state.step !== 'cancelled', ...progress(state) } });
    }
    if (path === '/api/auth/site-details') {
      return json({ success: false, code: 'TESLA_AUTH_REQUIRED', message: 'Connect or reconnect your Tesla account in Settings.' }, 503);
    }
    if (path === '/api/v1/config/timezone') {
      return json({ success: true, data: { timezone: 'UTC', offset: '+00:00', name: 'UTC', current_time: null } });
    }
    if (path === '/api/v1/config/timezones') return json({ success: true, data: { timezones: [] } });
    if (path === '/api/v1/version-info.json') {
      return json({ application: 'PowerNight', version: '2.1.0', build_timestamp: '', python_version: '3.14',
        node_version: '26', npm_version: '11', backend_dependencies: {}, frontend_dependencies: {} });
    }
    return json({ success: true });
  });
  return state;
}

async function paste(page: Page, text: string, browserName: string) {
  const input = page.getByLabel('Tesla Callback Link');
  if (browserName === 'firefox') {
    // Firefox drops clipboardData on script-created paste events (real pastes
    // work), so use the Verify button there; vitest covers the paste handler
    await input.fill(text);
    await page.getByRole('button', { name: 'Verify', exact: true }).click();
    return;
  }
  await input.evaluate((element, value) => {
    const data = new DataTransfer();
    data.setData('text', value);
    element.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }));
  }, text);
}

async function startSignIn(page: Page) {
  await page.goto('/settings');
  await page.getByLabel('Tesla Account Email', { exact: true }).fill(EMAIL);
  const popup = page.waitForEvent('popup');
  await page.getByRole('button', { name: 'Connect', exact: true }).click();
  return popup;
}

for (const authEnabled of [false, true]) {
  test.describe(`Tesla sign-in wizard with web auth ${authEnabled ? 'enabled' : 'disabled'}`, () => {
    test('signs in through the popup, verifies one paste, and saves the chosen site', async ({ page, browserName }) => {
      const state = await fakeBackend(page, authEnabled);
      const popup = await startSignIn(page);
      await expect.poll(() => popup.url()).toContain('/__tesla_stub/oauth2/v3/authorize');
      expect(await popup.evaluate(() => window.opener)).toBeNull();

      await paste(page, CONSOLE_LINE, browserName);
      await page.getByLabel('Tesla Callback Link').fill(CONSOLE_LINE);
      // A quick Verify click while the paste is still being checked must not send it again
      await page.getByRole('button', { name: /Verify/ }).click({ force: true, timeout: 1000 }).catch(() => undefined);

      await page.getByRole('radio', { name: /Cabin/ }).check();
      expect(state.calls['/api/auth/setup/callback']).toBe(1);
      await page.getByRole('button', { name: 'Use This Site' }).click();

      await expect(page.getByRole('status').filter({ hasText: /^Connected$/ })).toBeVisible();
      await expect(page.getByRole('cell', { name: 'Cabin' })).toBeVisible();
      expect(await page.evaluate(() => sessionStorage.getItem('powernight_tesla_setup'))).toBeNull();
    });

    test('offers a link for the same attempt when the popup is blocked', async ({ page }) => {
      const state = await fakeBackend(page, authEnabled);
      await page.addInitScript(() => { window.open = () => null; });
      await page.goto('/settings');
      await page.getByLabel('Tesla Account Email', { exact: true }).fill(EMAIL);
      await page.getByRole('button', { name: 'Connect', exact: true }).click();

      await expect(page.getByText('Your browser blocked the new tab')).toBeVisible();
      await expect(page.getByRole('link', { name: 'Open Tesla sign-in' }).first()).toHaveAttribute('href', STUB_URL);
      expect(state.calls['/api/auth/setup/start']).toBe(1);
    });

    test('explains a pasted sign-in page URL', async ({ page, browserName }) => {
      const state = await fakeBackend(page, authEnabled);
      await startSignIn(page);
      await paste(page, STUB_URL.replace('localhost:3000/__tesla_stub', 'auth.tesla.com'), browserName);

      await expect(page.getByText('This is the sign-in page, not the returned login result.', { exact: false })).toBeVisible();
      expect(state.calls['/api/auth/setup/callback'] ?? 0).toBe(0);
    });

    test('resumes after a reload and can be cancelled', async ({ page }) => {
      const state = await fakeBackend(page, authEnabled);
      await startSignIn(page);
      await page.reload();

      await expect(page.getByLabel('Tesla Callback Link')).toBeVisible();
      expect(state.calls['/api/auth/setup/start']).toBe(1);
      await page.getByRole('button', { name: 'Cancel', exact: true }).click();
      await expect.poll(() => state.calls['/api/auth/setup/cancel'] ?? 0).toBe(1);
      await expect(page.getByRole('button', { name: 'Connect', exact: true })).toBeVisible();
    });

    test('ends the attempt after ten minutes', async ({ page }) => {
      await page.clock.install();
      await fakeBackend(page, authEnabled);
      await startSignIn(page);
      await expect(page.getByLabel('Tesla Callback Link')).toBeVisible();

      await page.clock.fastForward('10:01');

      await expect(page.getByText(/expired after 10 minutes/)).toBeVisible();
    });

    test('guides through zero sites and uses a single site automatically', async ({ page, browserName }) => {
      const state = await fakeBackend(page, authEnabled, { siteResults: [[], [HOME]] });
      await startSignIn(page);
      await paste(page, CALLBACK, browserName);

      await expect(page.getByText('No Powerwall energy sites were found for this Tesla account.')).toBeVisible();
      await page.getByRole('button', { name: 'Retry Finding Sites' }).click();
      await expect(page.getByRole('button', { name: 'Use This Site' })).toBeVisible();
      expect(state.calls['/api/auth/setup/complete'] ?? 0).toBe(0);
    });

    test('reconnects without signing out', async ({ page, browserName }) => {
      const state = await fakeBackend(page, authEnabled, { authenticated: true });
      await page.goto('/settings');
      await expect(page.getByRole('status').filter({ hasText: /^Connected$/ })).toBeVisible();

      await page.getByRole('button', { name: 'Reconnect Tesla' }).click();
      await expect(page.getByLabel('Tesla Account Email', { exact: true })).toHaveValue(EMAIL);
      const popup = page.waitForEvent('popup');
      await page.getByRole('button', { name: 'Connect', exact: true }).click();
      await popup;
      await paste(page, CALLBACK, browserName);
      await page.getByRole('radio', { name: /Home/ }).check();
      await page.getByRole('button', { name: 'Use This Site' }).click();

      await expect(page.getByLabel('Tesla Callback Link')).toHaveCount(0);
      expect(state.calls['/api/auth/tesla/logout'] ?? 0).toBe(0);
      expect(state.calls['/api/auth/setup/complete']).toBe(1);
    });
  });
}

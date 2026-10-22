import React from 'react';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import Settings from '../../src/pages/Settings';
import { MacHelperLauncher } from '../../src/components/tesla/MacHelperLauncher';
import { TeslaSignInHelp } from '../../src/components/tesla/TeslaSignInHelp';
import { resolveHelpVisual } from '../../src/components/tesla/help/helpVisual';
import api from '../../src/utils/api';
import { openHelperLink } from '../../src/utils/teslaSetup';
import type { TeslaSetupProgress } from '../../src/types';

vi.mock('../../src/contexts/TimezoneContext', () => ({
  useTimezone: () => ({
    timezoneInfo: { timezone: 'UTC' },
    currentTime: '2026-10-21 12:00:00 UTC',
    isLoading: false,
    refreshTimezone: vi.fn(),
  }),
}));

vi.mock('../../src/contexts/ToastContext', () => ({
  useToast: () => ({ showToast: vi.fn() }),
}));

vi.mock('../../src/utils/api', () => ({
  default: {
    authenticatedFetch: vi.fn(),
    getAvailableTimezones: vi.fn(),
    getTimezone: vi.fn(),
    updateTimezone: vi.fn(),
    reloadAllTasks: vi.fn(),
  },
}));

vi.mock('../../src/utils/teslaSetup', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../src/utils/teslaSetup')>()),
  openHelperLink: vi.fn(),
}));

const authenticatedFetch = vi.mocked(api.authenticatedFetch);
const EMAIL = 'owner@example.com';
const SESSION = 'session-abcdefghijklmnopqrstuvwxyz0123';
const AUTH_URL = 'https://auth.tesla.com/oauth2/v3/authorize?client_id=ownerapi&state=st-1&code_challenge=xyz';
const CALLBACK = 'tesla://auth/callback?code=code-1&state=st-1';
const CONSOLE_LINE = `Failed to launch '${CALLBACK}' because the scheme does not have a registered handler.`;
const STORAGE_KEY = 'powernight_tesla_setup';
const HOME = { id: 111, name: 'Home', type: 'battery', state: 'online' };
const CABIN = { id: 333, name: 'Cabin', type: 'battery', state: 'online' };

type Handler = (init?: RequestInit) => Response | Promise<Response>;

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status });
}

function progress(overrides: Partial<TeslaSetupProgress> = {}): TeslaSetupProgress {
  return {
    session_id: SESSION,
    step: 'awaiting_callback',
    source: 'browser',
    email: EMAIL,
    created_at: '2026-10-21T12:00:00+00:00',
    setup_expires_at: '2026-10-21T12:10:00+00:00',
    setup_expires_in_seconds: 600,
    auth_url: AUTH_URL,
    token_expires_at: null,
    sites: null,
    selected_site_id: null,
    error_code: null,
    error: null,
    credentials_saved: false,
    helper_state: 'none',
    ...overrides,
  };
}

function startResponse(overrides: Partial<TeslaSetupProgress> = {}): Response {
  const setup = progress(overrides);
  return respond({
    success: true,
    auth_url: setup.auth_url,
    session_id: setup.session_id,
    setup_expires_at: setup.setup_expires_at,
    setup,
  });
}

function signedInResponse(sites: typeof HOME[], extra: Partial<TeslaSetupProgress> = {}): Response {
  const setup = progress({ step: 'selecting_site', auth_url: null, sites, ...extra });
  return respond({ success: true, sites, setup });
}

let authInfo: Record<string, unknown> = { authenticated: false, connection_state: 'sign_in_required' };

function backend(routes: Record<string, Handler>) {
  authenticatedFetch.mockImplementation(async (input, init) => {
    const url = input.toString();
    const match = Object.keys(routes).find((path) => url.startsWith(path));
    if (match) return routes[match](init);
    if (url.endsWith('/api/auth/tesla/info')) return respond({ success: true, data: authInfo });
    return respond({ application: 'PowerNight', version: '2.1.0', backend_dependencies: {}, frontend_dependencies: {} });
  });
}

function callsTo(path: string) {
  return authenticatedFetch.mock.calls.filter(([input]) => input.toString().startsWith(path));
}

function fakeTab() {
  return {
    opener: {} as unknown,
    closed: false,
    location: { href: '' },
    document: { title: '', body: { textContent: '' } },
    close: vi.fn(),
  };
}

async function startSignIn(tab: ReturnType<typeof fakeTab> | null = fakeTab()) {
  vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
  fireEvent.change(await screen.findByLabelText('Tesla Account Email'), { target: { value: EMAIL } });
  fireEvent.click(screen.getByRole('button', { name: 'Connect' }));
  return screen.findByLabelText('Tesla Callback Link');
}

function paste(input: HTMLElement, text: string) {
  fireEvent.paste(input, { clipboardData: { getData: () => text } });
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  sessionStorage.clear();
  localStorage.clear();
  authInfo = { authenticated: false, connection_state: 'sign_in_required' };
  vi.mocked(api.getTimezone).mockResolvedValue({ timezone: 'UTC', offset: '+00:00', name: 'UTC', current_time: null });
  vi.mocked(api.getAvailableTimezones).mockResolvedValue({ timezones: [], count: 0 });
});

afterEach(() => {
  vi.useRealTimers();
});

describe('Start and the Tesla tab', () => {
  it('opens the tab inside the click, before the start request resolves, and isolates it', async () => {
    let resolveStart: (response: Response) => void = () => undefined;
    backend({ '/api/auth/setup/start': () => new Promise<Response>((resolve) => { resolveStart = resolve; }) });
    const tab = fakeTab();
    const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    render(<Settings />);

    fireEvent.change(await screen.findByLabelText('Tesla Account Email'), { target: { value: EMAIL } });
    fireEvent.click(screen.getByRole('button', { name: 'Connect' }));

    expect(open).toHaveBeenCalledWith('', '_blank');
    expect(tab.opener).toBeNull();
    expect(tab.location.href).toBe('');

    await act(async () => resolveStart(startResponse()));

    await waitFor(() => expect(tab.location.href).toBe(AUTH_URL));
    expect(JSON.parse(sessionStorage.getItem(STORAGE_KEY)!)).toEqual({
      session_id: SESSION,
      email: EMAIL,
      setup_expires_at: '2026-10-21T12:10:00+00:00',
    });
    expect(screen.getByText('Tesla sign-in opened in a new tab.', { exact: false })).toBeInTheDocument();
  });

  it('offers a link for the same attempt when the popup is blocked', async () => {
    backend({ '/api/auth/setup/start': () => startResponse() });
    render(<Settings />);

    await startSignIn(null);

    expect(screen.getByText(/Your browser blocked the new tab/)).toBeInTheDocument();
    const links = screen.getAllByRole('link', { name: 'Open Tesla sign-in' });
    expect(links[0]).toHaveAttribute('href', AUTH_URL);
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer');
    expect(callsTo('/api/auth/setup/start')).toHaveLength(1);
  });

  it('closes the placeholder tab when the attempt cannot start', async () => {
    backend({ '/api/auth/setup/start': () => respond({ success: false, error: 'Internal server error' }, 500) });
    const tab = fakeTab();
    vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
    render(<Settings />);

    fireEvent.change(await screen.findByLabelText('Tesla Account Email'), { target: { value: EMAIL } });
    fireEvent.click(screen.getByRole('button', { name: 'Connect' }));

    await waitFor(() => expect(tab.close).toHaveBeenCalled());
    expect(await screen.findByText('Internal server error')).toBeInTheDocument();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

describe('Finish connection', () => {
  it('explains a pasted sign-in page URL without sending it', async () => {
    backend({ '/api/auth/setup/start': () => startResponse() });
    render(<Settings />);
    const input = await startSignIn();

    paste(input, AUTH_URL);

    expect(await screen.findByText(/This is the sign-in page, not the returned login result/)).toBeInTheDocument();
    expect(callsTo('/api/auth/setup/callback')).toHaveLength(0);
  });

  it('verifies a pasted console message once, even when Verify is clicked too', async () => {
    let resolveCallback: (response: Response) => void = () => undefined;
    backend({
      '/api/auth/setup/start': () => startResponse(),
      '/api/auth/setup/callback': () => new Promise<Response>((resolve) => { resolveCallback = resolve; }),
    });
    render(<Settings />);
    const input = await startSignIn();

    paste(input, CONSOLE_LINE);
    fireEvent.change(input, { target: { value: CONSOLE_LINE } });
    fireEvent.click(screen.getByRole('button', { name: /Verify/ }));
    paste(input, CONSOLE_LINE);

    expect(callsTo('/api/auth/setup/callback')).toHaveLength(1);
    expect(JSON.parse(callsTo('/api/auth/setup/callback')[0][1]!.body as string)).toEqual({
      session_id: SESSION,
      callback_url: CONSOLE_LINE,
    });

    await act(async () => resolveCallback(signedInResponse([HOME, CABIN])));
    expect(await screen.findByRole('radio', { name: /Cabin/ })).toBeInTheDocument();
    const stored = Object.keys(sessionStorage).map((key) => sessionStorage.getItem(key)).join('\n');
    expect(stored).toContain(SESSION);
    expect(stored).not.toContain('code-1');
    expect(localStorage.setItem).not.toHaveBeenCalledWith(expect.anything(), expect.stringContaining('code-1'));
  });

  it('polls status while another request finishes the exchange', async () => {
    let statusCalls = 0;
    backend({
      '/api/auth/setup/start': () => startResponse(),
      '/api/auth/setup/callback': () => respond({ success: true, in_progress: true, setup: progress({ step: 'exchanging', auth_url: null }) }, 202),
      '/api/auth/setup/status/': () => {
        statusCalls += 1;
        return respond({ success: true, data: { exists: true, ...progress({ step: 'selecting_site', auth_url: null, sites: [HOME, CABIN] }) } });
      },
    });
    render(<Settings />);
    paste(await startSignIn(), CALLBACK);

    expect(await screen.findByRole('radio', { name: /Home/ }, { timeout: 5000 })).toBeInTheDocument();
    expect(statusCalls).toBeGreaterThanOrEqual(1);
  });

  it('shows a Tesla error without sending it', async () => {
    backend({ '/api/auth/setup/start': () => startResponse() });
    render(<Settings />);
    paste(await startSignIn(), 'tesla://auth/callback?error=login_cancelled&state=st-1');

    expect(await screen.findByText(/Tesla reported "login_cancelled"/)).toBeInTheDocument();
    expect(callsTo('/api/auth/setup/callback')).toHaveLength(0);
  });
});

describe('Choose site', () => {
  it('uses the only site automatically after a fresh sign-in', async () => {
    backend({
      '/api/auth/setup/start': () => startResponse(),
      '/api/auth/setup/callback': () => signedInResponse([HOME]),
      '/api/auth/setup/complete': () => respond({ success: true, credentials_saved: true, setup: progress({ step: 'complete', auth_url: null, sites: [HOME] }) }),
    });
    render(<Settings />);
    paste(await startSignIn(), CALLBACK);

    await waitFor(() => expect(callsTo('/api/auth/setup/complete')).toHaveLength(1));
    expect(JSON.parse(callsTo('/api/auth/setup/complete')[0][1]!.body as string)).toEqual({
      session_id: SESSION,
      site_id: '111',
    });
    await waitFor(() => expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull());
  });

  it('requires an explicit choice between several sites and marks the saved one by ID', async () => {
    backend({
      '/api/auth/setup/start': () => startResponse(),
      '/api/auth/setup/callback': () => signedInResponse([HOME, CABIN]),
      '/api/auth/setup/complete': () => {
        authInfo = { authenticated: true, email: EMAIL, site_id: '333', connected: true, connection_state: 'connected' };
        return respond({ success: true, credentials_saved: true, setup: progress({ step: 'complete', auth_url: null, sites: [HOME, CABIN] }) });
      },
    });
    render(<Settings />);
    paste(await startSignIn(), CALLBACK);

    const use = await screen.findByRole('button', { name: 'Use This Site' });
    expect(use).toBeDisabled();
    expect(callsTo('/api/auth/setup/complete')).toHaveLength(0);
    fireEvent.click(screen.getByRole('radio', { name: /Cabin/ }));
    fireEvent.click(use);

    await waitFor(() => expect(callsTo('/api/auth/setup/complete')).toHaveLength(1));
    expect(JSON.parse(callsTo('/api/auth/setup/complete')[0][1]!.body as string).site_id).toBe('333');
    const table = await screen.findByRole('table');
    const cabinRow = within(table).getByText('Cabin').closest('tr')!;
    const homeRow = within(table).getByText('Home').closest('tr')!;
    expect(within(cabinRow).getByText('Selected')).toBeInTheDocument();
    expect(within(homeRow).queryByText('Selected')).not.toBeInTheDocument();
  });

  it('guides the user when no energy site is found and retries discovery', async () => {
    backend({
      '/api/auth/setup/start': () => startResponse(),
      '/api/auth/setup/callback': () => signedInResponse([], { error_code: 'NO_ENERGY_SITES', error: 'No sites' }),
      '/api/auth/setup/sites': () => signedInResponse([HOME, CABIN]),
    });
    render(<Settings />);
    paste(await startSignIn(), CALLBACK);

    expect(await screen.findByText('No Powerwall energy sites were found for this Tesla account.')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry Finding Sites' }));

    await waitFor(() => expect(callsTo('/api/auth/setup/sites')).toHaveLength(1));
    expect(await screen.findByRole('radio', { name: /Home/ })).toBeInTheDocument();
  });
});

describe('Resume, cancel and expiry', () => {
  function storeAttempt(expiresAt = '2099-01-01T00:00:00+00:00') {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ session_id: SESSION, email: EMAIL, setup_expires_at: expiresAt }));
  }

  it('resumes after a reload from the status endpoint without starting again', async () => {
    storeAttempt();
    backend({
      '/api/auth/setup/status/': () => respond({ success: true, data: { exists: true, ...progress() } }),
      '/api/auth/setup/start': () => startResponse(),
    });
    const open = vi.spyOn(window, 'open');
    render(<Settings />);

    expect(await screen.findByLabelText('Tesla Callback Link')).toBeInTheDocument();
    expect(screen.getAllByRole('link', { name: 'Open Tesla sign-in' })[0]).toHaveAttribute('href', AUTH_URL);
    expect(callsTo('/api/auth/setup/start')).toHaveLength(0);
    expect(open).not.toHaveBeenCalled();
  });

  it('never posts anything while mounting in StrictMode', async () => {
    storeAttempt();
    backend({ '/api/auth/setup/status/': () => respond({ success: true, data: { exists: true, ...progress() } }) });
    render(<React.StrictMode><Settings /></React.StrictMode>);

    await screen.findByLabelText('Tesla Callback Link');
    const posts = authenticatedFetch.mock.calls.filter(([, init]) => init?.method === 'POST');
    expect(posts).toHaveLength(0);
  });

  it('explains an expired attempt that the server no longer knows', async () => {
    storeAttempt('2020-01-01T00:00:00+00:00');
    backend({
      '/api/auth/setup/status/': () => respond({ success: true, data: { exists: false, step: null, error_code: 'SETUP_NOT_FOUND', error: 'gone' } }),
    });
    render(<Settings />);

    expect(await screen.findByText(/expired after 10 minutes/)).toBeInTheDocument();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('explains a restart when the server lost an attempt that had not expired', async () => {
    storeAttempt();
    backend({
      '/api/auth/setup/status/': () => respond({ success: true, data: { exists: false, step: null, error_code: 'SETUP_NOT_FOUND', error: 'gone' } }),
    });
    render(<Settings />);

    expect(await screen.findByText(/PowerNight was restarted/)).toBeInTheDocument();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });

  it('cancels the attempt on the server and forgets it', async () => {
    backend({
      '/api/auth/setup/start': () => startResponse(),
      '/api/auth/setup/cancel': () => respond({ success: true, setup: progress({ step: 'cancelled' }) }),
    });
    render(<Settings />);
    await startSignIn();

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    await waitFor(() => expect(callsTo('/api/auth/setup/cancel')).toHaveLength(1));
    expect(JSON.parse(callsTo('/api/auth/setup/cancel')[0][1]!.body as string)).toEqual({ session_id: SESSION });
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
    expect(await screen.findByRole('button', { name: 'Connect' })).toBeInTheDocument();
  });

  it('ends the attempt when its ten minutes run out', async () => {
    backend({ '/api/auth/setup/start': () => startResponse({ setup_expires_in_seconds: 1 }) });
    render(<Settings />);
    await startSignIn();

    expect(await screen.findByText(/expired after 10 minutes/, {}, { timeout: 4000 })).toBeInTheDocument();
    expect(sessionStorage.getItem(STORAGE_KEY)).toBeNull();
  });
});

describe('Connection state and Reconnect', () => {
  it.each([
    {
      info: { connected: true, connection_state: 'connected', connection_state_reason: 'connected' },
      badge: 'Connected',
      text: 'PowerNight is connected to your Tesla account.',
      first: 'Test Connection',
    },
    {
      info: { connected: false, connection_state: 'sign_in_required', connection_state_reason: 'access_token_expired' },
      badge: 'Sign-in required',
      text: /more than about 8 hours after signing in/,
      first: 'Reconnect Tesla',
    },
    {
      info: {
        connected: false,
        connection_status: 'disconnected',
        connection_state: 'temporarily_unavailable',
        connection_state_reason: 'no_response',
        connection_error: 'Tesla cloud did not return Powerwall data.',
      },
      badge: 'Connection temporarily unavailable',
      text: /Your saved Tesla sign-in is kept/,
      first: 'Retry Connection',
    },
  ])('shows $badge with the fitting first action', async ({ info, badge, text, first }) => {
    authInfo = { authenticated: true, email: EMAIL, site_id: 111, ...info };
    backend({});
    render(<Settings />);

    expect(await screen.findByRole('status', { name: '' })).toHaveTextContent(badge);
    expect(screen.getByText(text)).toBeInTheDocument();
    const actions = screen.getAllByRole('button').map((button) => button.textContent);
    const reconnect = actions.indexOf('Reconnect Tesla');
    const test = actions.findIndex((label) => label === 'Retry Connection' || label === 'Test Connection');
    expect(actions[Math.min(reconnect, test)]).toBe(first);
  });

  it('reconnects without signing out and keeps the current status visible', async () => {
    authInfo = { authenticated: true, email: EMAIL, site_id: 111, connected: true, connection_state: 'connected' };
    backend({ '/api/auth/setup/start': () => startResponse() });
    render(<Settings />);

    fireEvent.click(await screen.findByRole('button', { name: 'Reconnect Tesla' }));

    expect(screen.getByLabelText('Tesla Account Email')).toHaveValue(EMAIL);
    expect(screen.getByText(/Your current connection stays active until the new sign-in is saved/)).toBeInTheDocument();
    await startSignIn();
    expect(screen.getAllByRole('status')[0]).toHaveTextContent('Connected');
    expect(callsTo('/api/auth/tesla/logout')).toHaveLength(0);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByLabelText('Tesla Callback Link')).not.toBeInTheDocument());
    expect(callsTo('/api/auth/tesla/logout')).toHaveLength(0);
  });
});

describe('Experimental Mac helper', () => {
  const MAC = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 Safari/605.1.15';

  it('is only offered on a Mac and launches with a handoff, never the API key', async () => {
    vi.spyOn(window.navigator, 'userAgent', 'get').mockReturnValue(MAC);
    localStorage.setItem('powernight_api_key', 'app-key-secret');
    backend({
      '/api/auth/setup/start': () => startResponse(),
      '/api/auth/setup/handoff': () => respond({ success: true, handoff: 'handoff-token', setup: progress({ helper_state: 'pending' }) }),
      '/api/auth/setup/status/': () => respond({ success: true, data: { exists: true, ...progress({ helper_state: 'pending' }) } }),
    });
    render(<Settings />);
    await startSignIn();

    fireEvent.click(screen.getByLabelText(/Try the experimental Mac helper/));
    fireEvent.click(screen.getByRole('button', { name: 'Sign In with the Mac Helper' }));

    await waitFor(() => expect(openHelperLink).toHaveBeenCalledTimes(1));
    const link = vi.mocked(openHelperLink).mock.calls[0][0];
    expect(link).toBe('powernight-login://start?v=1&origin=http%3A%2F%2Flocalhost%3A3000&handoff=handoff-token');
    expect(link).not.toContain('app-key-secret');
    expect(link).not.toContain(SESSION);
    expect(screen.getByLabelText('Tesla Callback Link')).toBeInTheDocument();
  });

  it('is not offered on other systems', async () => {
    vi.spyOn(window.navigator, 'userAgent', 'get').mockReturnValue('Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/141.0');
    backend({ '/api/auth/setup/start': () => startResponse() });
    render(<Settings />);
    await startSignIn();

    expect(screen.queryByLabelText(/Try the experimental Mac helper/)).not.toBeInTheDocument();
  });

  it('falls back to the manual steps when the helper does not respond', () => {
    localStorage.setItem('powernight_mac_helper', 'on');
    render(<MacHelperLauncher helperState="pending" launchedAt={Date.now() - 20000} launching={false} onLaunch={vi.fn()} />);

    expect(screen.getByText(/The helper did not respond/)).toBeInTheDocument();
  });
});

describe('Sign-in help visuals', () => {
  const CHROME = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0 Safari/537.36';

  it('preselects the detected browser and shows the diagram by default', () => {
    render(<TeslaSignInHelp userAgent={CHROME} />);
    expect(screen.getByRole('tab', { name: 'Chrome / Edge' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('img', { name: /Chrome \/ Edge/ }).tagName.toLowerCase()).toBe('svg');
  });

  it('shows a screenshot when chosen and falls back to the diagram without one', () => {
    render(
      <TeslaSignInHelp
        userAgent={CHROME}
        visual="screenshot"
        screenshots={{ '../../../assets/tesla-help/chromium-console.png': '/assets/chromium-console.png' }}
      />,
    );
    expect(screen.getByRole('img', { name: /Chrome \/ Edge/ })).toHaveAttribute('src', '/assets/chromium-console.png');

    fireEvent.click(screen.getByRole('tab', { name: 'Safari' }));
    expect(screen.getByRole('img', { name: /Safari/ }).tagName.toLowerCase()).toBe('svg');
  });

  it('can be switched in the running app for comparison', () => {
    expect(resolveHelpVisual()).toBe('diagram');
    localStorage.setItem('powernight_help_visual', 'screenshot');
    expect(resolveHelpVisual()).toBe('screenshot');
  });
});

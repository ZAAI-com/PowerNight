import api from './api';
import type { TeslaSetupResponse, TeslaSetupStatusResponse } from '../types';

/** Status code plus parsed body; 4xx and 5xx resolve instead of throwing. */
export interface SetupApiResult<T> {
  status: number;
  ok: boolean;
  body: T;
}

/**
 * Tesla setup routes as [method, path]. tests/unit/test_route_smoke.py checks
 * that each one exists in Flask; a trailing slash marks a path parameter.
 */
export const SETUP_ROUTES = {
  start: ['POST', '/api/auth/setup/start'],
  callback: ['POST', '/api/auth/setup/callback'],
  tokens: ['POST', '/api/auth/setup/tokens'],
  sites: ['POST', '/api/auth/setup/sites'],
  complete: ['POST', '/api/auth/setup/complete'],
  cancel: ['POST', '/api/auth/setup/cancel'],
  handoff: ['POST', '/api/auth/setup/handoff'],
  status: ['GET', '/api/auth/setup/status/'],
} as const;

const UNEXPECTED_RESPONSE = { success: false, error: 'Unexpected response from PowerNight' };

async function request<T>(path: string, init?: RequestInit): Promise<SetupApiResult<T>> {
  const response = init ? await api.authenticatedFetch(path, init) : await api.authenticatedFetch(path);
  let body: unknown;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  const ok = typeof response.ok === 'boolean' ? response.ok : true;
  const status = typeof response.status === 'number' ? response.status : (ok ? 200 : 500);
  return { status, ok, body: (body ?? UNEXPECTED_RESPONSE) as T };
}

function postJson<T = TeslaSetupResponse>(path: string, payload: Record<string, string>) {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export const teslaSetupApi = {
  start: (email: string) => postJson(SETUP_ROUTES.start[1], { email }),
  submitCallback: (sessionId: string, callbackUrl: string) =>
    postJson(SETUP_ROUTES.callback[1], { session_id: sessionId, callback_url: callbackUrl }),
  importTokens: (email: string, refreshToken: string, accessToken: string) =>
    postJson(SETUP_ROUTES.tokens[1], { email, refresh_token: refreshToken, access_token: accessToken }),
  retrySites: (sessionId: string) => postJson(SETUP_ROUTES.sites[1], { session_id: sessionId }),
  complete: (sessionId: string, siteId: string) =>
    postJson(SETUP_ROUTES.complete[1], { session_id: sessionId, site_id: siteId }),
  cancel: (sessionId: string) => postJson(SETUP_ROUTES.cancel[1], { session_id: sessionId }),
  createHandoff: (sessionId: string) => postJson(SETUP_ROUTES.handoff[1], { session_id: sessionId }),
  status: (sessionId: string) =>
    request<TeslaSetupStatusResponse>(`${SETUP_ROUTES.status[1]}${encodeURIComponent(sessionId)}`),
};

export default teslaSetupApi;

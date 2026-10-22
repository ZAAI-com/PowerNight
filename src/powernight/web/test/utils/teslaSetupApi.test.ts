import { beforeEach, describe, expect, it, vi } from 'vitest';
import api from '../../src/utils/api';
import teslaSetupApi from '../../src/utils/teslaSetupApi';

vi.mock('../../src/utils/api', () => ({
  default: { authenticatedFetch: vi.fn() },
}));

const authenticatedFetch = vi.mocked(api.authenticatedFetch);

describe('teslaSetupApi', () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([400, 404, 409, 410, 500, 502])('resolves %i responses with the body instead of throwing', async (status) => {
    authenticatedFetch.mockResolvedValue(new Response(
      JSON.stringify({ success: false, error_code: 'EXCHANGE_FAILED', error: 'nope' }),
      { status },
    ));

    const result = await teslaSetupApi.submitCallback('session-1', 'tesla://auth/callback?code=a&state=b');

    expect(result.status).toBe(status);
    expect(result.ok).toBe(false);
    expect(result.body.error_code).toBe('EXCHANGE_FAILED');
  });

  it('keeps the existing request bodies', async () => {
    authenticatedFetch.mockResolvedValue(new Response(JSON.stringify({ success: true })));

    await teslaSetupApi.complete('session-1', '42');

    expect(authenticatedFetch).toHaveBeenCalledWith('/api/auth/setup/complete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: 'session-1', site_id: '42' }),
    });
  });

  it('tolerates mocked responses without a status and bodies that are not JSON', async () => {
    authenticatedFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ success: true }) } as Response);
    expect((await teslaSetupApi.cancel('session-1')).status).toBe(200);

    authenticatedFetch.mockResolvedValueOnce(new Response('<html>proxy error</html>', { status: 502 }));
    const result = await teslaSetupApi.cancel('session-1');
    expect(result.status).toBe(502);
    expect(result.body.success).toBe(false);
  });

  it('encodes the session ID in the status path', async () => {
    authenticatedFetch.mockResolvedValue(new Response(JSON.stringify({ success: true, data: { exists: false } })));
    await teslaSetupApi.status('a/b');
    expect(authenticatedFetch).toHaveBeenCalledWith('/api/auth/setup/status/a%2Fb');
  });
});

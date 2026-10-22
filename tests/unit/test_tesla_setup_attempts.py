"""
Tesla sign-in attempts: the state machine behind the Settings wizard.

Covers single code exchange under concurrency, deadlines at every commit,
cancellation, credential writes that fail, secret hygiene and the Mac helper
handoff. Tesla calls are mocked at the manager's boundary.
"""

import json
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from powernight.core.auth import token_storage
from powernight.core.auth.setup_attempts import (
    AUTHORIZATION_URL_HINT,
    SetupError,
    SiteDiscoveryError,
    parse_callback_text,
)
from powernight.core.auth.tesla_oauth import TeslaOAuthManager


pytestmark = pytest.mark.unit

EMAIL = 'owner@example.com'
SITES = [{'id': 111222, 'name': 'Home', 'type': 'battery', 'resource_type': 'battery', 'state': 'online'}]
TOKENS = {
    'access_token': 'eyJhbGciOiJSUzI1NiJ9.eyJzdWIiOiJvd25lciJ9.c2lnbmF0dXJlLXZhbHVl',
    'refresh_token': 'refresh-secret-value',
    'expires_in': 28800,
}
EXCHANGE = 'powernight.core.auth.tesla_oauth.tesla_auth._exchange_code'
SAMPLES = Path(__file__).resolve().parents[2] / 'src/powernight/web/test/fixtures/tesla-callback-samples.json'
# Energy sites legitimately carry a 'state' key ('online'), so the OAuth state
# is checked by value instead
SECRET_KEYS = {'access_token', 'refresh_token', 'code_verifier', 'state_digest', 'tokens', 'handoff'}


class FakeClock:
    def __init__(self) -> None:
        self.now = datetime(2026, 10, 21, 12, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def manager(tmp_path, clock):
    return TeslaOAuthManager(storage_path=str(tmp_path), clock=clock, expiry_timers=False)


def start(manager):
    progress = manager.start_setup(EMAIL)
    query = urllib.parse.parse_qs(urllib.parse.urlparse(progress['auth_url']).query)
    return progress['session_id'], query['state'][0]


def callback(state, code='code-1'):
    return f'tesla://auth/callback?code={code}&state={state}'


def signed_in(manager, sites=SITES):
    """An attempt that exchanged its code and listed its sites."""
    session_id, state = start(manager)
    with patch(EXCHANGE, return_value=dict(TOKENS)), \
            patch.object(manager, 'get_energy_sites', return_value=list(sites)):
        manager.submit_callback(session_id, callback(state))
    return session_id


def assert_no_secrets(value, secrets=(TOKENS['access_token'], TOKENS['refresh_token'])):
    """No secret key names at any depth and no secret values anywhere."""
    def walk(node):
        if isinstance(node, dict):
            for key, child in node.items():
                assert key not in SECRET_KEYS, key
                walk(child)
        elif isinstance(node, list):
            for child in node:
                walk(child)
    walk(value)
    text = json.dumps(value, default=str)
    for secret in secrets:
        assert secret not in text


class TestStart:
    def test_progress_has_deadline_and_auth_url_but_no_secrets(self, manager):
        progress = manager.start_setup(EMAIL)
        attempt = manager._attempts[progress['session_id']]

        assert progress['step'] == 'awaiting_callback'
        assert progress['setup_expires_in_seconds'] == 600
        assert progress['auth_url'].startswith(TeslaOAuthManager.AUTHORIZATION_URL)
        assert_no_secrets(progress, secrets=(attempt.code_verifier,))
        assert attempt.code_verifier not in repr(attempt)

    def test_live_attempt_cap_replaces_the_oldest(self, manager, clock):
        manager.MAX_LIVE_ATTEMPTS = 2
        first, _ = start(manager)
        clock.advance(seconds=1)
        start(manager)
        clock.advance(seconds=1)
        start(manager)

        assert manager._attempts[first].step == 'cancelled'
        assert manager._attempts[first].code_verifier is None


class TestCallbackValidation:
    def test_state_mismatch_leaves_attempt_untouched(self, manager):
        session_id, _ = start(manager)
        with patch(EXCHANGE) as exchange, pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, callback('another-attempt'))

        assert raised.value.code == 'STATE_MISMATCH'
        assert raised.value.http_status == 400
        assert 'state' in raised.value.message.lower()
        assert manager._attempts[session_id].step == 'awaiting_callback'
        exchange.assert_not_called()

    def test_tesla_denial_keeps_waiting_for_a_new_sign_in(self, manager):
        session_id, state = start(manager)
        with pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, f'tesla://auth/callback?error=login_cancelled&state={state}')

        assert raised.value.code == 'TESLA_DENIED'
        assert 'login_cancelled' in raised.value.message
        assert manager._attempts[session_id].step == 'awaiting_callback'

    def test_pasted_sign_in_page_explains_the_mistake(self, manager):
        session_id, _ = start(manager)
        with pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, manager._attempts[session_id].auth_url)

        assert raised.value.code == 'INVALID_INPUT'
        assert raised.value.message == AUTHORIZATION_URL_HINT

    def test_unknown_session_mentions_session(self, manager):
        with pytest.raises(SetupError) as raised:
            manager.submit_callback('x' * 43, 'tesla://auth/callback?code=a&state=b')
        assert raised.value.code == 'SETUP_NOT_FOUND'
        assert raised.value.http_status == 404
        assert 'session' in raised.value.message.lower()


@pytest.mark.parametrize('sample', json.loads(SAMPLES.read_text()), ids=lambda s: s['name'])
def test_parser_matches_shared_samples(sample):
    parsed = parse_callback_text(sample['text'])
    assert parsed.kind == sample['kind']
    for field in ('code', 'state', 'error'):
        if field in sample:
            assert getattr(parsed, field) == sample[field]


class TestSingleExchange:
    def test_concurrent_duplicate_gets_progress_without_waiting(self, manager):
        session_id, state = start(manager)
        entered, release = threading.Event(), threading.Event()

        def slow_exchange(code, verifier):
            entered.set()
            assert release.wait(5)
            return dict(TOKENS)

        results = {}
        with patch(EXCHANGE, side_effect=slow_exchange) as exchange, \
                patch.object(manager, 'get_energy_sites', return_value=SITES):
            first = threading.Thread(
                target=lambda: results.setdefault('first', manager.submit_callback(session_id, callback(state)))
            )
            first.start()
            assert entered.wait(5)

            began = time.monotonic()
            duplicate = manager.submit_callback(session_id, callback(state))
            assert time.monotonic() - began < 0.5
            release.set()
            first.join(5)

        assert duplicate.http_status == 202
        assert duplicate.progress['step'] == 'exchanging'
        assert results['first'].progress['step'] == 'selecting_site'
        assert exchange.call_count == 1

    def test_duplicate_after_success_returns_progress(self, manager):
        session_id, state = start(manager)
        with patch(EXCHANGE, return_value=dict(TOKENS)) as exchange, \
                patch.object(manager, 'get_energy_sites', return_value=SITES):
            manager.submit_callback(session_id, callback(state))
            duplicate = manager.submit_callback(session_id, callback(state))

        assert duplicate.http_status == 200
        assert duplicate.duplicate is True
        assert duplicate.progress['step'] == 'selecting_site'
        assert exchange.call_count == 1

    def test_rejected_code_is_never_retried_and_three_failures_end_the_attempt(self, manager):
        session_id, state = start(manager)
        rejected = RuntimeError('Token exchange failed (HTTP 400): {"error":"invalid_grant"}')

        with patch(EXCHANGE, side_effect=rejected) as exchange:
            with pytest.raises(SetupError) as first:
                manager.submit_callback(session_id, callback(state, 'code-1'))
            assert first.value.code == 'EXCHANGE_FAILED'
            assert first.value.http_status == 400
            assert manager._attempts[session_id].step == 'awaiting_callback'

            with pytest.raises(SetupError) as reused:
                manager.submit_callback(session_id, callback(state, 'code-1'))
            assert reused.value.code == 'EXCHANGE_FAILED'
            assert exchange.call_count == 1

            with pytest.raises(SetupError):
                manager.submit_callback(session_id, callback(state, 'code-2'))
            with pytest.raises(SetupError) as last:
                manager.submit_callback(session_id, callback(state, 'code-3'))

        assert exchange.call_count == 3
        assert last.value.http_status == 410
        assert manager._attempts[session_id].step == 'failed'
        assert manager._attempts[session_id].code_verifier is None

    def test_unreachable_tesla_is_a_502(self, manager):
        session_id, state = start(manager)
        with patch(EXCHANGE, side_effect=RuntimeError('HTTP/2 transport failed: timed out')), \
                pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, callback(state))
        assert raised.value.code == 'EXCHANGE_FAILED'
        assert raised.value.http_status == 502

    @pytest.mark.parametrize('error', [
        RuntimeError("No refresh_token in response: {'access_token': '%s', 'body': 'tesla-body'}"
                     % TOKENS['access_token']),
        RuntimeError('Token exchange failed (HTTP 401): tesla-body %s' % TOKENS['access_token']),
    ])
    def test_pypowerwall_error_text_never_reaches_responses_or_logs(self, manager, error):
        session_id, state = start(manager)
        manager.logger = MagicMock()

        with patch(EXCHANGE, side_effect=error), pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, callback(state))

        logged = json.dumps([str(call) for call in manager.logger.mock_calls])
        for text in (raised.value.message, json.dumps(raised.value.progress), logged):
            assert 'tesla-body' not in text
            assert TOKENS['access_token'] not in text


class TestSiteDiscovery:
    def test_unavailable_discovery_retries_without_a_new_exchange(self, manager):
        session_id, state = start(manager)
        with patch(EXCHANGE, return_value=dict(TOKENS)) as exchange, \
                patch.object(manager, 'get_energy_sites',
                             side_effect=[SiteDiscoveryError(rejected=False, status=503), SITES]):
            with pytest.raises(SetupError) as raised:
                manager.submit_callback(session_id, callback(state))
            assert raised.value.code == 'SITE_DISCOVERY_UNAVAILABLE'
            assert raised.value.http_status == 502
            assert raised.value.progress['step'] == 'selecting_site'
            assert raised.value.progress['sites'] is None

            outcome = manager.retry_site_discovery(session_id)

        assert outcome.progress['sites'] == SITES
        assert exchange.call_count == 1

    def test_rejected_discovery_ends_attempt_and_wipes_tokens(self, manager):
        session_id, state = start(manager)
        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites',
                             side_effect=SiteDiscoveryError(rejected=True, status=403)), \
                pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, callback(state))

        assert raised.value.code == 'TESLA_DENIED'
        assert manager._attempts[session_id].step == 'failed'
        assert manager._attempts[session_id].tokens is None

    def test_zero_sites_is_reported_and_no_site_can_be_saved(self, manager):
        session_id = signed_in(manager, sites=[])
        status = manager.get_session_status(session_id)
        assert status['sites'] == []
        assert status['error_code'] == 'NO_ENERGY_SITES'

        result = manager.complete_setup(session_id, '111222')
        assert result['error_code'] == 'INVALID_SITE'
        assert result['http_status'] == 400


class TestDeadline:
    def test_callback_after_ten_minutes_is_refused_and_secrets_wiped(self, manager, clock):
        session_id, state = start(manager)
        clock.advance(minutes=10)

        with patch(EXCHANGE) as exchange, pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, callback(state))

        assert raised.value.code == 'SETUP_EXPIRED'
        assert raised.value.http_status == 410
        exchange.assert_not_called()
        assert manager._attempts[session_id].code_verifier is None

    def test_expiry_during_exchange_discards_the_tokens(self, manager, clock):
        session_id, state = start(manager)

        def exchange_then_expire(code, verifier):
            clock.advance(minutes=11)
            return dict(TOKENS)

        with patch(EXCHANGE, side_effect=exchange_then_expire), \
                patch.object(manager, 'get_energy_sites') as sites, \
                pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, callback(state))

        assert raised.value.code == 'SETUP_EXPIRED'
        sites.assert_not_called()
        assert manager._attempts[session_id].tokens is None

    def test_expiry_during_discovery_discards_the_tokens(self, manager, clock):
        session_id, state = start(manager)

        def sites_then_expire(token):
            clock.advance(minutes=11)
            return SITES

        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites', side_effect=sites_then_expire), \
                pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, callback(state))

        assert raised.value.code == 'SETUP_EXPIRED'
        assert manager._attempts[session_id].tokens is None

    def test_expiry_before_the_write_keeps_old_credentials(self, manager, clock, tmp_path):
        manager.auth_storage.store_auth_data('old@example.com', {'access_token': 'old'}, {'id': 1})
        before = (tmp_path / '.pypowerwall.auth').read_bytes()
        session_id = signed_in(manager)

        def late_commit(write):
            clock.advance(minutes=11)
            write()

        result = manager.complete_setup(session_id, '111222', commit=late_commit)

        assert result['error_code'] == 'SETUP_EXPIRED'
        assert (tmp_path / '.pypowerwall.auth').read_bytes() == before
        assert manager._attempts[session_id].tokens is None

    def test_expiry_timer_callback_wipes_secrets(self, manager, clock):
        session_id, _ = start(manager)
        clock.advance(minutes=10, seconds=1)
        manager._expire(session_id)
        assert manager._attempts[session_id].step == 'expired'
        assert manager._attempts[session_id].code_verifier is None


class TestCancel:
    def test_cancel_during_exchange_discards_the_result(self, manager):
        session_id, state = start(manager)

        def exchange_then_cancel(code, verifier):
            manager.cancel_setup(session_id)
            return dict(TOKENS)

        with patch(EXCHANGE, side_effect=exchange_then_cancel), pytest.raises(SetupError) as raised:
            manager.submit_callback(session_id, callback(state))

        assert raised.value.code == 'SETUP_CANCELLED'
        assert manager._attempts[session_id].tokens is None
        assert manager.complete_setup(session_id, '111222')['error_code'] == 'SETUP_CANCELLED'

    def test_cancel_is_idempotent_and_only_affects_its_attempt(self, manager):
        first, _ = start(manager)
        second, _ = start(manager)

        manager.cancel_setup(first)
        again = manager.cancel_setup(first)

        assert again.duplicate is True
        assert manager._attempts[second].step == 'awaiting_callback'

    def test_cancel_while_saving_is_refused(self, manager):
        session_id = signed_in(manager)
        refused = []

        def commit(write):
            with pytest.raises(SetupError) as raised:
                manager.cancel_setup(session_id)
            refused.append(raised.value.http_status)
            write()

        result = manager.complete_setup(session_id, '111222', commit=commit)

        assert refused == [409]
        assert result['success'] is True


class TestCompletion:
    def test_concurrent_duplicate_completion_writes_once(self, manager):
        session_id = signed_in(manager)
        entered, release = threading.Event(), threading.Event()
        writes = []

        def slow_commit(write):
            entered.set()
            assert release.wait(5)
            write()
            writes.append(1)

        results = {}
        worker = threading.Thread(target=lambda: results.setdefault(
            'first', manager.complete_setup(session_id, '111222', commit=slow_commit)))
        worker.start()
        assert entered.wait(5)
        in_progress = manager.complete_setup(session_id, '111222', commit=slow_commit)
        release.set()
        worker.join(5)
        replay = manager.complete_setup(session_id, '111222', commit=slow_commit)
        other_site = manager.complete_setup(session_id, '999', commit=slow_commit)

        assert in_progress['http_status'] == 202
        assert results['first']['success'] is True and results['first']['duplicate'] is False
        assert replay['success'] is True and replay['duplicate'] is True
        assert other_site['http_status'] == 409
        assert writes == [1]

    def test_failed_write_keeps_attempt_and_old_files(self, manager, tmp_path):
        manager.auth_storage.store_auth_data('old@example.com', {'access_token': 'old'}, {'id': 1})
        before = {name: (tmp_path / name).read_bytes() for name in ('.pypowerwall.auth', '.pypowerwall.site')}
        session_id = signed_in(manager)

        def failing_commit(write):
            raise OSError('disk full')

        result = manager.complete_setup(session_id, '111222', commit=failing_commit)

        assert result['error_code'] == 'CREDENTIAL_WRITE_FAILED'
        assert result['http_status'] == 500
        attempt = manager._attempts[session_id]
        assert attempt.step == 'selecting_site'
        assert attempt.tokens is not None
        assert {name: (tmp_path / name).read_bytes() for name in before} == before

        # A retry with a working write succeeds with the same attempt
        assert manager.complete_setup(session_id, '111222')['success'] is True
        assert manager.auth_storage.load_auth_data()['email'] == EMAIL

    def test_completion_wipes_secrets_and_saves_selected_site(self, manager):
        session_id = signed_in(manager)
        result = manager.complete_setup(session_id, 111222)

        attempt = manager._attempts[session_id]
        assert result['success'] is True
        assert attempt.step == 'complete'
        assert attempt.tokens is None and attempt.code_verifier is None
        assert manager.auth_storage.load_auth_data()['site'] == {'id': 111222}
        assert_no_secrets(result['setup'])


class TestStatus:
    def test_progress_never_contains_secrets_at_any_step(self, manager):
        session_id, state = start(manager)
        secrets = (TOKENS['access_token'], TOKENS['refresh_token'], state)
        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites', return_value=SITES):
            manager.submit_callback(session_id, callback(state))
        assert_no_secrets(manager.get_session_status(session_id), secrets)
        manager.complete_setup(session_id, '111222')
        assert_no_secrets(manager.get_session_status(session_id), secrets)

    def test_auth_url_is_only_returned_while_waiting_for_sign_in(self, manager):
        session_id, state = start(manager)
        assert manager.get_session_status(session_id)['auth_url']
        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites', return_value=SITES):
            manager.submit_callback(session_id, callback(state))
        assert manager.get_session_status(session_id)['auth_url'] is None

    def test_ended_attempts_explain_why_until_forgotten(self, manager, clock):
        expired, _ = start(manager)
        cancelled, _ = start(manager)
        manager.cancel_setup(cancelled)
        clock.advance(minutes=11)

        assert manager.get_session_status(expired)['error_code'] == 'SETUP_EXPIRED'
        assert manager.get_session_status(expired)['exists'] is False
        assert manager.get_session_status(cancelled)['error_code'] == 'SETUP_CANCELLED'

        clock.advance(hours=2)
        manager.sweep_expired()
        status = manager.get_session_status(expired)
        assert status['exists'] is False
        assert status['error_code'] == 'SETUP_NOT_FOUND'

    def test_unknown_session_is_not_found(self, manager):
        status = manager.get_session_status('restarted-session-id-1234567890')
        assert status == {
            'exists': False,
            'step': None,
            'error_code': 'SETUP_NOT_FOUND',
            'error': status['error'],
        }
        assert 'restarted' in status['error']


class TestCredentialTransaction:
    def test_failed_site_write_restores_both_files(self, tmp_path):
        storage = token_storage.PyPowerwallAuthStorage(str(tmp_path))
        storage.store_auth_data('old@example.com', {'access_token': 'old'}, {'id': 1})
        before = {name: (tmp_path / name).read_bytes() for name in ('.pypowerwall.auth', '.pypowerwall.site')}
        real_write = token_storage.write_private_file

        def fail_on_site(path, content, **kwargs):
            if path.name == '.pypowerwall.site' and content == '2':
                raise OSError('disk full')
            return real_write(path, content, **kwargs)

        with patch.object(token_storage, 'write_private_file', side_effect=fail_on_site):
            with pytest.raises(OSError):
                storage.replace_auth_data('new@example.com', {'access_token': 'new'}, {'id': 2})

        assert {name: (tmp_path / name).read_bytes() for name in before} == before

    def test_first_time_failure_leaves_no_files(self, tmp_path):
        storage = token_storage.PyPowerwallAuthStorage(str(tmp_path))
        real_write = token_storage.write_private_file

        def fail_on_site(path, content, **kwargs):
            if path.name == '.pypowerwall.site':
                raise OSError('disk full')
            return real_write(path, content, **kwargs)

        with patch.object(token_storage, 'write_private_file', side_effect=fail_on_site):
            with pytest.raises(OSError):
                storage.replace_auth_data('new@example.com', {'access_token': 'new'}, {'id': 2})

        assert not (tmp_path / '.pypowerwall.auth').exists()
        assert not (tmp_path / '.pypowerwall.site').exists()

    def test_missing_site_id_removes_the_previous_site(self, tmp_path):
        storage = token_storage.PyPowerwallAuthStorage(str(tmp_path))
        storage.store_auth_data('old@example.com', {'access_token': 'old'}, {'id': 1})
        storage.replace_auth_data('new@example.com', {'access_token': 'new'}, {'id': None})
        assert not (tmp_path / '.pypowerwall.site').exists()


class TestHandoff:
    def test_helper_flow_consumes_the_handoff(self, manager):
        session_id, state = start(manager)
        handoff = manager.create_handoff(session_id)['handoff']

        authorization = manager.helper_authorization(handoff)
        assert authorization['auth_url'] == manager._attempts[session_id].auth_url
        assert 'session_id' not in authorization
        assert manager.get_session_status(session_id)['helper_state'] == 'opened'

        with patch(EXCHANGE, return_value=dict(TOKENS)), \
                patch.object(manager, 'get_energy_sites', return_value=SITES):
            outcome = manager.helper_submit_callback(handoff, callback(state))
        assert outcome.progress['step'] == 'selecting_site'
        assert manager.get_session_status(session_id)['helper_state'] == 'submitted'

        with pytest.raises(SetupError) as replay:
            manager.helper_submit_callback(handoff, callback(state))
        assert replay.value.http_status == 403

    def test_minting_again_invalidates_the_previous_handoff(self, manager):
        session_id, _ = start(manager)
        old = manager.create_handoff(session_id)['handoff']
        new = manager.create_handoff(session_id)['handoff']

        with pytest.raises(SetupError) as raised:
            manager.helper_authorization(old)
        assert raised.value.code == 'HANDOFF_INVALID'
        assert manager.helper_authorization(new)['auth_url']

    def test_retryable_failure_keeps_the_handoff(self, manager):
        session_id, _ = start(manager)
        handoff = manager.create_handoff(session_id)['handoff']
        with pytest.raises(SetupError):
            manager.helper_submit_callback(handoff, callback('wrong-state'))
        assert manager.helper_authorization(handoff)['auth_url']

    def test_handoff_ends_with_the_attempt(self, manager, clock):
        session_id, _ = start(manager)
        handoff = manager.create_handoff(session_id)['handoff']
        clock.advance(minutes=11)
        with pytest.raises(SetupError) as raised:
            manager.helper_authorization(handoff)
        assert raised.value.http_status == 410

    @pytest.mark.parametrize('handoff', [None, '', 'short', 'x' * 43])
    def test_unknown_handoffs_are_refused(self, manager, handoff):
        start(manager)
        with pytest.raises(SetupError) as raised:
            manager.helper_authorization(handoff)
        assert raised.value.code == 'HANDOFF_INVALID'
        assert raised.value.http_status == 403

    def test_token_import_attempts_cannot_use_the_helper(self, manager):
        with patch.object(manager, 'get_energy_sites', return_value=SITES):
            result = manager.import_tokens(EMAIL, 'rt', TOKENS['access_token'])
        with pytest.raises(SetupError) as raised:
            manager.create_handoff(result['session_id'])
        assert raised.value.http_status == 409

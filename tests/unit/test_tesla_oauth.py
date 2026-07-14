"""
Unit tests for Tesla OAuth functionality.

Tests the real public API:
- powernight.core.auth.tesla_oauth.TeslaOAuthManager
- powernight.core.auth.token_storage.PyPowerwallAuthStorage

External HTTP calls are mocked at the usage boundary
(powernight.core.auth.tesla_oauth.requests) with unittest.mock.patch.
"""

import base64
import hashlib
import json
import time
import urllib.parse
from unittest.mock import Mock, patch

import pytest

from powernight.core.auth.tesla_oauth import TeslaOAuthManager
from powernight.core.auth.token_storage import PyPowerwallAuthStorage


EMAIL = "tesla-owner@example.com"


def make_tokens(expires_at=None):
    """Build a token dict as store_auth_data expects."""
    if expires_at is None:
        expires_at = time.time() + 3600
    return {
        "access_token": "access-token-1234567890",
        "refresh_token": "refresh-token-0987654321",
        "token_type": "Bearer",
        "expires_at": expires_at,
    }


def make_site(site_id=123456):
    return {"id": site_id, "name": "Home Energy Site", "type": "battery"}


class TestPyPowerwallAuthStorage:
    """Tests for pypowerwall-compatible auth file storage."""

    def test_init_creates_storage_directory(self, tmp_path):
        target = tmp_path / "auth-storage"
        assert not target.exists()

        PyPowerwallAuthStorage(storage_path=str(target))

        assert target.is_dir()

    def test_store_and_load_round_trip(self, tmp_path):
        storage = PyPowerwallAuthStorage(storage_path=str(tmp_path))

        storage.store_auth_data(EMAIL, make_tokens(), make_site(123456))

        assert (tmp_path / ".pypowerwall.auth").exists()
        assert (tmp_path / ".pypowerwall.site").read_text().strip() == "123456"

        loaded = storage.load_auth_data()
        assert loaded is not None
        assert loaded["email"] == EMAIL
        assert loaded["access_token"] == "access-token-1234567890"
        assert loaded["refresh_token"] == "refresh-token-0987654321"
        assert loaded["token_type"] == "Bearer"
        assert isinstance(loaded["expires_at"], float)
        assert loaded["site"] == {"id": 123456}

    def test_auth_file_uses_teslapy_cache_format(self, tmp_path):
        storage = PyPowerwallAuthStorage(storage_path=str(tmp_path))
        storage.store_auth_data(EMAIL, make_tokens(), make_site())

        with open(tmp_path / ".pypowerwall.auth") as f:
            raw = json.load(f)

        assert EMAIL in raw
        assert raw[EMAIL]["url"] == "https://auth.tesla.com/"
        sso = raw[EMAIL]["sso"]
        assert sso["access_token"] == "access-token-1234567890"
        assert sso["refresh_token"] == "refresh-token-0987654321"

    def test_load_without_auth_file_returns_none(self, tmp_path):
        storage = PyPowerwallAuthStorage(storage_path=str(tmp_path))
        assert storage.load_auth_data() is None
        assert storage.has_auth_data() is False

    def test_load_supports_flat_json_format(self, tmp_path):
        flat = {
            "email": EMAIL,
            "access_token": "flat-access",
            "refresh_token": "flat-refresh",
            "token_type": "Bearer",
            "expires_at": time.time() + 100,
            "site_id": 42,
        }
        (tmp_path / ".pypowerwall.auth").write_text(json.dumps(flat))

        storage = PyPowerwallAuthStorage(storage_path=str(tmp_path))
        loaded = storage.load_auth_data()

        assert loaded is not None
        assert loaded["email"] == EMAIL
        assert loaded["access_token"] == "flat-access"
        assert loaded["site"] == {"id": 42}

    def test_clear_auth_data_removes_files(self, tmp_path):
        storage = PyPowerwallAuthStorage(storage_path=str(tmp_path))
        storage.store_auth_data(EMAIL, make_tokens(), make_site())
        assert storage.has_auth_data() is True

        storage.clear_auth_data()

        assert storage.has_auth_data() is False
        assert not (tmp_path / ".pypowerwall.auth").exists()
        assert not (tmp_path / ".pypowerwall.site").exists()
        assert storage.load_auth_data() is None

    def test_is_token_expired(self, tmp_path):
        storage = PyPowerwallAuthStorage(storage_path=str(tmp_path))

        fresh = {"expires_at": time.time() + 3600}
        stale = {"expires_at": time.time() - 10}
        assert storage.is_token_expired(fresh) is False
        assert storage.is_token_expired(stale) is True

        # Missing or empty auth data counts as expired
        assert storage.is_token_expired({}) is True
        assert storage.is_token_expired() is True  # no stored file at all

    def test_get_storage_info_reflects_stored_data(self, tmp_path):
        storage = PyPowerwallAuthStorage(storage_path=str(tmp_path))
        storage.store_auth_data(EMAIL, make_tokens(), make_site(777))

        info = storage.get_storage_info()

        assert info["storage_path"] == str(tmp_path)
        assert info["has_auth_data"] is True
        assert info["has_site_data"] is True
        assert info["email"] == EMAIL
        assert info["token_expired"] is False
        assert info["site_id"] == 777


class TestTeslaOAuthManagerPKCE:
    """Tests for the PKCE / authorization URL part of the OAuth flow."""

    def test_generate_code_challenge_is_s256(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        verifier = "some-code-verifier-value"

        expected = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )

        challenge = manager._generate_code_challenge(verifier)
        assert challenge == expected
        assert "=" not in challenge  # padding must be stripped

    def test_generate_auth_url_returns_url_and_session(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))

        result = manager.generate_auth_url(EMAIL)

        assert set(result.keys()) == {"auth_url", "session_id"}
        assert result["auth_url"].startswith(TeslaOAuthManager.AUTHORIZATION_URL)

        session = manager._active_sessions[result["session_id"]]
        assert session["email"] == EMAIL
        assert session["step"] == "awaiting_callback"

        params = urllib.parse.parse_qs(urllib.parse.urlparse(result["auth_url"]).query)
        assert params["client_id"] == ["ownerapi"]
        assert params["response_type"] == ["code"]
        assert params["code_challenge_method"] == ["S256"]
        assert params["login_hint"] == [EMAIL]
        assert params["state"] == [session["state"]]
        # The challenge in the URL must be derived from the stored verifier
        assert params["code_challenge"] == [
            manager._generate_code_challenge(session["code_verifier"])
        ]

    def test_each_auth_url_uses_unique_pkce_values(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))

        first = manager.generate_auth_url(EMAIL)
        second = manager.generate_auth_url(EMAIL)

        s1 = manager._active_sessions[first["session_id"]]
        s2 = manager._active_sessions[second["session_id"]]
        assert first["session_id"] != second["session_id"]
        assert s1["code_verifier"] != s2["code_verifier"]
        assert s1["state"] != s2["state"]


class TestTeslaOAuthManagerCallbackExchange:
    """Tests for exchanging the callback URL for tokens."""

    def test_invalid_session_returns_error(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))

        result = manager.exchange_code_from_callback_url(
            "does-not-exist", "https://auth.tesla.com/void/callback?code=x&state=y"
        )

        assert result["success"] is False
        assert "session" in result["error"].lower()

    def test_state_mismatch_returns_error(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        session_id = manager.generate_auth_url(EMAIL)["session_id"]

        callback = "https://auth.tesla.com/void/callback?code=abc&state=wrong-state"
        result = manager.exchange_code_from_callback_url(session_id, callback)

        assert result["success"] is False
        assert "state" in result["error"].lower()

    def test_oauth_error_in_callback_returns_error(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        session_id = manager.generate_auth_url(EMAIL)["session_id"]

        callback = "https://auth.tesla.com/void/callback?error=login_cancelled"
        result = manager.exchange_code_from_callback_url(session_id, callback)

        assert result["success"] is False
        assert "login_cancelled" in result["error"]

    def test_successful_exchange_stores_tokens_and_sites(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        session_id = manager.generate_auth_url(EMAIL)["session_id"]
        state = manager._active_sessions[session_id]["state"]

        token_response = Mock()
        token_response.status_code = 200
        token_response.json.return_value = {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "id_token": "id-token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "openid email offline_access",
        }

        products_response = Mock()
        products_response.status_code = 200
        products_response.json.return_value = {
            "response": [
                {
                    "resource_type": "battery",
                    "energy_site_id": 111222,
                    "site_name": "Home",
                    "state": "online",
                },
                {"resource_type": "vehicle", "id": "car-1"},
            ]
        }

        callback = f"https://auth.tesla.com/void/callback?code=auth-code&state={state}"

        with patch(
            "powernight.core.auth.tesla_oauth.requests.post",
            return_value=token_response,
        ) as mock_post, patch(
            "powernight.core.auth.tesla_oauth.requests.get",
            return_value=products_response,
        ):
            result = manager.exchange_code_from_callback_url(session_id, callback)

        assert result["success"] is True
        assert result["sites"] == [
            {
                "id": 111222,
                "name": "Home",
                "type": "battery",
                "resource_type": "battery",
                "state": "online",
            }
        ]

        # Token request must carry the PKCE verifier for this session
        post_data = mock_post.call_args.kwargs.get("data") or mock_post.call_args[1]["data"]
        assert post_data["grant_type"] == "authorization_code"
        assert post_data["code"] == "auth-code"
        assert post_data["code_verifier"] == manager._active_sessions[session_id]["code_verifier"]

        session = manager._active_sessions[session_id]
        assert session["step"] == "selecting_site"
        assert session["access_token"] == "new-access-token"
        assert session["refresh_token"] == "new-refresh-token"


class TestTeslaOAuthManagerTokens:
    """Tests for stored-token access and refresh logic."""

    def test_get_valid_access_token_without_auth_data(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        assert manager.get_valid_access_token() is None

    def test_get_valid_access_token_returns_fresh_token(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        manager.auth_storage.store_auth_data(EMAIL, make_tokens(), make_site())

        assert manager.get_valid_access_token() == "access-token-1234567890"

    def test_get_valid_access_token_refreshes_expired_token(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        manager.auth_storage.store_auth_data(
            EMAIL, make_tokens(expires_at=time.time() - 60), make_site()
        )

        def fake_refresh():
            tokens = make_tokens()
            tokens["access_token"] = "refreshed-access-token"
            manager.auth_storage.store_auth_data(EMAIL, tokens, make_site())
            return True

        with patch.object(manager, "refresh_access_token", side_effect=fake_refresh) as mock_refresh:
            token = manager.get_valid_access_token()

        assert token == "refreshed-access-token"
        mock_refresh.assert_called_once()

    def test_get_valid_access_token_returns_none_when_refresh_fails(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        manager.auth_storage.store_auth_data(
            EMAIL, make_tokens(expires_at=time.time() - 60), make_site()
        )

        with patch.object(manager, "refresh_access_token", return_value=False):
            assert manager.get_valid_access_token() is None

    def test_refresh_access_token_without_auth_data_returns_false(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        assert manager.refresh_access_token() is False

    def test_refresh_access_token_success_updates_storage(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        manager.auth_storage.store_auth_data(
            EMAIL, make_tokens(expires_at=time.time() - 60), make_site()
        )

        refresh_response = Mock()
        refresh_response.status_code = 200
        refresh_response.json.return_value = {
            "access_token": "refreshed-access-token",
            "refresh_token": "refreshed-refresh-token",
            "expires_in": 3600,
        }

        with patch(
            "powernight.core.auth.tesla_oauth.requests.post",
            return_value=refresh_response,
        ) as mock_post:
            assert manager.refresh_access_token() is True

        post_data = mock_post.call_args.kwargs.get("data") or mock_post.call_args[1]["data"]
        assert post_data["grant_type"] == "refresh_token"
        assert post_data["refresh_token"] == "refresh-token-0987654321"

        reloaded = manager.auth_storage.load_auth_data()
        assert reloaded["access_token"] == "refreshed-access-token"
        assert reloaded["refresh_token"] == "refreshed-refresh-token"
        assert manager.auth_storage.is_token_expired(reloaded) is False

    def test_refresh_access_token_http_failure_returns_false(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        manager.auth_storage.store_auth_data(EMAIL, make_tokens(), make_site())

        error_response = Mock()
        error_response.status_code = 401
        error_response.text = "unauthorized"

        with patch(
            "powernight.core.auth.tesla_oauth.requests.post",
            return_value=error_response,
        ):
            assert manager.refresh_access_token() is False


class TestTeslaOAuthManagerStatus:
    """Tests for auth status reporting."""

    def test_get_auth_status_without_auth_data(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))

        status = manager.get_auth_status()

        assert status["authenticated"] is False
        assert status["has_auth_data"] is False
        assert status["token_expired"] is True

    def test_get_auth_status_with_fresh_auth_data(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        manager.auth_storage.store_auth_data(EMAIL, make_tokens(), make_site(555))

        status = manager.get_auth_status()

        assert status["authenticated"] is True
        assert status["has_auth_data"] is True
        assert status["token_expired"] is False
        assert status["email"] == EMAIL
        assert status["site_id"] == 555
        assert status["expires_in_seconds"] > 0

    def test_get_session_status_for_unknown_session(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))

        status = manager.get_session_status("nope")

        assert status["exists"] is False

    def test_get_session_status_for_active_session(self, tmp_path):
        manager = TeslaOAuthManager(storage_path=str(tmp_path))
        session_id = manager.generate_auth_url(EMAIL)["session_id"]

        status = manager.get_session_status(session_id)

        assert status["exists"] is True
        assert status["step"] == "awaiting_callback"
        assert status["email"] == EMAIL

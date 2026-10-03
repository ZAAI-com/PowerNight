"""
Authentication enforcement regression tests.

Credentials opt deployments into authentication. Protected endpoints reject
unauthenticated requests and accept a valid API key, while installations with
no credentials remain available on their trusted local network.
"""

import pytest
from unittest.mock import Mock

from powernight.core.config.schema import PowerNightConfig
from powernight.web.app import create_app


API_KEY = "test-enforcement-key-1234567890"


@pytest.fixture
def auth_client(tmp_path, monkeypatch):
    monkeypatch.setenv("POWERNIGHT_DATA_PATH", str(tmp_path))

    # Mirror production startup: config is loaded into the ConfigManager
    # singleton (which require_auth reads) before the app is created.
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "powerwall:\n"
        "  tesla_email: auth@example.com\n"
        "automation:\n"
        "  enabled: false\n"
        "  schedule: []\n"
        "web_interface:\n"
        "  enabled: true\n"
        f"  api_key: {API_KEY}\n"
    )
    import powernight.core.config.manager as manager_mod
    manager_mod.ConfigManager._instance = None
    manager_mod._config_manager = None
    config = manager_mod.get_config_manager().load_config(str(config_path))

    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>")
    monkeypatch.setenv("POWERNIGHT_STATIC_PATH", str(static_dir))
    app = create_app(config, testing=True)
    yield app.test_client()

    manager_mod.ConfigManager._instance = None
    manager_mod._config_manager = None


@pytest.fixture
def open_client(tmp_path, monkeypatch):
    monkeypatch.setenv("POWERNIGHT_DATA_PATH", str(tmp_path))
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "powerwall:\n"
        "  tesla_email: open@example.com\n"
        "automation:\n"
        "  enabled: false\n"
        "  schedule: []\n"
        "web_interface:\n"
        "  enabled: true\n"
    )
    import powernight.core.config.manager as manager_mod
    manager_mod.ConfigManager._instance = None
    manager_mod._config_manager = None
    config = manager_mod.get_config_manager().load_config(str(config_path))

    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>")
    monkeypatch.setenv("POWERNIGHT_STATIC_PATH", str(static_dir))
    app = create_app(config, testing=True)
    yield app.test_client()

    manager_mod.ConfigManager._instance = None
    manager_mod._config_manager = None


@pytest.mark.unit
class TestAuthEnforcement:

    def test_api_key_automatically_enables_auth(self, auth_client):
        resp = auth_client.get("/api/v1/auth/check")
        assert resp.status_code == 401

    def test_no_credentials_allow_lan_access(self, open_client):
        resp = open_client.get("/api/v1/auth/check")
        assert resp.status_code == 200

    @pytest.mark.parametrize("path", [
        "/api/v1/status",
        "/api/v1/auth/check",
        "/api/v1/health",
        "/api/v1/tasks",
        "/api/v1/logs/executions",
        "/api/v1/backup-reserve",
        "/api/v1/config",
    ])
    def test_protected_endpoint_requires_auth(self, auth_client, path):
        resp = auth_client.get(path)
        assert resp.status_code == 401

    @pytest.mark.parametrize("path", [
        "/api/v1/status",
        "/api/v1/auth/check",
        "/api/v1/tasks",
    ])
    def test_valid_api_key_grants_access(self, auth_client, path):
        resp = auth_client.get(path, headers={"X-API-Key": API_KEY})
        assert resp.status_code != 401

    def test_wrong_api_key_rejected(self, auth_client):
        resp = auth_client.get("/api/v1/tasks", headers={"X-API-Key": "wrong"})
        assert resp.status_code == 401

    @pytest.mark.parametrize("path", ["/health", "/version"])
    def test_liveness_endpoints_public(self, auth_client, path):
        resp = auth_client.get(path)
        assert resp.status_code == 200

    def test_config_timezone_post_requires_auth(self, auth_client):
        resp = auth_client.post("/api/v1/config/timezone", json={"timezone": "UTC"})
        assert resp.status_code == 401


@pytest.mark.unit
class TestAuthenticationBoundaries:

    @pytest.mark.parametrize("client_fixture", ["open_client", "auth_client"])
    @pytest.mark.parametrize("path", [
        "/api/auth/site-details",
        "/api/auth/tesla/powerwalls",
    ])
    def test_missing_tesla_credentials_do_not_reject_app_login(
        self, request, client_fixture, path
    ):
        client = request.getfixturevalue(client_fixture)
        headers = {"X-API-Key": API_KEY} if client_fixture == "auth_client" else {}
        resp = client.get(path, headers=headers)
        assert resp.status_code == 503
        assert resp.json["success"] is False
        assert resp.json["code"] == "TESLA_AUTH_REQUIRED"
        assert resp.json["message"] == "Connect or reconnect your Tesla account in Settings."
        assert "timestamp" in resp.json
        assert client.get("/api/v1/auth/check", headers=headers).status_code == 200

    @pytest.mark.parametrize("client_fixture", ["open_client", "auth_client"])
    def test_failed_tesla_refresh_does_not_reject_app_login(
        self, request, client_fixture, monkeypatch
    ):
        client = request.getfixturevalue(client_fixture)
        from powernight.web.api import auth_api

        oauth = auth_api.oauth_manager
        monkeypatch.setattr(oauth.auth_storage, "load_auth_data", lambda: {
            "access_token": "expired-tesla-token",
        })
        monkeypatch.setattr(oauth.auth_storage, "is_token_expired", lambda data: True)
        refresh = Mock(return_value=False)
        monkeypatch.setattr(oauth, "refresh_access_token", refresh)

        headers = {"X-API-Key": API_KEY} if client_fixture == "auth_client" else {}
        resp = client.get("/api/auth/site-details", headers=headers)
        refresh.assert_called_once_with()
        assert resp.status_code == 503
        assert resp.json["code"] == "TESLA_AUTH_REQUIRED"
        assert resp.json["message"] == "Connect or reconnect your Tesla account in Settings."
        assert client.get("/api/v1/auth/check", headers=headers).status_code == 200

    @pytest.mark.parametrize("path", [
        "/api/auth/site-details",
        "/api/auth/tesla/powerwalls",
        "/api/v1/config",
    ])
    @pytest.mark.parametrize("headers", [{}, {"X-API-Key": "wrong"}])
    def test_invalid_app_credentials_are_rejected_before_tesla_access(
        self, auth_client, path, headers, monkeypatch
    ):
        from powernight.web.api import auth_api

        token_lookup = Mock()
        auth_lookup = Mock()
        monkeypatch.setattr(auth_api.oauth_manager, "get_valid_access_token", token_lookup)
        monkeypatch.setattr(auth_api.oauth_manager.auth_storage, "has_auth_data", auth_lookup)
        resp = auth_client.get(path, headers=headers)
        assert resp.status_code == 401
        assert "code" not in resp.json
        token_lookup.assert_not_called()
        auth_lookup.assert_not_called()

    @pytest.mark.parametrize("client_fixture", ["open_client", "auth_client"])
    def test_config_reads_remain_available_to_authorized_clients(
        self, request, client_fixture
    ):
        client = request.getfixturevalue(client_fixture)
        headers = {"X-API-Key": API_KEY} if client_fixture == "auth_client" else {}
        resp = client.get("/api/v1/config", headers=headers)
        assert resp.status_code == 200
        assert resp.json["success"] is True
        assert set(resp.json["data"]) == {"web", "automation", "powerwall"}
        assert resp.json["data"]["web"]["port"] == 8020


@pytest.mark.unit
class TestFailClosedStartup:

    def test_auth_enabled_without_credentials_refuses_to_start(self, tmp_path, monkeypatch):
        monkeypatch.setenv("POWERNIGHT_DATA_PATH", str(tmp_path))
        config_path = tmp_path / "config.yaml"
        config_path.write_text(
            "powerwall:\n"
            "  tesla_email: fail@example.com\n"
            "automation:\n"
            "  enabled: false\n"
            "  schedule: []\n"
            "web_interface:\n"
            "  enabled: true\n"
            "  auth_enabled: true\n"
        )
        import powernight.core.config.manager as manager_mod
        manager_mod.ConfigManager._instance = None
        manager_mod._config_manager = None

        from powernight.app import PowerNightApp
        app = PowerNightApp()
        assert app.initialize(str(config_path)) is False

        manager_mod.ConfigManager._instance = None
        manager_mod._config_manager = None


@pytest.mark.unit
class TestCredentialDrivenConfiguration:

    def test_no_credentials_leave_auth_disabled(self):
        config = PowerNightConfig.from_dict({"web_interface": {"enabled": True}})
        assert config.web_interface.auth_enabled is False

    def test_api_key_enables_auth_even_when_flag_is_false(self):
        config = PowerNightConfig.from_dict({
            "web_interface": {
                "auth_enabled": False,
                "api_key": API_KEY,
            }
        })
        assert config.web_interface.auth_enabled is True

    def test_complete_basic_credentials_enable_auth(self):
        config = PowerNightConfig.from_dict({
            "web_interface": {
                "username": "operator",
                "password": "secret",
            }
        })
        assert config.web_interface.auth_enabled is True
        assert config.validate() == []

    @pytest.mark.parametrize("credentials", [
        {"username": "operator"},
        {"password": "secret"},
    ])
    def test_incomplete_basic_credentials_are_rejected(self, credentials):
        config = PowerNightConfig.from_dict({"web_interface": credentials})
        assert any(
            "Both username and password" in error
            for error in config.validate()
        )

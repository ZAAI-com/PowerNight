"""
Authentication enforcement regression tests.

Credentials opt deployments into authentication. Protected endpoints reject
unauthenticated requests and accept a valid API key, while installations with
no credentials remain available on their trusted local network.
"""

import pytest

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

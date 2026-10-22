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


@pytest.fixture(autouse=True)
def isolated_singleton(monkeypatch):
    import powernight.core.config.manager as manager_mod
    for name in ('POWERNIGHT_API_KEY', 'POWERNIGHT_AUTH_ENABLED', 'POWERNIGHT_WEB_PORT'):
        monkeypatch.delenv(name, raising=False)
    previous = manager_mod.ConfigManager._instance, manager_mod._config_manager
    manager_mod.ConfigManager._instance = None
    manager_mod._config_manager = None
    try:
        yield
    finally:
        manager_mod.ConfigManager._instance, manager_mod._config_manager = previous


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
    config = manager_mod.get_config_manager().load_config(str(config_path))

    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>")
    monkeypatch.setenv("POWERNIGHT_STATIC_PATH", str(static_dir))
    app = create_app(config, testing=True)
    yield app.test_client()



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
    config = manager_mod.get_config_manager().load_config(str(config_path))

    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>")
    monkeypatch.setenv("POWERNIGHT_STATIC_PATH", str(static_dir))
    app = create_app(config, testing=True)
    yield app.test_client()



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

    @pytest.mark.parametrize(("path", "expected"), [
        ("/api/v1/status", 200),
        ("/api/v1/auth/check", 200),
        ("/api/v1/tasks", 200),
    ])
    def test_valid_api_key_grants_access(self, auth_client, path, expected):
        resp = auth_client.get(path, headers={"X-API-Key": API_KEY})
        assert resp.status_code == expected

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
    def test_unavailable_tesla_session_does_not_reject_app_login(
        self, request, client_fixture, monkeypatch
    ):
        client = request.getfixturevalue(client_fixture)
        from powernight.web.api import auth_api

        oauth = auth_api.oauth_manager
        monkeypatch.setattr(oauth.auth_storage, "load_auth_data", lambda: {
            "email": "owner@example.com",
            "access_token": "expired-tesla-token",
            "refresh_token": "refresh-token",
            "site": {"id": 123},
        })
        session = Mock(side_effect=RuntimeError("Tesla cloud refused the connection"))
        monkeypatch.setattr(auth_api, "_shared_cloud_session", session)

        headers = {"X-API-Key": API_KEY} if client_fixture == "auth_client" else {}
        resp = client.get("/api/auth/site-details", headers=headers)
        session.assert_called_once_with()
        assert resp.status_code == 502
        assert resp.json["success"] is False
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
        monkeypatch.setattr(auth_api.oauth_manager, "has_credentials", token_lookup)
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

        from powernight.app import PowerNightApp
        app = PowerNightApp()
        assert app.initialize(str(config_path)) is False



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


@pytest.mark.parametrize('credential', ['password', 'api_key'])
def test_numeric_yaml_credentials_are_normalized(credential):
    web = {credential: 123456}
    if credential == 'password':
        web['username'] = 'operator'
    config = PowerNightConfig.from_dict({'web_interface': web})
    assert getattr(config.web_interface, credential) == '123456'
    assert config.web_interface.auth_enabled
    assert config.validate() == []


def test_credentialless_auth_config_save_is_rejected(open_client):
    response = open_client.post('/api/v1/config', json={'web_interface': {'auth_enabled': True}})
    assert response.status_code == 400
    assert open_client.get('/api/v1/auth/check').status_code == 200


@pytest.mark.parametrize('update', [
    {'automation': {'timezone': 'not/a-zone'}},
    {'monitoring': {'health_check_interval': -1}},
])
def test_invalid_config_is_a_client_error(open_client, update):
    assert open_client.post('/api/v1/config', json=update).status_code == 400


def test_config_storage_failure_is_not_misclassified_as_bad_input(open_client, monkeypatch):
    from powernight.core.config.manager import get_config_manager
    from powernight.core.config.exceptions import ConfigurationError

    def fail(*args):
        raise ConfigurationError('private storage detail')

    monkeypatch.setattr(get_config_manager(), 'save_config', fail)
    response = open_client.post('/api/v1/config', json={'automation': {'timezone': 'UTC'}})
    assert response.status_code == 500
    assert response.json['error'] == 'Failed to update configuration'
    assert 'private storage detail' not in response.get_data(as_text=True)


SESSION = 's' * 32
SETUP_ROUTES = [
    ('post', '/api/auth/setup/start', {'email': 'owner@example.com'}),
    ('post', '/api/auth/setup/callback', {'session_id': SESSION, 'callback_url': 'tesla://auth/callback?code=a&state=b'}),
    ('post', '/api/auth/setup/tokens', {'email': 'owner@example.com', 'refresh_token': 'r', 'access_token': 'a'}),
    ('post', '/api/auth/setup/sites', {'session_id': SESSION}),
    ('post', '/api/auth/setup/complete', {'session_id': SESSION, 'site_id': '1'}),
    ('post', '/api/auth/setup/cancel', {'session_id': SESSION}),
    ('post', '/api/auth/setup/handoff', {'session_id': SESSION}),
    ('get', f'/api/auth/setup/status/{SESSION}', None),
]
LAN = {'REMOTE_ADDR': '192.168.1.50'}


@pytest.mark.unit
class TestSetupPolicy:
    """Every setup route, status included, follows the same bootstrap policy."""

    @pytest.fixture(autouse=True)
    def offline_tesla(self, monkeypatch):
        rejected = Mock(status_code=401)
        monkeypatch.setattr('powernight.core.auth.tesla_oauth.requests.get', Mock(return_value=rejected))

    @staticmethod
    def call(client, method, path, body, headers=None, environ=None):
        return getattr(client, method)(path, json=body, headers=headers or {}, environ_base=environ or {})

    @pytest.mark.parametrize('method, path, body', SETUP_ROUTES)
    def test_lan_client_without_key_is_refused(self, auth_client, method, path, body):
        response = self.call(auth_client, method, path, body, environ=LAN)
        assert response.status_code == 401
        assert response.json['error_code'] == 'APP_AUTH_REQUIRED'

    @pytest.mark.parametrize('method, path, body', SETUP_ROUTES)
    def test_loopback_bootstrap_is_allowed_without_tokens(self, auth_client, method, path, body):
        assert self.call(auth_client, method, path, body).status_code != 401

    @pytest.mark.parametrize('method, path, body', SETUP_ROUTES)
    def test_loopback_bootstrap_ends_once_tokens_exist(self, auth_client, tmp_path, method, path, body):
        from powernight.core.auth.token_storage import PyPowerwallAuthStorage
        PyPowerwallAuthStorage(str(tmp_path)).store_auth_data(
            'owner@example.com', {'access_token': 'at'}, {'id': 1}
        )
        assert self.call(auth_client, method, path, body).status_code == 401

    @pytest.mark.parametrize('method, path, body', SETUP_ROUTES)
    def test_api_key_is_allowed(self, auth_client, method, path, body):
        response = self.call(auth_client, method, path, body, headers={'X-API-Key': API_KEY}, environ=LAN)
        assert response.status_code != 401

    @pytest.mark.parametrize('method, path, body', SETUP_ROUTES)
    def test_open_installation_is_allowed(self, open_client, method, path, body):
        assert self.call(open_client, method, path, body, environ=LAN).status_code != 401

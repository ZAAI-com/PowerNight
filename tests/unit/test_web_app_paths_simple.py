"""
Simplified tests for web application static path handling.

Key behaviors covered:
1. No Docker paths are used by default
2. POWERNIGHT_STATIC_PATH is respected when the path exists
3. Fallback to the module-derived project_root/dist path works correctly
"""

from pathlib import Path

import pytest
from unittest.mock import patch

from powernight.web.app import create_app
from powernight.core.config.schema import (
    PowerNightConfig,
    PowerwallSettings,
    AutomationSettings,
    WebInterfaceSettings,
    LoggingSettings,
    MonitoringSettings,
)


def create_test_config():
    """Create a test configuration."""
    return PowerNightConfig(
        powerwall=PowerwallSettings(
            tesla_email="test@example.com"
        ),
        automation=AutomationSettings(enabled=False),
        web_interface=WebInterfaceSettings(enabled=True),
        logging=LoggingSettings(file_path="logs/powernight.log"),
        monitoring=MonitoringSettings(enabled=False)
    )


class TestWebAppPathHandling:
    """Test web application path handling in different environments."""

    def test_create_app_does_not_use_docker_paths_by_default(self, monkeypatch):
        config = create_test_config()
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        app = create_app(config, testing=True)

        assert app.static_folder != "/app/dist"
        assert not app.static_folder.startswith("/app/")
        assert app.static_folder is not None
        # Flask derives static_url_path from the folder basename (dist)
        assert app.static_url_path == "/dist"

    def test_create_app_respects_environment_variable_when_path_exists(
            self, temp_dir, monkeypatch):
        custom_static_path = temp_dir / "custom_static"
        custom_static_path.mkdir()
        monkeypatch.setenv('POWERNIGHT_STATIC_PATH', str(custom_static_path))

        app = create_app(create_test_config(), testing=True)

        assert app.static_folder == str(custom_static_path)

    def test_create_app_falls_back_when_environment_path_does_not_exist(
            self, temp_dir, monkeypatch):
        nonexistent_path = temp_dir / "nonexistent" / "static"
        monkeypatch.setenv('POWERNIGHT_STATIC_PATH', str(nonexistent_path))

        app = create_app(create_test_config(), testing=True)

        assert app.static_folder != str(nonexistent_path)
        assert app.static_folder is not None
        assert not app.static_folder.startswith("/app/")

    def test_create_app_handles_empty_environment_variable(self, monkeypatch):
        monkeypatch.setenv('POWERNIGHT_STATIC_PATH', '')

        app = create_app(create_test_config(), testing=True)

        assert app.static_folder is not None
        assert not app.static_folder.startswith("/app/")

    def test_create_app_works_with_relative_paths_in_config(self, monkeypatch):
        config = create_test_config()
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        # The config uses relative paths
        assert config.logging.file_path == "logs/powernight.log"
        assert not config.logging.file_path.startswith("/app/")

        app = create_app(config, testing=True)

        assert app is not None
        assert app.static_folder is not None
        assert app.template_folder == "templates"

    def test_create_app_initializes_all_components_correctly(self, monkeypatch):
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        with patch('powernight.web.app.init_auth_api') as mock_init_auth:
            app = create_app(create_test_config(), testing=True)

        assert app is not None
        assert app.static_folder is not None
        assert app.template_folder == "templates"
        mock_init_auth.assert_called_once_with(app)

    def test_create_app_uses_consistent_paths_across_calls(self, monkeypatch):
        config = create_test_config()
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        app1 = create_app(config, testing=True)
        app2 = create_app(config, testing=True)

        assert app1.static_folder == app2.static_folder
        assert app1.static_url_path == app2.static_url_path
        assert app1.template_folder == app2.template_folder

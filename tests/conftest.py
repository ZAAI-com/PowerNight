"""
Pytest configuration and fixtures for PowerNight tests.

This file provides common fixtures and configuration for all tests.
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture
def temp_dir():
    """Provide a temporary directory for tests."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def clean_environment():
    """Provide a clean environment without Docker-specific variables."""
    with patch.dict(os.environ, {}, clear=True):
        yield


@pytest.fixture
def mock_config_data():
    """Provide mock configuration data for tests."""
    return {
        "powerwall": {
            "tesla_email": "test@example.com"
        },
        "automation": {
            "enabled": False,
            "schedule": []
        },
        "web_interface": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 8080,
            # Endpoint-logic tests run with auth disabled; a dedicated test
            # (test_auth_enforcement) exercises the auth-on path.
            "auth_enabled": False
        },
        "logging": {
            "level": "INFO",
            "file_path": "logs/powernight.log"
        },
        "monitoring": {
            "enabled": False
        }
    }


@pytest.fixture
def config_file(temp_dir, mock_config_data):
    """Create a temporary configuration file for tests."""
    import yaml
    
    config_path = temp_dir / "config.yaml"
    with open(config_path, 'w') as f:
        yaml.dump(mock_config_data, f)
    
    return config_path


@pytest.fixture
def mock_powerwall_connector():
    """Provide a mock Powerwall connector."""
    from unittest.mock import MagicMock
    return MagicMock()


@pytest.fixture
def app_config(mock_config_data):
    """Provide a validated PowerNightConfig for tests."""
    from powernight.core.config.schema import PowerNightConfig
    return PowerNightConfig.from_dict(mock_config_data)


@pytest.fixture
def app(app_config, mock_powerwall_connector, temp_dir, monkeypatch):
    """Provide a Flask app built through the real factory in testing mode."""
    from powernight.web.app import create_app

    # Point static serving at an existing temp dir so SPA routes don't 500
    static_dir = temp_dir / "dist"
    static_dir.mkdir(exist_ok=True)
    (static_dir / "index.html").write_text("<html><body>PowerNight test</body></html>")
    monkeypatch.setenv("POWERNIGHT_STATIC_PATH", str(static_dir))

    flask_app = create_app(
        app_config,
        testing=True,
        powerwall_connector=mock_powerwall_connector,
    )
    return flask_app


@pytest.fixture
def client(app):
    """Provide a Flask test client."""
    return app.test_client()


@pytest.fixture
def mock_planner():
    """Provide a mock planner."""
    from unittest.mock import MagicMock
    planner = MagicMock()
    planner.start = MagicMock()
    planner.stop = MagicMock()
    planner.get_status = MagicMock(return_value={
        'task_count': 0,
        'is_running': False,
        'next_run': None
    })
    return planner


@pytest.fixture
def mock_flask_app():
    """Provide a mock Flask app."""
    from unittest.mock import MagicMock
    app = MagicMock()
    app.register_blueprint = MagicMock()
    app.run = MagicMock()
    return app

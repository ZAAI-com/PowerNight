"""
Tests for web application static path handling.

Current create_app behavior (src/powernight/web/app.py):
1. POWERNIGHT_STATIC_PATH wins when it is set AND the path exists on disk.
2. Otherwise the static folder is project_root/dist, computed from the
   location of the powernight.web.app module (independent of the cwd).

Flask derives static_url_path from the basename of the static folder.
"""

import os
from pathlib import Path

import pytest

import powernight.web.app as web_app_module
from powernight.web.app import create_app


def expected_default_static_folder():
    """Compute project_root/dist from the app module location.

    Mirrors the fallback logic in create_app.
    """
    web_dir = os.path.dirname(os.path.abspath(web_app_module.__file__))
    powernight_dir = os.path.dirname(web_dir)
    src_dir = os.path.dirname(powernight_dir)
    project_root = os.path.dirname(src_dir)
    return os.path.join(project_root, 'dist')


class TestWebAppPathHandling:
    """Test static path resolution in different environments."""

    def test_default_static_path_derived_from_module_location(
            self, app_config, monkeypatch):
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        app = create_app(app_config, testing=True)

        assert app.static_folder == expected_default_static_folder()
        assert app.static_url_path == '/dist'

    def test_default_static_path_independent_of_cwd(
            self, app_config, temp_dir, monkeypatch):
        """The fallback path comes from the module location, not the cwd."""
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)
        monkeypatch.chdir(temp_dir)

        app = create_app(app_config, testing=True)

        assert app.static_folder == expected_default_static_folder()
        assert not app.static_folder.startswith(str(temp_dir))

    def test_environment_variable_wins_when_path_exists(
            self, app_config, temp_dir, monkeypatch):
        custom_static_path = temp_dir / 'custom_static'
        custom_static_path.mkdir()
        monkeypatch.setenv('POWERNIGHT_STATIC_PATH', str(custom_static_path))

        app = create_app(app_config, testing=True)

        assert app.static_folder == str(custom_static_path)
        assert app.static_url_path == '/custom_static'

    def test_environment_variable_ignored_when_path_missing(
            self, app_config, temp_dir, monkeypatch):
        nonexistent_path = temp_dir / 'nonexistent' / 'static'
        monkeypatch.setenv('POWERNIGHT_STATIC_PATH', str(nonexistent_path))

        app = create_app(app_config, testing=True)

        assert app.static_folder != str(nonexistent_path)
        assert app.static_folder == expected_default_static_folder()

    def test_empty_environment_variable_falls_back_to_default(
            self, app_config, monkeypatch):
        monkeypatch.setenv('POWERNIGHT_STATIC_PATH', '')

        app = create_app(app_config, testing=True)

        assert app.static_folder == expected_default_static_folder()

    def test_no_docker_path_by_default(self, app_config, monkeypatch):
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        app = create_app(app_config, testing=True)

        assert app.static_folder != '/app/dist'
        assert not app.static_folder.startswith('/app/')


class TestWebAppPathIntegration:
    """Integration behavior of create_app around path handling."""

    def test_create_app_succeeds_when_dist_missing(
            self, app_config, monkeypatch):
        """App creation must not fail just because dist/ does not exist."""
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        app = create_app(app_config, testing=True)

        assert app is not None
        assert app.static_folder is not None

    def test_path_consistency_across_calls(self, app_config, monkeypatch):
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        app1 = create_app(app_config, testing=True)
        app2 = create_app(app_config, testing=True)

        assert app1.static_folder == app2.static_folder
        assert app1.static_folder == expected_default_static_folder()

    def test_create_app_sets_testing_flag(self, app_config, monkeypatch):
        monkeypatch.delenv('POWERNIGHT_STATIC_PATH', raising=False)

        app = create_app(app_config, testing=True)

        assert app.testing is True

"""
Tests for auth API path handling to prevent Docker container path bugs.

These tests ensure that the auth API uses proper development paths
and doesn't rely on Docker container paths when running locally.
"""

import os
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from powernight.web.api.auth_api import init_auth_api
from powernight.core.auth.tesla_oauth import TeslaOAuthManager


class TestAuthAPIPathHandling:
    """Test auth API path handling in different environments."""

    def test_init_auth_api_uses_relative_path_by_default(self):
        """Test that init_auth_api uses relative path by default."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock Flask app
                mock_app = MagicMock()
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock TeslaOAuthManager to avoid actual initialization
                    with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                        mock_oauth_instance = MagicMock()
                        mock_oauth.return_value = mock_oauth_instance
                        
                        # Call init_auth_api
                        init_auth_api(mock_app)
                        
                        # Verify TeslaOAuthManager was called with relative path
                        mock_oauth.assert_called_once_with(storage_path='data')
                        
                        # Verify blueprint was registered
                        mock_app.register_blueprint.assert_called_once()
                        
            finally:
                os.chdir(original_cwd)

    def test_init_auth_api_respects_environment_variable(self):
        """Test that init_auth_api respects POWERNIGHT_DATA_PATH environment variable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            custom_path = str(Path(temp_dir) / "custom_data")
            
            # Mock Flask app
            mock_app = MagicMock()
            
            # Set environment variable
            with patch.dict(os.environ, {'POWERNIGHT_DATA_PATH': custom_path}):
                # Mock TeslaOAuthManager to avoid actual initialization
                with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                    mock_oauth_instance = MagicMock()
                    mock_oauth.return_value = mock_oauth_instance
                    
                    # Call init_auth_api
                    init_auth_api(mock_app)
                    
                    # Verify TeslaOAuthManager was called with custom path
                    mock_oauth.assert_called_once_with(storage_path=custom_path)

    def test_init_auth_api_does_not_use_docker_paths_by_default(self):
        """Test that init_auth_api does not use Docker paths by default."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock Flask app
                mock_app = MagicMock()
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock TeslaOAuthManager to avoid actual initialization
                    with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                        mock_oauth_instance = MagicMock()
                        mock_oauth.return_value = mock_oauth_instance
                        
                        # Call init_auth_api
                        init_auth_api(mock_app)
                        
                        # Verify TeslaOAuthManager was NOT called with Docker path
                        mock_oauth.assert_called_once()
                        call_args = mock_oauth.call_args
                        storage_path = call_args[1]['storage_path']
                        
                        assert storage_path != '/app/data'
                        assert not storage_path.startswith('/app/')
                        assert storage_path == 'data'  # Should use relative path
                        
            finally:
                os.chdir(original_cwd)

    def test_auth_api_works_with_relative_paths(self):
        """Test that auth API works correctly with relative paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Create data directory
                data_dir = Path(temp_dir) / "data"
                data_dir.mkdir()
                
                # Mock Flask app
                mock_app = MagicMock()
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock TeslaOAuthManager to avoid actual initialization
                    with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                        mock_oauth_instance = MagicMock()
                        mock_oauth.return_value = mock_oauth_instance
                        
                        # Call init_auth_api
                        init_auth_api(mock_app)
                        
                        # Verify the call was successful
                        mock_oauth.assert_called_once()
                        mock_app.register_blueprint.assert_called_once()
                        
            finally:
                os.chdir(original_cwd)

    def test_auth_api_handles_absolute_paths_when_specified(self):
        """Test that auth API handles absolute paths when explicitly specified."""
        with tempfile.TemporaryDirectory() as temp_dir:
            absolute_path = str(Path(temp_dir) / "absolute_data")
            
            # Mock Flask app
            mock_app = MagicMock()
            
            # Set environment variable to absolute path
            with patch.dict(os.environ, {'POWERNIGHT_DATA_PATH': absolute_path}):
                # Mock TeslaOAuthManager to avoid actual initialization
                with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                    mock_oauth_instance = MagicMock()
                    mock_oauth.return_value = mock_oauth_instance
                    
                    # Call init_auth_api
                    init_auth_api(mock_app)
                    
                    # Verify TeslaOAuthManager was called with absolute path
                    mock_oauth.assert_called_once_with(storage_path=absolute_path)

    def test_auth_api_initialization_does_not_fail_with_relative_paths(self):
        """Test that auth API initialization doesn't fail with relative paths."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock Flask app
                mock_app = MagicMock()
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock TeslaOAuthManager to avoid actual initialization
                    with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                        mock_oauth_instance = MagicMock()
                        mock_oauth.return_value = mock_oauth_instance
                        
                        # This should not raise any exceptions
                        try:
                            init_auth_api(mock_app)
                            success = True
                        except Exception as e:
                            success = False
                            pytest.fail(f"init_auth_api failed with relative paths: {e}")
                        
                        assert success
                        
            finally:
                os.chdir(original_cwd)


class TestAuthAPIPathEdgeCases:
    """Test edge cases in auth API path handling."""

    def test_auth_api_handles_empty_environment_variable(self):
        """Test that auth API handles empty environment variable gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock Flask app
                mock_app = MagicMock()
                
                # Set empty environment variable
                with patch.dict(os.environ, {'POWERNIGHT_DATA_PATH': ''}):
                    # Mock TeslaOAuthManager to avoid actual initialization
                    with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                        mock_oauth_instance = MagicMock()
                        mock_oauth.return_value = mock_oauth_instance
                        
                        # Call init_auth_api
                        init_auth_api(mock_app)
                        
                        # Should use empty string as specified
                        mock_oauth.assert_called_once_with(storage_path='')
                        
            finally:
                os.chdir(original_cwd)

    def test_auth_api_handles_nonexistent_paths(self):
        """Test that auth API handles nonexistent paths gracefully."""
        with tempfile.TemporaryDirectory() as temp_dir:
            nonexistent_path = str(Path(temp_dir) / "nonexistent" / "data")
            
            # Mock Flask app
            mock_app = MagicMock()
            
            # Set environment variable to nonexistent path
            with patch.dict(os.environ, {'POWERNIGHT_DATA_PATH': nonexistent_path}):
                # Mock TeslaOAuthManager to avoid actual initialization
                with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                    mock_oauth_instance = MagicMock()
                    mock_oauth.return_value = mock_oauth_instance
                    
                    # This should not raise an exception during initialization
                    # (TeslaOAuthManager should handle path creation)
                    try:
                        init_auth_api(mock_app)
                        success = True
                    except Exception as e:
                        success = False
                        pytest.fail(f"init_auth_api failed with nonexistent path: {e}")
                    
                    assert success
                    mock_oauth.assert_called_once_with(storage_path=nonexistent_path)

    def test_auth_api_works_in_different_working_directories(self):
        """Test that auth API works correctly in different working directories."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create subdirectory
            subdir = Path(temp_dir) / "subdir"
            subdir.mkdir()
            
            original_cwd = os.getcwd()
            try:
                # Test in subdirectory
                os.chdir(subdir)
                
                # Mock Flask app
                mock_app = MagicMock()
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock TeslaOAuthManager to avoid actual initialization
                    with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                        mock_oauth_instance = MagicMock()
                        mock_oauth.return_value = mock_oauth_instance
                        
                        # Call init_auth_api
                        init_auth_api(mock_app)
                        
                        # Should still use relative path
                        mock_oauth.assert_called_once_with(storage_path='data')
                        
            finally:
                os.chdir(original_cwd)


class TestAuthAPIPathIntegration:
    """Integration tests for auth API path handling."""

    def test_auth_api_integration_with_flask_app(self):
        """Test auth API integration with Flask app initialization."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock Flask app with more realistic behavior
                mock_app = MagicMock()
                mock_app.register_blueprint = MagicMock()
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock TeslaOAuthManager to avoid actual initialization
                    with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                        mock_oauth_instance = MagicMock()
                        mock_oauth.return_value = mock_oauth_instance
                        
                        # Call init_auth_api
                        init_auth_api(mock_app)
                        
                        # Verify all expected calls were made
                        mock_oauth.assert_called_once_with(storage_path='data')
                        mock_app.register_blueprint.assert_called_once()
                        
                        # Verify the global oauth_manager was set
                        from powernight.web.api.auth_api import oauth_manager
                        assert oauth_manager is not None
                        
            finally:
                os.chdir(original_cwd)

    def test_auth_api_path_consistency_across_calls(self):
        """Test that auth API uses consistent paths across multiple calls."""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                
                # Mock Flask app
                mock_app = MagicMock()
                
                # Clear any existing environment variable
                with patch.dict(os.environ, {}, clear=True):
                    # Mock TeslaOAuthManager to avoid actual initialization
                    with patch('powernight.web.api.auth_api.TeslaOAuthManager') as mock_oauth:
                        mock_oauth_instance = MagicMock()
                        mock_oauth.return_value = mock_oauth_instance
                        
                        # Call init_auth_api multiple times
                        init_auth_api(mock_app)
                        init_auth_api(mock_app)
                        
                        # Should use same path each time
                        assert mock_oauth.call_count == 2
                        for call in mock_oauth.call_args_list:
                            assert call[1]['storage_path'] == 'data'
                        
            finally:
                os.chdir(original_cwd)

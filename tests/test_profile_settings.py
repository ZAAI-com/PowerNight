"""
Tests for profile settings functionality.

Tests the database models, services, and API endpoints for profile management.
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

# Mock SQLAlchemy to avoid import errors during testing
with patch.dict('sys.modules', {
    'sqlalchemy': MagicMock(),
    'sqlalchemy.orm': MagicMock(),
    'sqlalchemy.ext.declarative': MagicMock(),
    'sqlalchemy.dialects.postgresql': MagicMock(),
    'sqlalchemy.sql': MagicMock(),
    'sqlalchemy.pool': MagicMock(),
    'sqlalchemy.exc': MagicMock(),
}):
    from src.powernight.core.database.models import PowerwallProfile, ProfileSettings
    from src.powernight.core.database.services import ProfileService, SettingsService
    from src.powernight.core.database.exceptions import ProfileNotFoundError, DuplicateProfileError


class TestProfileSettings:
    """Test profile settings functionality."""
    
    def test_profile_creation(self):
        """Test creating a new profile."""
        # Mock database session
        mock_session = MagicMock()
        
        # Create profile service with mocked session
        profile_service = ProfileService(session=mock_session)
        
        # Mock the database operations
        mock_session.query.return_value.filter.return_value.first.return_value = None  # No existing profile
        mock_session.add.return_value = None
        mock_session.flush.return_value = None
        mock_session.commit.return_value = None
        
        # Create a profile
        profile = profile_service.create_profile(
            user_id="test_user",
            name="Test Powerwall",
            ip_address="192.168.1.100",
            email="test@example.com",
            password="test-password",
            auth_method="local",
            verify_ssl=True,
            timeout=30,
            retry_attempts=3,
            is_demo=False
        )
        
        # Verify profile was created
        assert profile is not None
        assert profile.name == "Test Powerwall"
        assert profile.ip_address == "192.168.1.100"
        assert profile.email == "test@example.com"
        assert profile.auth_method == "local"
        assert profile.verify_ssl == True
        assert profile.is_demo == False
    
    def test_duplicate_profile_error(self):
        """Test that creating a duplicate profile raises an error."""
        # Mock database session
        mock_session = MagicMock()
        
        # Create profile service with mocked session
        profile_service = ProfileService(session=mock_session)
        
        # Mock existing profile found
        existing_profile = MagicMock()
        existing_profile.name = "Test Powerwall"
        mock_session.query.return_value.filter.return_value.first.return_value = existing_profile
        
        # Attempt to create duplicate profile
        with pytest.raises(DuplicateProfileError):
            profile_service.create_profile(
                user_id="test_user",
                name="Test Powerwall",  # Same name
                ip_address="192.168.1.100",
                email="test@example.com",
                password="test-password"
            )
    
    def test_profile_not_found_error(self):
        """Test that getting a non-existent profile raises an error."""
        # Mock database session
        mock_session = MagicMock()
        
        # Create profile service with mocked session
        profile_service = ProfileService(session=mock_session)
        
        # Mock no profile found
        mock_session.query.return_value.filter.return_value.first.return_value = None
        
        # Attempt to get non-existent profile
        with pytest.raises(ProfileNotFoundError):
            profile_service.get_profile("non-existent-id", "test_user")
    
    def test_settings_creation(self):
        """Test creating profile settings."""
        # Mock database session
        mock_session = MagicMock()
        
        # Create settings service with mocked session
        settings_service = SettingsService(session=mock_session)
        
        # Mock the database operations
        mock_session.query.return_value.filter.return_value.first.return_value = None  # No existing settings
        mock_session.add.return_value = None
        mock_session.commit.return_value = None
        
        # Create settings
        settings_data = {
            'powerwall': {
                'ip_address': '192.168.1.100',
                'email': 'test@example.com',
                'auth_method': 'local',
                'verify_ssl': True,
                'timeout': 30,
                'retry_attempts': 3
            },
            'automation': {
                'enabled': False,
                'dry_run_mode': True,
                'polling_interval': 30,
                'backup_retention': 30
            }
        }
        
        settings = settings_service.update_settings("test-profile-id", settings_data)
        
        # Verify settings were created
        assert settings is not None
        assert settings.get_powerwall_settings() == settings_data['powerwall']
        assert settings.get_automation_settings() == settings_data['automation']


class TestProfileSettingsAPI:
    """Test profile settings API endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client."""
        from src.powernight.web.app import create_app
        app = create_app(testing=True)
        return app.test_client()
    
    def test_get_profile_configuration_no_profile(self, client):
        """Test getting configuration when no profile is active."""
        with patch('src.powernight.web.api.api._get_active_profile_id', return_value=None):
            with patch('src.powernight.web.api.api.get_config') as mock_get_config:
                # Mock global config
                mock_config = MagicMock()
                mock_config.powerwall.ip_address = "10.0.0.30"
                mock_config.powerwall.email = "demo@example.com"
                mock_config.powerwall.verify_ssl = False
                mock_config.powerwall.timeout = 30
                mock_config.powerwall.retry_attempts = 3
                mock_config.automation.enabled = False
                mock_config.automation.check_interval = 30
                mock_config.web_interface.host = "0.0.0.0"
                mock_config.web_interface.port = 5001
                mock_config.web_interface.debug = True
                mock_config.logging.level = "INFO"
                mock_config.logging.max_files = 10
                mock_config.logging.max_size_mb = 10
                mock_get_config.return_value = mock_config
                
                response = client.get('/api/v1/config/profile')
                
                assert response.status_code == 200
                data = json.loads(response.data)
                assert data['success'] == True
                assert data['is_global'] == True
                assert data['profile_id'] is None
                assert 'powerwall' in data['data']
                assert 'automation' in data['data']
    
    def test_get_profile_configuration_with_profile(self, client):
        """Test getting configuration when a profile is active."""
        with patch('src.powernight.web.api.api._get_active_profile_id', return_value="test-profile-id"):
            with patch('src.powernight.web.api.api.profile_service') as mock_profile_service:
                with patch('src.powernight.web.api.api.settings_service') as mock_settings_service:
                    # Mock profile
                    mock_profile = MagicMock()
                    mock_profile.name = "Test Powerwall"
                    mock_profile_service.get_profile.return_value = mock_profile
                    
                    # Mock settings
                    mock_settings = MagicMock()
                    mock_settings.to_dict.return_value = {
                        'powerwall': {'ip_address': '192.168.1.100'},
                        'automation': {'enabled': True}
                    }
                    mock_settings_service.get_settings.return_value = mock_settings
                    
                    response = client.get('/api/v1/config/profile')
                    
                    assert response.status_code == 200
                    data = json.loads(response.data)
                    assert data['success'] == True
                    assert data['is_global'] == False
                    assert data['profile_id'] == "test-profile-id"
                    assert data['profile_name'] == "Test Powerwall"
    
    def test_update_profile_configuration(self, client):
        """Test updating profile configuration."""
        with patch('src.powernight.web.api.api._get_active_profile_id', return_value="test-profile-id"):
            with patch('src.powernight.web.api.api.profile_service') as mock_profile_service:
                with patch('src.powernight.web.api.api.settings_service') as mock_settings_service:
                    # Mock profile
                    mock_profile = MagicMock()
                    mock_profile.name = "Test Powerwall"
                    mock_profile_service.get_profile.return_value = mock_profile
                    
                    # Mock settings update
                    mock_settings = MagicMock()
                    mock_settings.to_dict.return_value = {
                        'powerwall': {'ip_address': '192.168.1.100'},
                        'automation': {'enabled': True}
                    }
                    mock_settings_service.update_settings.return_value = mock_settings
                    
                    update_data = {
                        'powerwall': {'ip_address': '192.168.1.101'},
                        'automation': {'enabled': False}
                    }
                    
                    response = client.put(
                        '/api/v1/config/profile',
                        data=json.dumps(update_data),
                        content_type='application/json'
                    )
                    
                    assert response.status_code == 200
                    data = json.loads(response.data)
                    assert data['success'] == True
                    assert data['profile_id'] == "test-profile-id"
                    assert data['profile_name'] == "Test Powerwall"
    
    def test_update_profile_configuration_no_profile(self, client):
        """Test updating configuration when no profile is active."""
        with patch('src.powernight.web.api.api._get_active_profile_id', return_value=None):
            update_data = {
                'powerwall': {'ip_address': '192.168.1.101'}
            }
            
            response = client.put(
                '/api/v1/config/profile',
                data=json.dumps(update_data),
                content_type='application/json'
            )
            
            assert response.status_code == 400
            data = json.loads(response.data)
            assert data['success'] == False
            assert 'No active profile' in data['message']


if __name__ == "__main__":
    pytest.main([__file__])

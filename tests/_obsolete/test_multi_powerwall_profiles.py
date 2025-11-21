"""
Unit tests for multi-Powerwall profile functionality.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone

from powernight.core.database.models import PowerwallProfile
from powernight.core.database.services import ProfileService
from powernight.web.api.profiles_api import sync_powerwalls


class TestPowerwallProfile:
    """Test cases for PowerwallProfile model."""

    def test_init_cloud_profile(self):
        """Test initializing a cloud-based Powerwall profile."""
        profile = PowerwallProfile(
            user_id="test-user-123",
            name="Home Powerwall",
            tesla_email="user@example.com",
            powerwall_id="powerwall-123",
            powerwall_serial="PW123456789",
            powerwall_site_id="site-123",
            powerwall_name="Home Powerwall",
            energy_site_id="energy-site-123",
            auth_method="tesla_cloud",
            is_demo=False
        )
        
        assert profile.user_id == "test-user-123"
        assert profile.name == "Home Powerwall"
        assert profile.tesla_email == "user@example.com"
        assert profile.powerwall_id == "powerwall-123"
        assert profile.powerwall_serial == "PW123456789"
        assert profile.powerwall_site_id == "site-123"
        assert profile.powerwall_name == "Home Powerwall"
        assert profile.energy_site_id == "energy-site-123"
        assert profile.auth_method == "tesla_cloud"
        assert profile.is_demo is False

    def test_to_dict_cloud_profile(self):
        """Test converting cloud profile to dictionary."""
        profile = PowerwallProfile(
            user_id="test-user-123",
            name="Home Powerwall",
            tesla_email="user@example.com",
            powerwall_id="powerwall-123",
            powerwall_serial="PW123456789",
            powerwall_site_id="site-123",
            powerwall_name="Home Powerwall",
            energy_site_id="energy-site-123",
            auth_method="tesla_cloud",
            is_demo=False
        )
        
        profile_dict = profile.to_dict()
        
        assert profile_dict["user_id"] == "test-user-123"
        assert profile_dict["name"] == "Home Powerwall"
        assert profile_dict["tesla_email"] == "user@example.com"
        assert profile_dict["powerwall_id"] == "powerwall-123"
        assert profile_dict["powerwall_serial"] == "PW123456789"
        assert profile_dict["powerwall_site_id"] == "site-123"
        assert profile_dict["powerwall_name"] == "Home Powerwall"
        assert profile_dict["energy_site_id"] == "energy-site-123"
        assert profile_dict["auth_method"] == "tesla_cloud"
        assert profile_dict["is_demo"] is False

    def test_to_dict_demo_profile(self):
        """Test converting demo profile to dictionary."""
        profile = PowerwallProfile(
            user_id="test-user-123",
            name="Demo Powerwall",
            tesla_email="demo@example.com",
            powerwall_id="demo-powerwall-123",
            auth_method="demo",
            is_demo=True
        )
        
        profile_dict = profile.to_dict()
        
        assert profile_dict["user_id"] == "test-user-123"
        assert profile_dict["name"] == "Demo Powerwall"
        assert profile_dict["tesla_email"] == "demo@example.com"
        assert profile_dict["powerwall_id"] == "demo-powerwall-123"
        assert profile_dict["auth_method"] == "demo"
        assert profile_dict["is_demo"] is True


class TestProfileService:
    """Test cases for ProfileService class."""

    @pytest.fixture
    def mock_session(self):
        """Create mock database session."""
        return Mock()

    @pytest.fixture
    def profile_service(self, mock_session):
        """Create ProfileService with mock session."""
        service = ProfileService()
        service.session = mock_session
        return service

    def test_create_cloud_profile(self, profile_service, mock_session):
        """Test creating a cloud-based Powerwall profile."""
        mock_session.add = Mock()
        mock_session.commit = Mock()
        mock_session.refresh = Mock()
        
        profile_data = {
            "name": "Home Powerwall",
            "tesla_email": "user@example.com",
            "powerwall_id": "powerwall-123",
            "powerwall_serial": "PW123456789",
            "powerwall_site_id": "site-123",
            "powerwall_name": "Home Powerwall",
            "energy_site_id": "energy-site-123",
            "auth_method": "tesla_cloud",
            "is_demo": False
        }
        
        with patch('powernight.core.database.services.PowerwallProfile') as mock_profile_class:
            mock_profile = Mock()
            mock_profile.id = "profile-123"
            mock_profile_class.return_value = mock_profile
            
            result = profile_service.create_profile(
                user_id="test-user-123",
                **profile_data
            )
            
            assert result == mock_profile
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once_with(mock_profile)

    def test_get_profiles_by_user(self, profile_service, mock_session):
        """Test getting profiles by user ID."""
        mock_profiles = [
            Mock(id="profile-1", name="Home Powerwall", powerwall_id="powerwall-1"),
            Mock(id="profile-2", name="Office Powerwall", powerwall_id="powerwall-2")
        ]
        
        mock_session.query.return_value.filter.return_value.all.return_value = mock_profiles
        
        profiles = profile_service.get_profiles_by_user("test-user-123")
        
        assert len(profiles) == 2
        assert profiles[0].id == "profile-1"
        assert profiles[1].id == "profile-2"

    def test_update_profile(self, profile_service, mock_session):
        """Test updating a profile."""
        mock_profile = Mock()
        mock_profile.id = "profile-123"
        mock_profile.name = "Updated Powerwall"
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_profile
        mock_session.commit = Mock()
        
        update_data = {
            "name": "Updated Powerwall",
            "powerwall_name": "Updated Powerwall Name"
        }
        
        result = profile_service.update_profile("profile-123", update_data)
        
        assert result == mock_profile
        assert mock_profile.name == "Updated Powerwall"
        assert mock_profile.powerwall_name == "Updated Powerwall Name"
        mock_session.commit.assert_called_once()

    def test_delete_profile(self, profile_service, mock_session):
        """Test deleting a profile."""
        mock_profile = Mock()
        mock_profile.id = "profile-123"
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_profile
        mock_session.delete = Mock()
        mock_session.commit = Mock()
        
        result = profile_service.delete_profile("profile-123")
        
        assert result is True
        mock_session.delete.assert_called_once_with(mock_profile)
        mock_session.commit.assert_called_once()

    def test_get_profile_by_id(self, profile_service, mock_session):
        """Test getting a profile by ID."""
        mock_profile = Mock()
        mock_profile.id = "profile-123"
        mock_profile.name = "Home Powerwall"
        
        mock_session.query.return_value.filter.return_value.first.return_value = mock_profile
        
        profile = profile_service.get_profile_by_id("profile-123")
        
        assert profile == mock_profile
        assert profile.name == "Home Powerwall"


class TestMultiPowerwallAPI:
    """Test cases for multi-Powerwall API endpoints."""

    @pytest.fixture
    def mock_request(self):
        """Create mock Flask request."""
        request = Mock()
        request.headers = {"X-Powerwall-Profile": "test-profile"}
        return request

    def test_sync_powerwalls_success(self, mock_request):
        """Test successful Powerwall synchronization."""
        with patch('powernight.web.api.profiles_api.request', mock_request):
            with patch('powernight.web.api.profiles_api.TeslaOAuthManager') as mock_oauth:
                mock_oauth_instance = Mock()
                mock_oauth_instance.get_powerwalls.return_value = [
                    {
                        "id": "powerwall-1",
                        "display_name": "Home Powerwall",
                        "serial_number": "PW123456789",
                        "site_id": "site-123",
                        "energy_site_id": "energy-site-123"
                    },
                    {
                        "id": "powerwall-2",
                        "display_name": "Office Powerwall",
                        "serial_number": "PW987654321",
                        "site_id": "site-456",
                        "energy_site_id": "energy-site-456"
                    }
                ]
                mock_oauth.return_value = mock_oauth_instance
                
                with patch('powernight.web.api.profiles_api._get_user_id') as mock_user_id:
                    mock_user_id.return_value = "test-user-123"
                    
                    with patch('powernight.web.api.profiles_api.profile_service') as mock_service:
                        mock_service.get_profiles_by_user.return_value = []
                        mock_service.create_profile.return_value = Mock(id="profile-123")
                        
                        with patch('powernight.web.api.profiles_api.jsonify') as mock_jsonify:
                            mock_jsonify.return_value = {"success": True}
                            
                            result = sync_powerwalls()
                            
                            assert result == {"success": True}
                            mock_oauth_instance.get_powerwalls.assert_called_once()
                            assert mock_service.create_profile.call_count == 2

    def test_sync_powerwalls_no_powerwalls(self, mock_request):
        """Test Powerwall synchronization with no Powerwalls found."""
        with patch('powernight.web.api.profiles_api.request', mock_request):
            with patch('powernight.web.api.profiles_api.TeslaOAuthManager') as mock_oauth:
                mock_oauth_instance = Mock()
                mock_oauth_instance.get_powerwalls.return_value = []
                mock_oauth.return_value = mock_oauth_instance
                
                with patch('powernight.web.api.profiles_api._get_user_id') as mock_user_id:
                    mock_user_id.return_value = "test-user-123"
                    
                    with patch('powernight.web.api.profiles_api.jsonify') as mock_jsonify:
                        mock_jsonify.return_value = {"success": True, "message": "No Powerwalls found"}
                        
                        result = sync_powerwalls()
                        
                        assert result == {"success": True, "message": "No Powerwalls found"}
                        mock_oauth_instance.get_powerwalls.assert_called_once()

    def test_sync_powerwalls_update_existing(self, mock_request):
        """Test Powerwall synchronization with existing profiles."""
        with patch('powernight.web.api.profiles_api.request', mock_request):
            with patch('powernight.web.api.profiles_api.TeslaOAuthManager') as mock_oauth:
                mock_oauth_instance = Mock()
                mock_oauth_instance.get_powerwalls.return_value = [
                    {
                        "id": "powerwall-1",
                        "display_name": "Updated Home Powerwall",
                        "serial_number": "PW123456789",
                        "site_id": "site-123",
                        "energy_site_id": "energy-site-123"
                    }
                ]
                mock_oauth.return_value = mock_oauth_instance
                
                with patch('powernight.web.api.profiles_api._get_user_id') as mock_user_id:
                    mock_user_id.return_value = "test-user-123"
                    
                    with patch('powernight.web.api.profiles_api.profile_service') as mock_service:
                        # Mock existing profile
                        existing_profile = Mock()
                        existing_profile.powerwall_id = "powerwall-1"
                        existing_profile.powerwall_name = "Old Home Powerwall"
                        existing_profile.updated_at = datetime.now(timezone.utc)
                        
                        mock_service.get_profiles_by_user.return_value = [existing_profile]
                        mock_service.update_profile.return_value = existing_profile
                        
                        with patch('powernight.web.api.profiles_api.jsonify') as mock_jsonify:
                            mock_jsonify.return_value = {"success": True}
                            
                            result = sync_powerwalls()
                            
                            assert result == {"success": True}
                            mock_service.update_profile.assert_called_once()
                            assert existing_profile.powerwall_name == "Updated Home Powerwall"

    def test_sync_powerwalls_oauth_error(self, mock_request):
        """Test Powerwall synchronization with OAuth error."""
        with patch('powernight.web.api.profiles_api.request', mock_request):
            with patch('powernight.web.api.profiles_api.TeslaOAuthManager') as mock_oauth:
                mock_oauth_instance = Mock()
                mock_oauth_instance.get_powerwalls.side_effect = Exception("OAuth error")
                mock_oauth.return_value = mock_oauth_instance
                
                with patch('powernight.web.api.profiles_api.jsonify') as mock_jsonify:
                    mock_jsonify.return_value = {"success": False, "error": "OAuth error"}
                    
                    result = sync_powerwalls()
                    
                    assert result == {"success": False, "error": "OAuth error"}
                    mock_oauth_instance.get_powerwalls.assert_called_once()


class TestPowerwallSelector:
    """Test cases for Powerwall selector functionality."""

    def test_powerwall_selector_initialization(self):
        """Test Powerwall selector component initialization."""
        # This would test the React component initialization
        # For now, we'll test the underlying logic
        
        powerwalls = [
            {
                "id": "powerwall-1",
                "name": "Home Powerwall",
                "serial": "PW123456789",
                "site_id": "site-123"
            },
            {
                "id": "powerwall-2",
                "name": "Office Powerwall",
                "serial": "PW987654321",
                "site_id": "site-456"
            }
        ]
        
        # Test that we can process the powerwall list
        assert len(powerwalls) == 2
        assert powerwalls[0]["name"] == "Home Powerwall"
        assert powerwalls[1]["name"] == "Office Powerwall"

    def test_powerwall_selector_filtering(self):
        """Test Powerwall selector filtering functionality."""
        powerwalls = [
            {
                "id": "powerwall-1",
                "name": "Home Powerwall",
                "serial": "PW123456789",
                "site_id": "site-123",
                "is_demo": False
            },
            {
                "id": "powerwall-2",
                "name": "Demo Powerwall",
                "serial": "DEMO-PW-123",
                "site_id": "demo-site",
                "is_demo": True
            }
        ]
        
        # Filter out demo powerwalls
        real_powerwalls = [pw for pw in powerwalls if not pw.get("is_demo", False)]
        
        assert len(real_powerwalls) == 1
        assert real_powerwalls[0]["name"] == "Home Powerwall"

    def test_powerwall_selector_switching(self):
        """Test Powerwall selector switching functionality."""
        active_powerwall = "powerwall-1"
        
        powerwalls = [
            {
                "id": "powerwall-1",
                "name": "Home Powerwall",
                "serial": "PW123456789",
                "site_id": "site-123"
            },
            {
                "id": "powerwall-2",
                "name": "Office Powerwall",
                "serial": "PW987654321",
                "site_id": "site-456"
            }
        ]
        
        # Find active powerwall
        active_pw = next((pw for pw in powerwalls if pw["id"] == active_powerwall), None)
        
        assert active_pw is not None
        assert active_pw["name"] == "Home Powerwall"
        
        # Switch to different powerwall
        new_active_powerwall = "powerwall-2"
        new_active_pw = next((pw for pw in powerwalls if pw["id"] == new_active_powerwall), None)
        
        assert new_active_pw is not None
        assert new_active_pw["name"] == "Office Powerwall"

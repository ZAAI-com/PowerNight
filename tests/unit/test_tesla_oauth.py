"""
Unit tests for Tesla OAuth functionality.
"""

import pytest
import json
import tempfile
import os
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone, timedelta

from powernight.core.auth.tesla_oauth import TeslaOAuthManager, TeslaOAuthError
from powernight.core.auth.token_storage import TokenStorage, TokenStorageError


class TestTokenStorage:
    """Test cases for TokenStorage class."""

    @pytest.fixture
    def temp_storage_path(self):
        """Create temporary storage path for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_init_creates_directory(self, temp_storage_path):
        """Test that initialization creates storage directory."""
        storage = TokenStorage(storage_path=temp_storage_path)
        assert os.path.exists(temp_storage_path)
        assert os.path.exists(os.path.join(temp_storage_path, "encryption.key"))

    def test_save_and_load_tokens(self, temp_storage_path):
        """Test saving and loading tokens."""
        storage = TokenStorage(storage_path=temp_storage_path)
        
        test_tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "token_type": "Bearer"
        }
        
        # Save tokens
        storage.save_tokens("test@example.com", test_tokens)
        
        # Load tokens
        loaded_tokens = storage.load_tokens("test@example.com")
        
        assert loaded_tokens is not None
        assert loaded_tokens["access_token"] == "test_access_token"
        assert loaded_tokens["refresh_token"] == "test_refresh_token"
        assert loaded_tokens["expires_in"] == 3600

    def test_load_nonexistent_tokens(self, temp_storage_path):
        """Test loading tokens that don't exist."""
        storage = TokenStorage(storage_path=temp_storage_path)
        loaded_tokens = storage.load_tokens("nonexistent@example.com")
        assert loaded_tokens is None

    def test_delete_tokens(self, temp_storage_path):
        """Test deleting tokens."""
        storage = TokenStorage(storage_path=temp_storage_path)
        
        test_tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600
        }
        
        # Save tokens
        storage.save_tokens("test@example.com", test_tokens)
        
        # Verify tokens exist
        assert storage.load_tokens("test@example.com") is not None
        
        # Delete tokens
        storage.delete_tokens("test@example.com")
        
        # Verify tokens are deleted
        assert storage.load_tokens("test@example.com") is None

    def test_token_expiration_check(self, temp_storage_path):
        """Test token expiration checking."""
        storage = TokenStorage(storage_path=temp_storage_path)
        
        # Test expired token
        expired_tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "saved_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        }
        assert storage.is_token_expired(expired_tokens) is True
        
        # Test valid token
        valid_tokens = {
            "access_token": "test_access_token",
            "refresh_token": "test_refresh_token",
            "expires_in": 3600,
            "saved_at": datetime.now(timezone.utc).isoformat()
        }
        assert storage.is_token_expired(valid_tokens) is False

    def test_invalid_token_file(self, temp_storage_path):
        """Test handling of invalid token files."""
        storage = TokenStorage(storage_path=temp_storage_path)
        
        # Create invalid token file
        token_file_path = os.path.join(temp_storage_path, "test@example.com_token.json")
        with open(token_file_path, "wb") as f:
            f.write(b"invalid encrypted data")
        
        # Should return None and delete invalid file
        loaded_tokens = storage.load_tokens("test@example.com")
        assert loaded_tokens is None
        assert not os.path.exists(token_file_path)


class TestTeslaOAuthManager:
    """Test cases for TeslaOAuthManager class."""

    @pytest.fixture
    def oauth_manager(self):
        """Create OAuth manager for testing."""
        with patch('powernight.core.auth.tesla_oauth.get_config') as mock_config:
            mock_config.return_value.tesla_oauth.client_id = "test_client_id"
            mock_config.return_value.tesla_oauth.client_secret = "test_client_secret"
            mock_config.return_value.tesla_oauth.redirect_uri = "http://localhost:8080/callback"
            mock_config.return_value.tesla_oauth.scope = "openid email offline_access"
            mock_config.return_value.powerwall.tesla_email = "test@example.com"
            
            return TeslaOAuthManager()

    def test_init_with_config(self, oauth_manager):
        """Test OAuth manager initialization."""
        assert oauth_manager.client_id == "test_client_id"
        assert oauth_manager.client_secret == "test_client_secret"
        assert oauth_manager.redirect_uri == "http://localhost:8080/callback"
        assert oauth_manager.tesla_email == "test@example.com"

    def test_get_authorization_url(self, oauth_manager):
        """Test getting authorization URL."""
        with patch('powernight.core.auth.tesla_oauth.OAuth2Session') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.create_authorization_url.return_value = (
                "https://auth.tesla.com/oauth2/v3/authorize?client_id=test&response_type=code",
                "test_state"
            )
            mock_session.return_value = mock_session_instance
            
            url = oauth_manager.get_authorization_url()
            
            assert url.startswith("https://auth.tesla.com/oauth2/v3/authorize")
            assert "client_id=test" in url
            assert "response_type=code" in url

    def test_exchange_code_for_token_success(self, oauth_manager):
        """Test successful code exchange for tokens."""
        with patch('powernight.core.auth.tesla_oauth.OAuth2Session') as mock_session:
            mock_session_instance = Mock()
            mock_session_instance.fetch_token.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "token_type": "Bearer"
            }
            mock_session.return_value = mock_session_instance
            
            # Mock URL parsing
            with patch('powernight.core.auth.tesla_oauth.urlparse') as mock_parse:
                mock_parse.return_value.query = "code=test_code&state=test_state"
                with patch('powernight.core.auth.tesla_oauth.parse_qs') as mock_parse_qs:
                    mock_parse_qs.return_value = {
                        'code': ['test_code'],
                        'state': ['test_state']
                    }
                    
                    tokens = oauth_manager.exchange_code_for_token("http://localhost:8080/callback?code=test_code&state=test_state")
                    
                    assert tokens["access_token"] == "test_access_token"
                    assert tokens["refresh_token"] == "test_refresh_token"
                    assert tokens["expires_in"] == 3600

    def test_exchange_code_for_token_missing_code(self, oauth_manager):
        """Test code exchange with missing authorization code."""
        with patch('powernight.core.auth.tesla_oauth.urlparse') as mock_parse:
            mock_parse.return_value.query = "state=test_state"
            with patch('powernight.core.auth.tesla_oauth.parse_qs') as mock_parse_qs:
                mock_parse_qs.return_value = {
                    'state': ['test_state']
                }
                
                with pytest.raises(TeslaOAuthError, match="Authorization code not found"):
                    oauth_manager.exchange_code_for_token("http://localhost:8080/callback?state=test_state")

    def test_refresh_access_token_success(self, oauth_manager):
        """Test successful token refresh."""
        # Mock token storage
        with patch.object(oauth_manager.token_storage, 'load_tokens') as mock_load:
            mock_load.return_value = {
                "access_token": "old_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600
            }
            
            with patch('powernight.core.auth.tesla_oauth.OAuth2Session') as mock_session:
                mock_session_instance = Mock()
                mock_session_instance.refresh_token.return_value = {
                    "access_token": "new_access_token",
                    "refresh_token": "new_refresh_token",
                    "expires_in": 3600,
                    "token_type": "Bearer"
                }
                mock_session.return_value = mock_session_instance
                
                new_tokens = oauth_manager.refresh_access_token()
                
                assert new_tokens["access_token"] == "new_access_token"
                assert new_tokens["refresh_token"] == "new_refresh_token"

    def test_refresh_access_token_no_refresh_token(self, oauth_manager):
        """Test token refresh with no refresh token available."""
        with patch.object(oauth_manager.token_storage, 'load_tokens') as mock_load:
            mock_load.return_value = None
            
            with pytest.raises(TeslaOAuthError, match="No refresh token available"):
                oauth_manager.refresh_access_token()

    def test_get_valid_access_token_valid(self, oauth_manager):
        """Test getting valid access token."""
        with patch.object(oauth_manager.token_storage, 'load_tokens') as mock_load:
            mock_load.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "saved_at": datetime.now(timezone.utc).isoformat()
            }
            
            with patch.object(oauth_manager.token_storage, 'is_token_expired') as mock_expired:
                mock_expired.return_value = False
                
                token = oauth_manager.get_valid_access_token()
                
                assert token == "test_access_token"

    def test_get_valid_access_token_expired_refresh(self, oauth_manager):
        """Test getting access token with expired token that gets refreshed."""
        with patch.object(oauth_manager.token_storage, 'load_tokens') as mock_load:
            mock_load.return_value = {
                "access_token": "old_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600,
                "saved_at": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            }
            
            with patch.object(oauth_manager.token_storage, 'is_token_expired') as mock_expired:
                mock_expired.return_value = True
                
                with patch.object(oauth_manager, 'refresh_access_token') as mock_refresh:
                    mock_refresh.return_value = {
                        "access_token": "new_access_token",
                        "refresh_token": "new_refresh_token",
                        "expires_in": 3600
                    }
                    
                    token = oauth_manager.get_valid_access_token()
                    
                    assert token == "new_access_token"
                    mock_refresh.assert_called_once()

    def test_get_powerwalls_success(self, oauth_manager):
        """Test successful Powerwall fetching."""
        with patch.object(oauth_manager, 'get_valid_access_token') as mock_token:
            mock_token.return_value = "test_access_token"
            
            with patch('powernight.core.auth.tesla_oauth.requests.get') as mock_get:
                mock_response = Mock()
                mock_response.json.return_value = {
                    "response": [
                        {
                            "id": "powerwall_123",
                            "resource_type": "powerwall",
                            "display_name": "Home Powerwall",
                            "serial_number": "PW123456789",
                            "site_id": "site_123",
                            "energy_site_id": "energy_site_123"
                        }
                    ]
                }
                mock_response.raise_for_status.return_value = None
                mock_get.return_value = mock_response
                
                powerwalls = oauth_manager.get_powerwalls()
                
                assert len(powerwalls) == 1
                assert powerwalls[0]["id"] == "powerwall_123"
                assert powerwalls[0]["display_name"] == "Home Powerwall"

    def test_get_powerwalls_no_token(self, oauth_manager):
        """Test Powerwall fetching with no access token."""
        with patch.object(oauth_manager, 'get_valid_access_token') as mock_token:
            mock_token.return_value = None
            
            powerwalls = oauth_manager.get_powerwalls()
            
            assert powerwalls == []

    def test_revoke_tokens_success(self, oauth_manager):
        """Test successful token revocation."""
        with patch.object(oauth_manager.token_storage, 'load_tokens') as mock_load:
            mock_load.return_value = {
                "access_token": "test_access_token",
                "refresh_token": "test_refresh_token",
                "expires_in": 3600
            }
            
            with patch('powernight.core.auth.tesla_oauth.requests.post') as mock_post:
                mock_response = Mock()
                mock_response.raise_for_status.return_value = None
                mock_post.return_value = mock_response
                
                with patch.object(oauth_manager.token_storage, 'delete_tokens') as mock_delete:
                    oauth_manager.revoke_tokens()
                    
                    mock_post.assert_called_once()
                    mock_delete.assert_called_once_with("test@example.com")

    def test_revoke_tokens_no_tokens(self, oauth_manager):
        """Test token revocation with no tokens available."""
        with patch.object(oauth_manager.token_storage, 'load_tokens') as mock_load:
            mock_load.return_value = None
            
            with patch.object(oauth_manager.token_storage, 'delete_tokens') as mock_delete:
                oauth_manager.revoke_tokens()
                
                mock_delete.assert_called_once_with("test@example.com")

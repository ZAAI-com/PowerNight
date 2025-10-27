"""
Tesla OAuth 2.0 authentication manager for pypowerwall compatibility.

Handles the complete OAuth flow matching pypowerwall's terminal setup process.
"""

import os
import secrets
import urllib.parse
import hashlib
import base64
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
import requests

from .token_storage import PyPowerwallAuthStorage
from ...utils.logging import get_logger, ComponentType


class TeslaOAuthManager:
    """
    Manages Tesla OAuth 2.0 authentication flow for pypowerwall cloud mode.
    
    Implements the same OAuth flow as pypowerwall's terminal setup process,
    including PKCE, callback URL handling, and site selection.
    """
    
    # Tesla OAuth endpoints
    AUTHORIZATION_URL = "https://auth.tesla.com/oauth2/v3/authorize"
    TOKEN_URL = "https://auth.tesla.com/oauth2/v3/token"
    REVOKE_URL = "https://auth.tesla.com/oauth2/v3/revoke"
    PRODUCTS_URL = "https://owner-api.teslamotors.com/api/1/products"
    
    # OAuth scopes matching pypowerwall
    SCOPES = [
        "openid",
        "email", 
        "offline_access"
    ]
    
    # Client ID matching pypowerwall
    CLIENT_ID = "ownerapi"
    
    def __init__(self, storage_path: str = None):
        """
        Initialize Tesla OAuth manager.
        
        Args:
            storage_path: Path to store pypowerwall auth files. If None, uses environment variable or default.
        """
        self.logger = get_logger()
        self.auth_storage = PyPowerwallAuthStorage(storage_path)
        self._active_sessions: Dict[str, Dict[str, Any]] = {}
    
    def generate_auth_url(self, email: str) -> Dict[str, str]:
        """
        Generate Tesla authorization URL for pypowerwall-compatible OAuth flow.
        
        Args:
            email: Tesla account email
            
        Returns:
            Dictionary containing auth_url and session_id
        """
        try:
            # Generate session ID for this auth flow
            session_id = secrets.token_urlsafe(32)
            
            # Generate PKCE parameters
            code_verifier = secrets.token_urlsafe(86)  # 86 chars as per pypowerwall
            code_challenge = self._generate_code_challenge(code_verifier)
            state = secrets.token_urlsafe(32)
            
            # Store session data
            self._active_sessions[session_id] = {
                'email': email,
                'code_verifier': code_verifier,
                'state': state,
                'created_at': datetime.now(timezone.utc),
                'step': 'awaiting_callback'
            }
            
            # Build authorization URL matching pypowerwall format
            params = {
                'response_type': 'code',
                'client_id': self.CLIENT_ID,
                'redirect_uri': 'https://auth.tesla.com/void/callback',
                'scope': ' '.join(self.SCOPES),
                'state': state,
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256',
                'login_hint': email,
                'skip_redirection': 'true',
                'locale': 'en-US'
            }
            
            auth_url = f"{self.AUTHORIZATION_URL}?{urllib.parse.urlencode(params)}"
            
            self.logger.info(f"Generated Tesla authorization URL for {email}")
            
            return {
                'auth_url': auth_url,
                'session_id': session_id
            }
            
        except Exception as e:
            self.logger.error(f"Failed to generate authorization URL: {e}")
            raise
    
    def exchange_code_from_callback_url(self, session_id: str, callback_url: str) -> Dict[str, Any]:
        """
        Exchange authorization code from callback URL for tokens.
        
        Args:
            session_id: Session ID for this auth flow
            callback_url: Full callback URL from Tesla
            
        Returns:
            Dictionary with token exchange result and sites
        """
        try:
            # Get session data
            session_data = self._active_sessions.get(session_id)
            if not session_data:
                raise ValueError("Invalid or expired session")
            
            # Parse callback URL
            parsed_url = urllib.parse.urlparse(callback_url)
            query_params = urllib.parse.parse_qs(parsed_url.query)
            
            code = query_params.get('code', [None])[0]
            state = query_params.get('state', [None])[0]
            error = query_params.get('error', [None])[0]
            
            if error:
                raise ValueError(f"OAuth error: {error}")
            
            if not code or not state:
                raise ValueError("Missing authorization code or state parameter")
            
            # Validate state parameter
            if state != session_data['state']:
                raise ValueError("Invalid state parameter")
            
            # Exchange code for tokens
            token_data = self._exchange_code_for_tokens(code, session_data['code_verifier'])
            
            # Get energy sites
            sites = self.get_energy_sites(token_data['access_token'])
            
            # Update session data
            session_data.update({
                'access_token': token_data['access_token'],
                'refresh_token': token_data.get('refresh_token'),
                'expires_at': token_data.get('expires_at'),
                'sites': sites,
                'step': 'selecting_site'
            })
            
            self.logger.info(f"Successfully exchanged authorization code for tokens for {session_data['email']}")
            
            return {
                'success': True,
                'sites': sites,
                'expires_at': token_data.get('expires_at')
            }
            
        except Exception as e:
            self.logger.error(f"Failed to exchange callback URL: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def _generate_code_challenge(self, code_verifier: str) -> str:
        """Generate PKCE code challenge from verifier."""
        digest = hashlib.sha256(code_verifier.encode()).digest()
        return base64.urlsafe_b64encode(digest).decode().rstrip('=')
    
    def get_energy_sites(self, access_token: str) -> List[Dict[str, Any]]:
        """
        Get Tesla Energy sites for the authenticated user.
        
        Args:
            access_token: Valid Tesla access token
            
        Returns:
            List of energy sites
        """
        try:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'User-Agent': 'PowerNight/1.0'
            }
            
            response = requests.get(
                self.PRODUCTS_URL,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                raise Exception(f"Failed to get energy sites: {response.status_code} - {response.text}")
            
            data = response.json()
            products = data.get('response', [])
            
            # Filter for energy products (Powerwalls)
            energy_sites = []
            for product in products:
                if product.get('resource_type') == 'battery':
                    site_info = {
                        'id': product.get('energy_site_id'),
                        'name': product.get('site_name', 'Unknown Site'),
                        'type': 'battery',
                        'resource_type': product.get('resource_type'),
                        'state': product.get('state', 'unknown')
                    }
                    energy_sites.append(site_info)
            
            self.logger.info(f"Found {len(energy_sites)} energy sites")
            return energy_sites
            
        except Exception as e:
            self.logger.error(f"Failed to get energy sites: {e}")
            raise
    
    def _exchange_code_for_tokens(self, code: str, code_verifier: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        data = {
            'grant_type': 'authorization_code',
            'client_id': self.CLIENT_ID,
            'code': code,
            'code_verifier': code_verifier,
            'redirect_uri': 'https://auth.tesla.com/void/callback'
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'PowerNight/1.0'
        }
        
        response = requests.post(
            self.TOKEN_URL,
            data=data,
            headers=headers,
            timeout=30
        )
        
        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.status_code} - {response.text}")
        
        token_response = response.json()
        
        # Calculate expiration time
        expires_in = token_response.get('expires_in', 3600)
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        return {
            'access_token': token_response['access_token'],
            'refresh_token': token_response.get('refresh_token'),
            'id_token': token_response.get('id_token'),
            'token_type': token_response.get('token_type', 'Bearer'),
            'expires_in': expires_in,
            'expires_at': expires_at.isoformat(),
            'scope': token_response.get('scope', '')
        }
    
    def complete_setup(self, session_id: str, site_id: str) -> Dict[str, Any]:
        """
        Complete the auth setup by storing tokens and site selection.
        
        Args:
            session_id: Session ID for this auth flow
            site_id: Selected site ID
            
        Returns:
            Dictionary with setup completion result
        """
        try:
            # Get session data
            session_data = self._active_sessions.get(session_id)
            if not session_data:
                raise ValueError("Invalid or expired session")
            
            # Find selected site (handle potential type mismatch between API and frontend)
            selected_site = None
            for site in session_data.get('sites', []):
                if str(site['id']) == str(site_id):
                    selected_site = site
                    break
            
            if not selected_site:
                raise ValueError("Invalid site selection")
            
            # Prepare token data
            token_data = {
                'access_token': session_data['access_token'],
                'refresh_token': session_data.get('refresh_token'),
                'expires_at': session_data.get('expires_at'),
                'token_type': 'Bearer'
            }
            
            # Store auth data in pypowerwall format
            self.auth_storage.store_auth_data(
                email=session_data['email'],
                tokens=token_data,
                site=selected_site
            )
            
            # --- Create and return the authenticated pypowerwall instance ---
            import pypowerwall
            powerwall_instance = pypowerwall.Powerwall(
                email=session_data['email'],
                cloudmode=True,
                authmode="token",
                authpath=str(self.auth_storage.storage_path) + "/",
                timeout=30
            )

            # Update session
            session_data['step'] = 'complete'
            session_data['selected_site'] = selected_site
            
            self.logger.info(f"Auth setup completed for {session_data['email']} with site {selected_site['name']}")
            
            return {
                'success': True,
                'message': 'Setup complete. Auth file created.',
                'email': session_data['email'],
                'site': selected_site,
                'powerwall_instance': powerwall_instance
            }
            
        except Exception as e:
            self.logger.error(f"Failed to complete setup: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def get_valid_access_token(self) -> Optional[str]:
        """
        Get a valid access token from stored auth data.
        
        Returns:
            Valid access token or None if unavailable
        """
        auth_data = self.auth_storage.load_auth_data()
        if not auth_data:
            return None
        
        # Check if token is expired
        if self.auth_storage.is_token_expired(auth_data):
            self.logger.info("Access token expired, attempting refresh")
            if not self.refresh_access_token():
                return None
            
            # Reload auth data after refresh
            auth_data = self.auth_storage.load_auth_data()
        
        return auth_data.get('access_token') if auth_data else None

    def refresh_access_token(self) -> bool:
        """
        Refresh access token using refresh token.
        
        Returns:
            True if refresh successful, False otherwise
        """
        try:
            auth_data = self.auth_storage.load_auth_data()
            if not auth_data or 'refresh_token' not in auth_data:
                self.logger.warning("No refresh token available")
                return False
            
            data = {
                'grant_type': 'refresh_token',
                'client_id': self.CLIENT_ID,
                'refresh_token': auth_data['refresh_token']
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'User-Agent': 'PowerNight/1.0'
            }
            
            response = requests.post(
                self.TOKEN_URL,
                data=data,
                headers=headers,
                timeout=30
            )
            
            if response.status_code != 200:
                self.logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return False
            
            token_response = response.json()
            
            # Update tokens
            expires_in = token_response.get('expires_in', 3600)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
            
            updated_tokens = {
                'access_token': token_response['access_token'],
                'refresh_token': token_response.get('refresh_token', auth_data['refresh_token']),
                'expires_at': expires_at.isoformat(),
                'token_type': 'Bearer'
            }
            
            # Update stored auth data
            self.auth_storage.store_auth_data(
                email=auth_data['email'],
                tokens=updated_tokens,
                site={
                    'id': auth_data.get('site_id'),
                    'name': auth_data.get('site_name'),
                    'type': auth_data.get('site_type')
                }
            )
            
            self.logger.info("Access token refreshed successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to refresh access token: {e}")
            return False
    
    def test_pypowerwall_connection(self, email: str) -> Dict[str, Any]:
        """
        Test pypowerwall cloud mode connection and get basic Powerwall info.
        
        Args:
            email: Tesla account email (for compatibility, but uses stored auth data)
            
        Returns:
            Dictionary with connection test result and basic Powerwall info
        """
        try:
            import pypowerwall
            
            # Get auth data
            auth_data = self.auth_storage.load_auth_data()
            if not auth_data:
                raise Exception("No authentication data found. Please complete setup first.")
            
            # Test connection using pypowerwall cloud mode with stored auth
            pw = pypowerwall.Powerwall(
                email=auth_data['email'],
                cloudmode=True,
                authmode="token",
                authpath=str(self.auth_storage.storage_path) + "/",
                timeout=30
            )
            
            # Test basic connectivity by getting site info
            site_info = pw.site()
            if site_info is None:
                raise Exception("No site information available")
            
            # Get basic Powerwall info
            battery_level = pw.level()
            power_data = pw.power()
            
            # Create a simplified Powerwall info structure
            powerwall_info = {
                'id': auth_data.get('site_id', 'unknown'),
                'serial_number': auth_data.get('site_id', 'unknown'),
                'site_id': auth_data.get('site_id', 'unknown'),
                'display_name': f"Powerwall ({auth_data['email']})",
                'energy_site_id': auth_data.get('site_id', 'unknown'),
                'resource_type': 'battery',
                'state': 'online' if battery_level is not None else 'unknown',
                'components': {
                    'battery': True,
                    'solar': 'solar' in str(site_info).lower(),
                    'grid': True
                },
                'battery_level': battery_level,
                'connection_test': True
            }
            
            self.logger.info(f"Successfully tested pypowerwall connection for {auth_data['email']}")
            return {
                'success': True,
                'powerwall': powerwall_info,
                'connection_type': 'pypowerwall_cloud'
            }
            
        except Exception as e:
            self.logger.error(f"Failed to test pypowerwall connection: {e}")
            return {
                'success': False,
                'error': str(e),
                'connection_type': 'pypowerwall_cloud'
            }
    
    def revoke_tokens(self) -> bool:
        """
        Revoke all stored tokens.
        
        Returns:
            True if revocation successful, False otherwise
        """
        try:
            auth_data = self.auth_storage.load_auth_data()
            if not auth_data:
                return True
            
            # Revoke access token
            if 'access_token' in auth_data:
                data = {
                    'token': auth_data['access_token'],
                    'token_type_hint': 'access_token'
                }
                
                headers = {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'User-Agent': 'PowerNight/1.0'
                }
                
                requests.post(
                    self.REVOKE_URL,
                    data=data,
                    headers=headers,
                    timeout=30
                )
            
            # Clear stored auth data
            self.auth_storage.clear_auth_data()
            
            self.logger.info("Tokens revoked and auth data cleared")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to revoke tokens: {e}")
            return False
    
    def get_auth_status(self) -> Dict[str, Any]:
        """
        Get current authentication status.
        
        Returns:
            Dictionary with authentication status information
        """
        auth_data = self.auth_storage.load_auth_data()
        
        status = {
            'authenticated': bool(auth_data),
            'has_auth_data': self.auth_storage.has_auth_data(),
            'token_expired': self.auth_storage.is_token_expired(auth_data) if auth_data else True,
            'storage_info': self.auth_storage.get_storage_info()
        }
        
        if auth_data:
            try:
                expires_at_value = auth_data['expires_at']
                # Handle both unix timestamp (float/int) and ISO string formats
                if isinstance(expires_at_value, (int, float)):
                    expires_at = datetime.fromtimestamp(expires_at_value, timezone.utc)
                else:
                    expires_at = datetime.fromisoformat(str(expires_at_value).replace('Z', '+00:00'))
                
                status['expires_at'] = expires_at.isoformat()
                status['expires_in_seconds'] = int((expires_at - datetime.now(timezone.utc)).total_seconds())
                status['email'] = auth_data.get('email')
                status['site_name'] = auth_data.get('site_name')
                status['site_id'] = auth_data.get('site', {}).get('id') if auth_data.get('site') else None
            except (ValueError, KeyError, TypeError):
                status['expires_at'] = None
                status['expires_in_seconds'] = 0
        
        return status

    def get_session_status(self, session_id: str) -> Dict[str, Any]:
        """
        Get status of an active auth session.
        
        Args:
            session_id: Session ID to check
            
        Returns:
            Dictionary with session status
        """
        session_data = self._active_sessions.get(session_id)
        if not session_data:
            return {
                'exists': False,
                'error': 'Session not found or expired'
            }
        
        # Check if session is expired (10 minutes)
        created_at = session_data['created_at']
        if datetime.now(timezone.utc) - created_at > timedelta(minutes=10):
            # Clean up expired session
            del self._active_sessions[session_id]
            return {
                'exists': False,
                'error': 'Session expired'
            }
        
        return {
            'exists': True,
            'step': session_data['step'],
            'email': session_data['email'],
            'sites': session_data.get('sites', []),
            'created_at': created_at.isoformat()
        }

    def cleanup_expired_sessions(self) -> None:
        """Clean up expired auth sessions."""
        current_time = datetime.now(timezone.utc)
        expired_sessions = []
        
        for session_id, session_data in self._active_sessions.items():
            if current_time - session_data['created_at'] > timedelta(minutes=10):
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            del self._active_sessions[session_id]
        
        if expired_sessions:
            self.logger.info(f"Cleaned up {len(expired_sessions)} expired auth sessions")

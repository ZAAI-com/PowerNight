"""
Tesla OAuth 2.0 authentication manager for pypowerwall compatibility.

Handles the complete OAuth flow matching pypowerwall's terminal setup process.
"""

import secrets
import urllib.parse
import hashlib
import base64
import json
import re
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
import requests
from pypowerwall import tesla_auth

from .token_storage import PyPowerwallAuthStorage
from ...utils.logging import get_logger


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

    # Tesla only accepts the native-app redirect for the ownerapi client. A
    # browser cannot open tesla://, so the user copies the URL it was sent to.
    REDIRECT_URI = tesla_auth.REDIRECT_URI

    # Code-exchange access tokens are valid for about 8 hours
    DEFAULT_ACCESS_TOKEN_LIFETIME = 28800
    
    def __init__(self, storage_path: Optional[str] = None) -> None:
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
            code_verifier = secrets.token_urlsafe(32)  # 43 chars, matching pypowerwall
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
                'redirect_uri': self.REDIRECT_URI,
                'scope': ' '.join(self.SCOPES),
                'state': state,
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256',
                'login_hint': email,
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
            callback_url: The tesla://auth/callback URL, or any pasted text
                containing it (e.g. a browser console line)
            
        Returns:
            Dictionary with token exchange result and sites
        """
        try:
            # Get session data
            session_data = self._active_sessions.get(session_id)
            if not session_data:
                raise ValueError("Invalid or expired session")
            
            query_params = self._parse_callback_params(callback_url)
            code = query_params.get('code')
            state = query_params.get('state')
            error = query_params.get('error')
            
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
    
    @staticmethod
    def _parse_callback_params(text: str) -> Dict[str, str]:
        """Extract code, state and error from a pasted callback URL or log line."""
        params: Dict[str, str] = {}
        for name, value in re.findall(r'[?&#](code|state|error)=([^&#\s\'"]+)', text or ''):
            params.setdefault(name, urllib.parse.unquote(value))
        return params

    def import_tokens(self, email: str, refresh_token: str, access_token: str) -> Dict[str, Any]:
        """
        Start a setup session from tokens created by ``python -m pypowerwall authtoken``.

        Tesla only accepts access tokens from a fresh native login, so this is
        the fallback when the browser flow cannot capture the tesla:// redirect.

        Returns:
            Dictionary with session_id and sites on success
        """
        try:
            refresh_token = (refresh_token or '').strip()
            access_token = (access_token or '').strip()
            if not refresh_token or not access_token:
                raise ValueError("Both the refresh token and the access token are required")

            expires_at = self._access_token_expiry(access_token)
            if expires_at <= datetime.now(timezone.utc):
                raise ValueError(
                    "This access token has expired. Run 'python -m pypowerwall authtoken' again."
                )

            try:
                sites = self.get_energy_sites(access_token)
            except Exception as error:
                raise ValueError(
                    "Tesla rejected the access token. Create a fresh one with "
                    "'python -m pypowerwall authtoken' and paste it right away."
                ) from error

            session_id = secrets.token_urlsafe(32)
            self._active_sessions[session_id] = {
                'email': email,
                'created_at': datetime.now(timezone.utc),
                'access_token': access_token,
                'refresh_token': refresh_token,
                'expires_at': expires_at.isoformat(),
                'sites': sites,
                'step': 'selecting_site',
            }
            self.logger.info(f"Imported Tesla tokens for {email}")
            return {
                'success': True,
                'session_id': session_id,
                'sites': sites,
                'expires_at': expires_at.isoformat(),
            }

        except Exception as e:
            self.logger.error(f"Failed to import Tesla tokens: {e}")
            return {
                'success': False,
                'error': str(e)
            }

    def _access_token_expiry(self, access_token: str) -> datetime:
        """Read the exp claim of a Tesla JWT access token (no signature check)."""
        try:
            payload = access_token.split('.')[1]
            claims = json.loads(base64.urlsafe_b64decode(payload + '=' * (-len(payload) % 4)))
            return datetime.fromtimestamp(int(claims['exp']), timezone.utc)
        except (IndexError, KeyError, TypeError, ValueError):
            return datetime.now(timezone.utc) + timedelta(seconds=self.DEFAULT_ACCESS_TOKEN_LIFETIME)

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
        """Exchange authorization code for access and refresh tokens.

        Delegates to pypowerwall, which speaks HTTP/2 with the TLS settings
        Tesla's token endpoint now requires and uses the tesla:// redirect.
        """
        token_response = tesla_auth._exchange_code(code, code_verifier)
        
        # Calculate expiration time
        expires_in = token_response.get('expires_in', self.DEFAULT_ACCESS_TOKEN_LIFETIME)
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
            
            # Update session
            session_data['step'] = 'complete'
            session_data['selected_site'] = selected_site
            
            self.logger.info(f"Auth setup completed for {session_data['email']} with site {selected_site['name']}")
            
            return {
                'success': True,
                'message': 'Setup complete. Auth file created.',
                'email': session_data['email'],
                'site': selected_site,
                'credentials_saved': True,
            }
            
        except Exception as e:
            self.logger.error(f"Failed to complete setup: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    
    def has_credentials(self) -> bool:
        """Return True when a Tesla login is stored.

        PowerNight never refreshes tokens itself: Tesla's owner API rejects
        access tokens minted by a refresh on a new session (HTTP 403), so the
        token lifecycle is left to pypowerwall's long-lived cloud session.
        """
        auth_data = self.auth_storage.load_auth_data()
        return bool(auth_data and (auth_data.get('refresh_token') or auth_data.get('access_token')))

    def describe_powerwall(self, pw: Any) -> Dict[str, Any]:
        """
        Summarize the Powerwall reachable through an existing pypowerwall session.
        
        Args:
            pw: Connected pypowerwall cloud session (the shared connector's)
            
        Returns:
            Dictionary with connection test result and basic Powerwall info
        """
        try:
            auth_data = self.auth_storage.load_auth_data()
            if not auth_data:
                raise Exception("No authentication data found. Please complete setup first.")
            
            # Test basic connectivity by getting site info
            site_info = pw.site()
            if site_info is None:
                raise Exception("No site information available")
            
            # Get basic Powerwall info
            battery_level = pw.level()
            
            # Create a simplified Powerwall info structure
            site_id = (auth_data.get('site') or {}).get('id', 'unknown')
            powerwall_info = {
                'id': site_id,
                'serial_number': site_id,
                'site_id': site_id,
                'display_name': f"Powerwall ({auth_data['email']})",
                'energy_site_id': site_id,
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
            
            # Best-effort revocation: signing out must still clear local
            # credentials when Tesla is unreachable or rejects the request
            if auth_data.get('access_token'):
                try:
                    requests.post(
                        self.REVOKE_URL,
                        data={
                            'token': auth_data['access_token'],
                            'token_type_hint': 'access_token'
                        },
                        headers={
                            'Content-Type': 'application/x-www-form-urlencoded',
                            'User-Agent': 'PowerNight/1.0'
                        },
                        timeout=30
                    )
                except requests.RequestException as error:
                    self.logger.warning(f"Tesla token revocation failed: {error}")
            
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

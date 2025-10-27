"""
pypowerwall-compatible auth file storage.

Provides storage for Tesla OAuth tokens in .pypowerwall.auth format.
"""

import os
import json
import base64
import time
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from ...utils.logging import get_logger


class PyPowerwallAuthStorage:
    """
    pypowerwall-compatible auth file storage.

    Stores Tesla OAuth tokens in teslapy cache format (.pypowerwall.auth)
    and site ID in .pypowerwall.site, exactly as pypowerwall expects.
    """

    def __init__(self, storage_path: str = None):
        """
        Initialize pypowerwall auth storage.

        Args:
            storage_path: Path to store auth files. If None, uses environment variable or default.
        """
        if storage_path is None:
            # Use environment variable for persistent storage, fallback to default
            storage_path = os.environ.get('POWERNIGHT_DATA_PATH', '/data')
        
        self.storage_path = Path(storage_path)
        self.logger = get_logger()

        # Ensure storage directory exists
        self.storage_path.mkdir(parents=True, exist_ok=True)
    
    def store_auth_data(self, email: str, tokens: Dict[str, Any], site: Dict[str, Any]) -> None:
        """
        Store pypowerwall auth data in teslapy cache format (.pypowerwall.auth).

        Args:
            email: Tesla account email
            tokens: Dictionary containing access_token, refresh_token, expires_at, etc.
            site: Dictionary containing id, name, type
        """
        try:
            # Create teslapy-compatible cache structure
            # Format: {email: {"url": sso_url, "sso": token_dict}}
            cache_data = {
                email: {
                    "url": "https://auth.tesla.com/",
                    "sso": {
                        "access_token": tokens.get("access_token"),
                        "refresh_token": tokens.get("refresh_token"),
                        "token_type": tokens.get("token_type", "Bearer"),
                        "expires_at": self._convert_expires_at(tokens.get("expires_at")),
                        "scope": tokens.get("scope", "openid email offline_access")
                    }
                }
            }

            # Store in pypowerwall auth file format (plain JSON, no encryption)
            auth_file = self.storage_path / ".pypowerwall.auth"
            with open(auth_file, 'w') as f:
                json.dump(cache_data, f, indent=2)

            # Set restrictive permissions (0o640 as per teslapy)
            os.chmod(auth_file, 0o640)

            # Store site ID in separate file
            site_file = self.storage_path / ".pypowerwall.site"
            site_id = site.get("id")
            if site_id is None:
                self.logger.warning("Site ID is None, not storing site file")
            else:
                site_file.write_text(str(site_id))
                os.chmod(site_file, 0o640)

            self.logger.info(f"pypowerwall auth data stored for {email} (teslapy format)")

        except Exception as e:
            self.logger.error(f"Failed to store pypowerwall auth data: {e}")
            raise

    def _convert_expires_at(self, expires_at_str: str) -> float:
        """Convert ISO format expires_at to unix timestamp."""
        try:
            if isinstance(expires_at_str, (int, float)):
                return float(expires_at_str)
            dt = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            return dt.timestamp()
        except (ValueError, AttributeError):
            # Default to 8 hours from now
            return time.time() + (8 * 3600)
    
    def load_auth_data(self) -> Optional[Dict[str, Any]]:
        """
        Load pypowerwall auth data from teslapy cache format or flat JSON format.

        Returns:
            Dictionary containing flattened auth data with email, tokens, and site info
        """
        try:
            auth_file = self.storage_path / ".pypowerwall.auth"
            site_file = self.storage_path / ".pypowerwall.site"

            if not auth_file.exists():
                return None

            # Read auth data
            with open(auth_file, 'r') as f:
                cache_data = json.load(f)

            if not cache_data:
                return None

            # Check if it's teslapy cache format (nested structure)
            if isinstance(cache_data, dict) and any(isinstance(v, dict) and "sso" in v for v in cache_data.values()):
                # Teslapy cache format: {email: {sso: {tokens...}}}
                email = list(cache_data.keys())[0]
                user_data = cache_data[email]
                sso_tokens = user_data.get("sso", {})
                
                # Read site ID if available
                site_id = None
                if site_file.exists():
                    try:
                        site_id = int(site_file.read_text().strip())
                    except (ValueError, OSError):
                        pass

                # Return flattened format for compatibility
                return {
                    "email": email,
                    "access_token": sso_tokens.get("access_token"),
                    "refresh_token": sso_tokens.get("refresh_token"),
                    "token_type": sso_tokens.get("token_type", "Bearer"),
                    "expires_at": sso_tokens.get("expires_at"),
                    "site": {"id": site_id} if site_id else None
                }
            
            # Check if it's flat JSON format (direct structure)
            elif isinstance(cache_data, dict) and "email" in cache_data and "access_token" in cache_data:
                # Flat format: {email, access_token, refresh_token, ...}
                site_id = cache_data.get("site_id")
                
                return {
                    "email": cache_data.get("email"),
                    "access_token": cache_data.get("access_token"),
                    "refresh_token": cache_data.get("refresh_token"),
                    "token_type": cache_data.get("token_type", "Bearer"),
                    "expires_at": cache_data.get("expires_at"),
                    "site": {"id": site_id} if site_id else None
                }
            
            else:
                self.logger.warning(f"Unknown auth file format in {auth_file}")
                return None

        except Exception as e:
            self.logger.error(f"Failed to load pypowerwall auth data: {e}")
            return None
    
    def clear_auth_data(self) -> None:
        """Clear all stored pypowerwall auth data."""
        try:
            auth_file = self.storage_path / ".pypowerwall.auth"
            site_file = self.storage_path / ".pypowerwall.site"

            if auth_file.exists():
                auth_file.unlink()
            if site_file.exists():
                site_file.unlink()

            self.logger.info("pypowerwall auth data cleared")

        except Exception as e:
            self.logger.error(f"Failed to clear pypowerwall auth data: {e}")
    
    def has_auth_data(self) -> bool:
        """Check if pypowerwall auth data is stored."""
        auth_file = self.storage_path / ".pypowerwall.auth"
        return auth_file.exists()
    
    def is_token_expired(self, auth_data: Optional[Dict[str, Any]] = None) -> bool:
        """
        Check if access token is expired.

        Args:
            auth_data: Auth data dictionary (if None, loads from storage)

        Returns:
            True if token is expired or missing
        """
        if auth_data is None:
            auth_data = self.load_auth_data()

        if not auth_data or "expires_at" not in auth_data:
            return True

        try:
            expires_at = auth_data["expires_at"]
            # expires_at is unix timestamp in teslapy format
            if isinstance(expires_at, (int, float)):
                return time.time() >= expires_at
            # Fallback: try ISO format
            dt = datetime.fromisoformat(str(expires_at).replace('Z', '+00:00'))
            return datetime.now(timezone.utc) >= dt
        except (ValueError, KeyError, TypeError):
            return True
    
    def get_storage_info(self) -> Dict[str, Any]:
        """Get information about pypowerwall auth storage."""
        auth_file = self.storage_path / ".pypowerwall.auth"
        site_file = self.storage_path / ".pypowerwall.site"

        info = {
            "storage_path": str(self.storage_path),
            "has_auth_data": auth_file.exists(),
            "has_site_data": site_file.exists(),
            "storage_exists": self.storage_path.exists(),
            "format": "teslapy cache (pypowerwall compatible)",
        }

        if auth_file.exists():
            try:
                stat = auth_file.stat()
                info.update({
                    "file_size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                })

                # Try to load auth data to get additional info
                auth_data = self.load_auth_data()
                if auth_data:
                    info.update({
                        "email": auth_data.get("email"),
                        "token_expired": self.is_token_expired(auth_data)
                    })
                    if auth_data.get("site"):
                        info["site_id"] = auth_data["site"].get("id")
            except OSError:
                pass

        return info

    def get_auth_file_path(self) -> str:
        """Get the path to the .pypowerwall.auth file."""
        return str(self.storage_path / ".pypowerwall.auth")

    def get_email(self) -> Optional[str]:
        """Get the email from stored auth data."""
        auth_data = self.load_auth_data()
        return auth_data.get("email") if auth_data else None

    def get_site_info(self) -> Optional[Dict[str, Any]]:
        """Get site information from stored auth data."""
        auth_data = self.load_auth_data()
        if not auth_data or not auth_data.get("site"):
            return None

        return auth_data.get("site")

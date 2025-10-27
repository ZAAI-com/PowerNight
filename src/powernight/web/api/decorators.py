"""
API decorators module.

Re-exports decorators from the auth module for convenience.
"""

from .auth import require_auth, require_role, get_current_user

__all__ = ['require_auth', 'require_role', 'get_current_user']


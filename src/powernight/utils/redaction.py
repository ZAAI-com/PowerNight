"""Remove credentials from text before it reaches logs or API responses."""

import re


_AUTHORIZATION_HEADER = re.compile(r'(?i)(authorization\s*[:=]\s*)(?:bearer\s+)?[A-Za-z0-9._~+/=-]+')
_TOKEN_FIELD = re.compile(r'(?i)(access_token|refresh_token|id_token)(["\'\s:=]+)([^,\s"\'&}]+)')
_BEARER = re.compile(r'(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+')
_JWT = re.compile(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+')
_OAUTH_CODE = re.compile(r'(?i)([?&#](?:code|state)=)[^&#\s\'"]+')


def redact_secrets(text: str) -> str:
    """Replace bearer values, OAuth tokens, JWTs and callback codes with a marker."""
    text = _AUTHORIZATION_HEADER.sub(r'\1***REDACTED***', text)
    text = _TOKEN_FIELD.sub(r'\1\2***REDACTED***', text)
    text = _BEARER.sub(r'\1***REDACTED***', text)
    text = _JWT.sub('***REDACTED***', text)
    return _OAUTH_CODE.sub(r'\1***REDACTED***', text)


def safe_error_detail(error: BaseException) -> str:
    """Describe an exception for logs with every credential removed."""
    return redact_secrets(f'{type(error).__name__}: {error}')

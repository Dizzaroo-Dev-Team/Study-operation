"""OAuth2 + PKCE helpers for the hub-and-spoke SSO flow."""
from __future__ import annotations

import base64
import hashlib
import secrets
from urllib.parse import urlencode

from app.config import settings


def generate_pkce() -> tuple[str, str]:
    """Return (verifier, challenge) using S256."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def generate_state() -> str:
    return secrets.token_urlsafe(16)


def get_hub_authorize_url(challenge: str, state: str) -> str:
    api_base = (settings.hub_oauth_api_url or "").rstrip("/")
    if not api_base:
        raise RuntimeError("HUB_OAUTH_API_URL is not configured")
    if not settings.oauth_client_id:
        raise RuntimeError("OAUTH_CLIENT_ID is not configured")
    if not settings.oauth_redirect_uri:
        raise RuntimeError("OAUTH_REDIRECT_URI is not configured")

    params = {
        "client_id": settings.oauth_client_id,
        "redirect_uri": settings.oauth_redirect_uri,
        "response_type": "code",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
        "scope": "openid profile email",
    }
    return f"{api_base}/api/oauth/authorize?{urlencode(params)}"

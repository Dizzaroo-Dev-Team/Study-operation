"""
ONLYOFFICE Document Server Utilities

Handles JWT token generation, document URL creation, and callback processing.
"""

import logging
import jwt
import hashlib
import time
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from urllib.parse import urlparse

from fastapi import Request

from app.config import settings

logger = logging.getLogger(__name__)


def generate_jwt_token(payload: Dict[str, Any]) -> str:
    """
    Generate JWT token for ONLYOFFICE communication.
    
    Args:
        payload: Dictionary to encode in JWT
        
    Returns:
        JWT token string
    """
    if not settings.onlyoffice_jwt_secret:
        logger.warning("ONLYOFFICE JWT secret not configured. JWT disabled.")
        return ""
    
    try:
        # PyJWT 2.x returns a string, but ensure it's a string
        token = jwt.encode(
            payload,
            settings.onlyoffice_jwt_secret,
            algorithm="HS256"
        )
        # Ensure we return a string (PyJWT 2.x should already return str)
        if isinstance(token, bytes):
            token = token.decode('utf-8')
        logger.debug(f"Generated JWT token (length: {len(token)})")
        return str(token)
    except Exception as e:
        logger.exception(f"Failed to generate JWT token: {str(e)}")
        raise


def create_document_config(
    document_url: str,
    callback_url: str,
    document_key: str,
    document_title: str,
    user_id: str,
    user_name: str,
    mode: str = "edit",  # "edit", "view", "readonly", or "comment"
    file_type: str = "docx",
    document_type: str = "word",
) -> Dict[str, Any]:
    """
    Create ONLYOFFICE document configuration.

    Args:
        document_url: URL to fetch the document
        callback_url: URL for ONLYOFFICE to call when saving
        document_key: Unique key for the document
        document_title: Title of the document
        user_id: User ID for editor
        user_name: User name for editor
        mode:
            "edit"    – full text editing (internal users)
            "view"    – pure read-only viewer
            "readonly" – open editor UI but lock text editing/signing stage safe
            "comment" – NEW: read-only text but user CAN add/resolve comments
                        This is the mode used when a review link is opened by
                        an external site user.  OnlyOffice achieves this by
                        opening the editor in "edit" mode with
                        permissions.edit = false and permissions.comment = true.

    Returns:
        Document configuration dictionary
    """
    # ── Determine effective OnlyOffice editorConfig.mode ─────────────────────
    # OnlyOffice only understands "edit" and "view" as editorConfig.mode values.
    # Our internal "comment" mode maps to editorConfig.mode = "edit" so that
    # the comment toolbar is rendered, but permissions.edit is set to False so
    # the user cannot change document content.
    oo_mode = "view" if mode == "view" else "edit"

    # ── Build permissions block ───────────────────────────────────────────────
    if mode == "edit":
        permissions = {
            "edit": True,       # Full text editing
            "download": True,
            "comment": True,    # Can also add comments while editing
            "review": True,     # Track-changes review mode
            "fillForms": True,
        }
    elif mode == "comment":
        # SITE USER REVIEW MODE
        # Text is locked (edit=False) but the comment toolbar is available.
        # review=False prevents "Track Changes" which would allow text mutations.
        permissions = {
            "edit": False,      # 🔒 No text editing
            "download": True,
            "comment": True,    # ✅ Can add / view comments
            "review": False,    # 🔒 No track-changes editing
            "fillForms": False,
        }
    elif mode == "readonly":
        # Locked document session that still uses the editor surface.
        # This avoids rendering issues seen with some pure "view" sessions.
        permissions = {
            "edit": False,
            "download": True,
            "comment": False,
            "review": False,
            "fillForms": False,
        }
    else:  # "view"
        permissions = {
            "edit": False,
            "download": True,
            "comment": False,   # Pure read-only
            "review": False,
            "fillForms": False,
        }

    # Autosave/forcesave trigger callbacks from the document server. For sessions
    # where the document must not be saved (view / locked signing), leaving them
    # enabled can confuse ONLYOFFICE and lead to a loaded shell with a blank page.
    _autosave = mode not in ("view", "readonly")
    _forcesave = mode not in ("view", "readonly")

    config = {
        "document": {
            "fileType": file_type,
            "key": document_key,
            "title": document_title,
            "url": document_url,
            # ── PERMISSIONS must live here (document.permissions) ────────────
            # OnlyOffice API spec: permissions is a property of the *document*
            # object, NOT of editorConfig.  Placing it under editorConfig is
            # silently ignored, which is why edit=False had no effect before.
            "permissions": permissions,
        },
        "documentType": document_type,
        "editorConfig": {
            # Force full editor UI (File/Home/Insert tabs) instead of compact embedded mode.
            "type": "desktop",
            "mode": oo_mode,
            "callbackUrl": callback_url,
            "user": {
                "id": user_id,
                "name": user_name,
            },
            "customization": {
                "autosave": _autosave,
                "forcesave": _forcesave,
                "hideRightMenu": False,
                "hideRulers": False,
                "hideMenu": False,  # Show menu bar (File, Edit, etc.)
                "compactHeader": False,  # Show full header with menu
                "compactToolbar": False,  # Show full toolbar
                "toolbarNoTabs": False,  # Show toolbar tabs
                # FIT TO PAGE WIDTH on load: OnlyOffice zoom special value -2 = "fit to
                # page width" (-1 would be "fit to page"). The page width then matches the
                # editor container width, so the document only scrolls VERTICALLY — no
                # horizontal scrollbar. It's a sticky fit mode, so the editor re-fits when
                # the container width changes (e.g. when the runner's History panel
                # collapses and the document column gets wider). Set here so it is included
                # in the JWT-signed config (mutating it client-side would break the token).
                "zoom": -2,
            },
        },
    }

    # Note: documentServerUrl is not required and should not be added to editorConfig
    
    # Add JWT if enabled
    if settings.onlyoffice_jwt_enabled and settings.onlyoffice_jwt_secret:
        token = generate_jwt_token(config)
        config["token"] = token
        logger.debug(f"JWT token generated and added to config (token length: {len(token)})")
    else:
        logger.warning("JWT is not enabled or secret is missing - config will not be signed")
    
    logger.info(f"ONLYOFFICE document config created - document.url: {config.get('document', {}).get('url')}, callbackUrl: {config.get('editorConfig', {}).get('callbackUrl')}, has_token: {'token' in config}")
    return config


def verify_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify and decode JWT token from ONLYOFFICE callback.
    
    Args:
        token: JWT token string
        
    Returns:
        Decoded payload or None if invalid
    """
    if not settings.onlyoffice_jwt_secret:
        return None
    
    try:
        payload = jwt.decode(
            token,
            settings.onlyoffice_jwt_secret,
            algorithms=["HS256"]
        )
        return payload
    except Exception as e:
        logger.exception(f"Failed to verify JWT token: {str(e)}")
        return None


def get_onlyoffice_editor_url(request: Optional[Request] = None) -> str:
    """
    Get ONLYOFFICE editor URL for iframe embedding.
    
    Returns:
        URL to ONLYOFFICE editor
    """
    # Use the configured public URL when available; otherwise fall back to the
    # internal Document Server URL. If production is still configured with a
    # localhost-only public URL, try to derive a browser-reachable host from
    # the current request instead of returning a dead localhost URL.
    public_url = settings.onlyoffice_public_url or settings.onlyoffice_url

    try:
        parsed_public = urlparse(public_url or "")
        is_loopback_public = parsed_public.hostname in {"localhost", "127.0.0.1"}

        if request is not None and is_loopback_public:
            forwarded_host = request.headers.get("x-forwarded-host")
            request_host = forwarded_host or request.headers.get("host") or request.url.netloc
            request_scheme = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"

            request_hostname = urlparse(f"//{request_host}").hostname if request_host else None

            # Only rewrite loopback-only ONLYOFFICE URLs when the browser is
            # actually talking to a non-local deployment host. Keep localhost
            # as-is for local development.
            if request_hostname and request_hostname not in {"localhost", "127.0.0.1"}:
                browser_host = request_host
                if parsed_public.port and ":" not in browser_host:
                    browser_host = f"{browser_host}:{parsed_public.port}"
                public_url = f"{request_scheme}://{browser_host}"
    except Exception:
        # Keep the configured value if parsing fails; the editor loader will
        # surface a clearer error if the URL is truly unusable.
        pass

    return f"{public_url}/web-apps/apps/api/documents/api.js"

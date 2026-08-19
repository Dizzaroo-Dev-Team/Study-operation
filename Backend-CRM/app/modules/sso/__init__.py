"""Hub-and-Spoke SSO module.

This backend is an OAuth2 + PKCE spoke that delegates login to the IAM hub.
Public surface mounted under /api/auth: login, callback, logout, me.
"""
from __future__ import annotations

from .routes import router

__all__ = ["router"]

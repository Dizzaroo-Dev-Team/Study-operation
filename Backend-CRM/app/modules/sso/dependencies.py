"""FastAPI dependencies for SSO-backed session auth."""
from __future__ import annotations

from fastapi import HTTPException, Request, status


def get_session_user(request: Request) -> dict:
    """Return the user dict from the signed Starlette session cookie.

    Raises 401 when no session is present. Use this for routes that need a
    browser session (i.e. SPA frontend calls). Bearer-token-only callers
    should continue to use app.auth.get_current_user.
    """
    user = request.session.get("user") if hasattr(request, "session") else None
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return user

"""Session auth for /api/monitor/* — token-gated public routes stay open."""
from __future__ import annotations

import re
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status

from app.auth import get_current_user_optional


def _is_monitor_public_route(path: str, method: str) -> bool:
    """Magic-link / token flows that must work without a CRM login session."""
    p = (path or "").rstrip("/")
    m = (method or "GET").upper()

    if p.endswith("/acknowledge") and m == "POST":
        return True

    if re.search(r"/visits/[^/]+/reschedule$", p) and m in ("GET", "POST"):
        return True

    if "/visit-report/review" in p:
        return True

    if re.search(r"/visits/[^/]+/confirmation-letter/confirm-data$", p) and m == "GET":
        return True

    if re.search(r"/visits/[^/]+/confirmation-letter/confirm$", p) and m == "GET":
        return True

    if re.search(r"/visits/[^/]+/pre-visit/acknowledge$", p) and m == "POST":
        return True

    return False


async def require_monitor_auth(
    request: Request,
    user: Optional[dict] = Depends(get_current_user_optional),
) -> Optional[dict]:
    if _is_monitor_public_route(request.url.path, request.method):
        return user
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user

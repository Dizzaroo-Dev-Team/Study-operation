"""Feature gating for site budgeting."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, status

from app.auth import get_current_user
from app.config import settings


def _allowed_user_ids() -> set[str]:
    raw = settings.site_budgeting_allowed_user_ids or ""
    return {x.strip() for x in raw.split(",") if x.strip()}


def require_site_budgeting(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    if not settings.enable_site_budgeting:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site budgeting is not enabled")
    allow = _allowed_user_ids()
    if allow:
        uid = user.get("user_id") or ""
        if uid not in allow:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Site budgeting not available for this user")
    return user

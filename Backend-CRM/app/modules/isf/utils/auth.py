"""
ISF Auth adapter for CRM integration.

Validates the CRM Bearer JWT token and returns an ISF-compatible UserResponse.
ISF does NOT issue tokens, does NOT have a login flow, and does NOT manage
SECRET_KEY / ALGORITHM / ACCESS_TOKEN_EXPIRE_MINUTES — all of that belongs
100% to the CRM's app.auth module.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Optional
from datetime import datetime, timezone
import os

from app.modules.isf.models.user import UserResponse, UserRole
from jose import JWTError, jwt as jose_jwt

# ── Borrow SECRET_KEY + ALGORITHM directly from the CRM ─────────────────────
# This guarantees ISF always validates tokens with the exact same secret the
# CRM used to sign them.  If the CRM ever moves to an env var, ISF follows
# automatically — no change needed here.
try:
    from app.auth import SECRET_KEY as _CRM_SECRET_KEY, ALGORITHM as _CRM_ALGORITHM
except ImportError:
    # Safety fallback: read from env (never a hardcoded string)
    _CRM_SECRET_KEY = os.environ.get("SECRET_KEY", "")
    _CRM_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")

_security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_security),
) -> Optional[UserResponse]:
    """
    Validate the CRM JWT and return an ISF UserResponse.

    - No token  → returns a minimal anonymous user (CRM UI already requires login,
                  so this only happens in rare edge-cases like direct API calls).
    - Valid token → maps the CRM user to an ISF UserResponse.
    - Invalid token → graceful degradation (returns anonymous user).
    """
    if credentials is None:
        return _default_user()

    try:
        payload = jose_jwt.decode(
            credentials.credentials,
            _CRM_SECRET_KEY,
            algorithms=[_CRM_ALGORITHM],
        )
        user_id: str = payload.get("sub")
        email: str = payload.get("email", "")
        role_str: str = payload.get("role", "participant")

        if not user_id:
            return _default_user()

        role = _map_role(role_str)
        return UserResponse(
            id=user_id,
            user_name=email.split("@")[0] if email else user_id,
            email=email,
            role=role,
            permissions=_permissions_for_role(role),
            assigned_studies=[],   # Study context comes from the CRM frontend
            is_active=True,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
            updated_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat() + "Z",
        )

    except JWTError:
        return _default_user()


async def get_current_active_user(
    current_user: Optional[UserResponse] = Depends(get_current_user),
) -> UserResponse:
    if current_user is None or not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user",
        )
    return current_user


# ── Helpers ──────────────────────────────────────────────────────────────────

def _default_user() -> UserResponse:
    """Minimal anonymous user returned when no/invalid token is present."""
    return UserResponse(
        id="crm-anonymous",
        user_name="anonymous",
        email="anonymous@crm.internal",
        role=UserRole.USER,
        permissions=["read_documents", "write_documents"],
        assigned_studies=[],
        is_active=True,
        created_at="2024-01-01T00:00:00Z",
        updated_at="2024-01-01T00:00:00Z",
    )


def _map_role(crm_role: str) -> UserRole:
    mapping = {
        "admin":        UserRole.SYSTEM_ADMIN,
        "sponsor":      UserRole.STUDY_LEAD,
        "cra":          UserRole.REVIEWER,
        "investigator": UserRole.SITE_MANAGER,
        "site_staff":   UserRole.DATA_MANAGER,
        "qa":           UserRole.QC_LEAD,
        "regulatory":   UserRole.APPROVER,
        "participant":  UserRole.USER,
    }
    return mapping.get(crm_role.lower(), UserRole.USER)


def _permissions_for_role(role: UserRole) -> list:
    base = ["read_documents"]
    if role in (UserRole.SYSTEM_ADMIN, UserRole.STUDY_LEAD, UserRole.QC_LEAD, UserRole.APPROVER):
        base += ["write_documents", "approve_documents", "admin"]
    elif role in (UserRole.SITE_MANAGER, UserRole.DATA_MANAGER, UserRole.REVIEWER):
        base += ["write_documents"]
    return base

"""
Authentication utilities for JWT tokens and password hashing.

Supports two modes (controlled by `settings.iam_auth_mode`):
  * "local" — only legacy HS256 JWTs minted by /auth/login are accepted.
  * "hub"   — only hub-issued tokens, verified via /api/auth/verify, are accepted.
  * "both"  — try local decode first; on failure fall through to hub verify.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from jose import JWTError, jwt
import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import AsyncSessionLocal, get_db
from app.config import settings
from app.integrations.iam.auth import (
    HubAuthError,
    entitlement_ok,
    map_hub_role_to_user_role,
    verify_hub_token,
)
from app.integrations.kafka.events.user_event import _upsert_postgres_user

logger = logging.getLogger(__name__)

# OAuth2 schemes for token extraction
# - oauth2_scheme: strict, errors if no/invalid token (used for required-auth endpoints)
# - oauth2_optional_scheme: does NOT auto-error, lets us treat auth as optional
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")
oauth2_optional_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

# JWT settings — read from environment via app.config.settings
# Set SECRET_KEY in .env (local) or as a cloud secret (production).
# Generate a strong key: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = settings.secret_key
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    try:
        # Ensure password is bytes
        password_bytes = plain_password.encode('utf-8')
        # Truncate to 72 bytes if necessary (bcrypt limit)
        if len(password_bytes) > 72:
            password_bytes = password_bytes[:72]
        # Verify password
        return bcrypt.checkpw(password_bytes, hashed_password.encode('utf-8'))
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    """Hash a password. Bcrypt has a 72 byte limit, so we truncate if necessary."""
    # Convert password to bytes
    password_bytes = password.encode('utf-8')
    # Bcrypt has a 72 byte limit, truncate if password is too long
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    # Generate salt and hash
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    return hashed.decode('utf-8')


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Create a JWT access token.

    RFC 7519 mandates `exp` as a NumericDate (integer seconds since epoch).
    PyJWT will coerce a datetime, but some downstream verifiers (offline
    validators in other languages) reject a non-integer `exp`. Encoding as
    int up front keeps the token portable.
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def _try_local_jwt(token: str) -> Optional[dict]:
    """Decode our own HS256 JWT. Returns user dict or None when the token
    isn't ours / the signed user no longer exists. Reads user details from
    Mongo `local_users` (Postgres is no longer the source of truth)."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    user_id = payload.get("sub")
    if not user_id:
        return None
    from app.db.mongo import get_mongo_db
    from app.integrations.iam.users import get_local_user_by_id, local_user_to_dict

    try:
        mongo_db = await get_mongo_db()
        doc = await get_local_user_by_id(mongo_db, user_id)
        if doc is None:
            return None
        return await local_user_to_dict(mongo_db, doc)
    except Exception as exc:
        # MongoDB unavailable / timeout — treat as "user not found via local JWT"
        # so the hub-token fallback can still be attempted.
        logger.warning("[auth] _try_local_jwt: MongoDB lookup failed (user_id=%s): %s", user_id, exc)
        return None


def _extract_hub_user_id(user_obj: dict) -> str:
    """Pull the user id out of a hub verify payload (key name varies by hub version)."""
    user_id = (
        user_obj.get("user_id")
        or user_obj.get("userId")
        or user_obj.get("id")
        or user_obj.get("sub")
    )
    return str(user_id).strip() if user_id is not None else ""


async def _sync_hub_user_to_postgres(user_id: str, email: str, display_name, sync_role) -> None:
    """Auto-provision / sync the Postgres `users` row. Use a fresh session because
    the hub flow may run outside of the request's session lifecycle and we want
    commits visible before the dependency returns. Failures are logged, not raised —
    don't reject the request just because dual-write hiccupped."""
    try:
        await _upsert_postgres_user(
            AsyncSessionLocal,
            user_id=user_id,
            email=email,
            display_name=display_name,
            initial_role=sync_role,
            sync_role=sync_role,
        )
    except Exception as exc:
        logger.exception("[auth] hub auto-provision failed for user_id=%s: %s", user_id, exc)


def _hub_raw_roles(hub_role, sync_role) -> list[str]:
    """Normalise the hub role claim (str | list | None) into a raw-roles list,
    ensuring the squashed sync_role is also present."""
    raw_roles: list[str] = []
    if isinstance(hub_role, list):
        raw_roles = [str(r) for r in hub_role if r]
    elif isinstance(hub_role, str) and hub_role.strip():
        raw_roles = [hub_role.strip()]
    if sync_role and sync_role.value not in raw_roles:
        raw_roles.append(sync_role.value)
    return raw_roles


async def _try_hub_token(token: str) -> Optional[dict]:
    """
    Verify a hub-issued bearer token via the hub `/api/auth/verify` endpoint
    (slow path, cached). Returns the local user dict or None on rejection.

    Side effects:
      * Auto-provisions a Postgres `users` row if missing.
      * Syncs `users.role` from the hub role on every successful verify
        (only writes when changed).
    """
    try:
        verify_resp = await verify_hub_token(token)
    except HubAuthError as exc:
        logger.debug("[auth] hub verify rejected token: %s", exc)
        return None

    user_obj = verify_resp.get("user") or verify_resp
    if not isinstance(user_obj, dict):
        return None

    user_id = _extract_hub_user_id(user_obj)
    if not user_id:
        return None

    if not entitlement_ok(verify_resp, settings.iam_application_id or ""):
        # User exists but isn't entitled to this app — surface as 403.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not have access to this application.",
        )

    email = (
        user_obj.get("email")
        or user_obj.get("emailAddress")
        or user_obj.get("email_address")
        or ""
    )
    display_name = (
        user_obj.get("name")
        or user_obj.get("displayName")
        or user_obj.get("display_name")
        or user_obj.get("full_name")
    )

    hub_role = (
        user_obj.get("role")
        or user_obj.get("hub_role")
        or user_obj.get("hub_roles")
    )
    sync_role = map_hub_role_to_user_role(hub_role) if hub_role else None

    await _sync_hub_user_to_postgres(user_id, email, display_name, sync_role)

    # Fetch the canonical user dict from Mongo `local_users` (the IAM mirror).
    # Postgres `users` is no longer the source of truth for the auth layer.
    from app.db.mongo import get_mongo_db
    from app.integrations.iam.users import get_local_user_by_id, local_user_to_dict

    mongo_db = await get_mongo_db()
    doc = await get_local_user_by_id(mongo_db, user_id)
    if doc is not None:
        return await local_user_to_dict(mongo_db, doc)

    # Race: Kafka feed hasn't mirrored this user yet. Build a synthetic dict
    # from the verify response so the request still succeeds. Carry the RAW hub
    # role(s) in `roles` (un-squashed) so workflow role matching still works.
    return {
        "user_id": user_id,
        "email": email or None,
        "name": display_name or None,
        "role": (sync_role.value if sync_role else "participant"),
        "roles": _hub_raw_roles(hub_role, sync_role),
        "is_privileged": False,
    }


async def _resolve_user_from_token(token: Optional[str]) -> Optional[dict]:
    """Bearer-only resolution path, factored out so non-HTTP callers (WebSocket
    handlers, background jobs) can use it without supplying a Request.

    Returns None when the token is absent or fails decode under every mode.
    Raises HTTPException only when the hub explicitly rejects the token (so
    callers can distinguish "no auth" from "bad auth").
    """
    if not token:
        return None

    mode = (settings.iam_auth_mode or "both").lower()

    if mode in ("local", "both"):
        local = await _try_local_jwt(token)
        if local is not None:
            return local

    if mode in ("hub", "both"):
        # _try_hub_token raises HTTPException on hub-side rejection; let it
        # propagate so the caller can map it to its own 401/close code.
        hub = await _try_hub_token(token)
        if hub is not None:
            return hub

    return None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_optional_scheme),
) -> dict:
    """
    Get the current authenticated user. Resolution order:

      1. Starlette session cookie  — set by the SSO callback in
         app/modules/sso/routes/sso.py. When present, this is authoritative;
         we never hit the hub for already-authed cookie sessions.
      2. Bearer JWT in Authorization header — dispatched per
         `settings.iam_auth_mode` ("local" / "hub" / "both"). Used by the
         legacy password flow (POST /api/auth/login) and any service-to-service
         caller that passes a hub-issued token.

    The session-first ordering means every existing route guarded by
    `Depends(get_current_user)` accepts SSO sessions without any per-route
    change. The bearer path stays intact for non-browser callers.

    `request` is REQUIRED (no default) — FastAPI auto-injects it for any
    route that depends on us. Defaults of None on Request parameters trip
    FastAPI's Pydantic-field validator (it normalises `T = None` to
    `Optional[T]`, which Pydantic then rejects). WebSocket handlers and
    other non-HTTP callers should use `_resolve_user_from_token` directly
    instead of going through this dispatcher.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Cookie session (SSO). Skip silently if SessionMiddleware isn't mounted
    #    (no SESSION_SECRET_KEY) — falls through to bearer.
    try:
        session_user = (
            request.session.get("user") if hasattr(request, "session") else None
        )
    except (AssertionError, AttributeError):
        session_user = None
    if session_user:
        return session_user

    # 2. Bearer token path.
    user = await _resolve_user_from_token(token)
    if user is not None:
        return user

    raise credentials_exception


async def get_current_user_optional(
    request: Request,
    token: Optional[str] = Depends(oauth2_optional_scheme),
) -> Optional[dict]:
    """Same dispatcher as get_current_user, but returns None instead of 401."""
    try:
        return await get_current_user(request, token)
    except HTTPException:
        return None


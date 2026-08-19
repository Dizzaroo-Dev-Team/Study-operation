"""
Mongo-backed user lookups for the auth pipeline.

The CRM stopped treating Postgres `users` as the source of truth — the IAM
hub feeds Mongo `local_users` (via the Kafka sync), and that collection is
now the canonical user roster. Login + JWT-decode + display flows query
Mongo here. Postgres `users` is still maintained for FK joins, but the auth
layer no longer reads from it.

Public functions:
  * `get_local_user_by_id`      — Mongo `_id` lookup, returns the raw doc.
  * `get_local_user_by_email`   — case-insensitive email lookup.
  * `authenticate_local_user`   — verifies password against Mongo's
                                  `password_hash` (bcrypt), returns the doc
                                  on success or None.
  * `local_user_to_dict`        — shape used by the rest of the codebase
                                  (`get_current_user` return value, login
                                  response, etc).

Role resolution: when `local_users.role` is set we trust it. Otherwise we
fall back to the user's `hub_roles` entry in `local_hub_user_attributes`
(IAM publishes role assignments into that collection). Anything else
defaults to `participant`.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.auth import verify_password
from app.integrations.kafka.models.sync_models import (
    COLL_LOCAL_APP_USER_ATTRIBUTES,
    COLL_LOCAL_HUB_USER_ATTRIBUTES,
    COLL_LOCAL_USERS,
)

logger = logging.getLogger(__name__)


# ─── Lookups ────────────────────────────────────────────────────────────────

async def get_local_user_by_id(
    mongo_db: AsyncIOMotorDatabase, user_id: str
) -> Optional[dict]:
    if not user_id:
        return None
    return await mongo_db[COLL_LOCAL_USERS].find_one({"_id": str(user_id)})


async def get_local_user_by_email(
    mongo_db: AsyncIOMotorDatabase, email: str
) -> Optional[dict]:
    if not email:
        return None
    # Hub may not normalise email casing; do a case-insensitive match so
    # `Demo@Gmail.com` matches `demo@gmail.com`.
    return await mongo_db[COLL_LOCAL_USERS].find_one(
        {"email": {"$regex": f"^{_re_escape(email.strip())}$", "$options": "i"}}
    )


def _re_escape(s: str) -> str:
    # Minimal regex escape — only the characters Mongo's PCRE actually treats
    # as metachars. Avoids an `import re` for this hot path.
    out = []
    for ch in s:
        if ch in r"\^$.|?*+()[]{}":
            out.append("\\")
        out.append(ch)
    return "".join(out)


# ─── Auth ───────────────────────────────────────────────────────────────────

async def authenticate_local_user(
    mongo_db: AsyncIOMotorDatabase, email: str, password: str
) -> Optional[dict]:
    """Return the Mongo `local_users` doc when (email, password) is valid."""
    doc = await get_local_user_by_email(mongo_db, email)
    if not doc:
        return None
    pw_hash = doc.get("password_hash")
    if not pw_hash:
        return None
    if not verify_password(password, pw_hash):
        return None
    return doc


# ─── Role resolution ────────────────────────────────────────────────────────

# NOTE: this allow-list is ONLY for the legacy single `role` field consumed by
# the UserRole-enum permission system (app/permissions.py has_role/has_any_role)
# and the frontend. It is NOT used for workflow authorization — the workflow now
# matches against the user's REAL IAM roles (see get_user_real_roles below), so
# roles like "Contract Specialist" are honored as-is, never squashed.
_VALID_ROLES = {
    "sponsor",
    "site_manager",
    "coordinator",
    "participant",
    "cra",
    "study_manager",
    "medical_monitor",
}

# attributeKeys under which IAM publishes role grants into local_hub_user_attributes.
_ROLE_ATTRIBUTE_KEYS = ["hub_roles", "hubRoles", "roles", "role", "global_role", "globalRole"]


async def get_user_real_roles(
    mongo_db: AsyncIOMotorDatabase, user_id: str
) -> list[str]:
    """Every REAL IAM role the user holds — the source of truth for workflow role
    matching. NO allow-list, NO squashing. Collected from
    ``local_hub_user_attributes`` (hub_roles / roles / role / global_role; a
    value may be a single string or a list) and the per-resource roles inside
    ``local_app_user_attributes.resource_access``. Returns deduped raw display
    strings, e.g. ["Contract Specialist", "CRA"]."""
    out: list[str] = []
    seen: set[str] = set()

    def _add(v: Any) -> None:
        if isinstance(v, str) and v.strip():
            k = v.strip().lower()
            if k not in seen:
                seen.add(k)
                out.append(v.strip())

    if not user_id:
        return []

    # 1) hub role attributes (string or list of role names)
    try:
        cursor = mongo_db[COLL_LOCAL_HUB_USER_ATTRIBUTES].find(
            {"userId": str(user_id), "attributeKey": {"$in": _ROLE_ATTRIBUTE_KEYS}}
        )
        async for row in cursor:
            val = row.get("value")
            if isinstance(val, list):
                for v in val:
                    _add(v)
            else:
                _add(val)
    except Exception:
        logger.warning("get_user_real_roles: hub attribute lookup failed (user=%s)",
                       user_id, exc_info=True)

    # 2) per-resource roles from resource_access
    try:
        from app.integrations.iam.membership import (
            RESOURCE_ACCESS_ATTRIBUTE,
            parse_resource_access_value,
        )
        doc = await mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].find_one(
            {"attributeName": RESOURCE_ACCESS_ATTRIBUTE, "userId": str(user_id)}
        )
        if doc:
            for entry in parse_resource_access_value(doc.get("value")):
                _add(entry.get("role"))
    except Exception:
        logger.warning("get_user_real_roles: resource_access lookup failed (user=%s)",
                       user_id, exc_info=True)

    return out


def _slug(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value or "").strip().lower()).strip("_")


async def get_all_iam_roles(mongo_db: AsyncIOMotorDatabase) -> list[str]:
    """The distinct REAL roles that EXIST in the system — the vocabulary the
    workflow generator authors against. Derived from the roles actually granted
    to users: the FUNCTIONAL roles in ``local_app_user_attributes.resource_access``
    (e.g. CONTRACT_SPECIALIST, CRA, PRINCIPAL_INVESTIGATOR) plus the hub roles in
    ``local_hub_user_attributes``. Deduped by slug, preserving first-seen display
    form. (There is no separate role-catalog collection; granted roles are the
    source of truth for 'roles a real user can hold'.)"""
    roles: list[str] = []
    seen: set[str] = set()

    def _add(v: Any) -> None:
        if isinstance(v, str) and v.strip():
            k = _slug(v)
            if k and k not in seen:
                seen.add(k)
                roles.append(v.strip())

    try:
        cursor = mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].find(
            {"attributeName": "resource_access"}
        )
        async for doc in cursor:
            for entry in (doc.get("value") or []):
                if isinstance(entry, dict):
                    _add(entry.get("role"))
        hub_cursor = mongo_db[COLL_LOCAL_HUB_USER_ATTRIBUTES].find(
            {"attributeKey": {"$in": _ROLE_ATTRIBUTE_KEYS}}
        )
        async for row in hub_cursor:
            val = row.get("value")
            for v in (val if isinstance(val, list) else [val]):
                _add(v)
    except Exception:
        logger.warning("get_all_iam_roles: vocabulary lookup failed", exc_info=True)

    return roles


async def _resolve_role_from_hub_attrs(
    mongo_db: AsyncIOMotorDatabase, user_id: str
) -> Optional[str]:
    """
    Look at `local_hub_user_attributes` for `hub_roles` (or `role`/`roles`)
    and pick the first value that maps to a known UserRole enum value.
    Hub may store it as a string or list of strings.
    """
    if not user_id:
        return None
    cursor = mongo_db[COLL_LOCAL_HUB_USER_ATTRIBUTES].find(
        {
            "userId": user_id,
            "attributeKey": {"$in": ["hub_roles", "hubRoles", "role", "roles", "global_role"]},
        }
    )
    candidates: list[Any] = []
    async for row in cursor:
        v = row.get("value")
        if v is None:
            continue
        if isinstance(v, list):
            candidates.extend(v)
        else:
            candidates.append(v)

    for raw in candidates:
        if not isinstance(raw, str):
            continue
        s = raw.strip().lower()
        if s in _VALID_ROLES:
            return s
    return None


async def local_user_to_dict(
    mongo_db: AsyncIOMotorDatabase, doc: dict
) -> dict:
    """
    Map a Mongo `local_users` doc into the response shape the rest of the
    codebase expects (matches the previous Postgres-backed `_user_to_dict`).
    """
    if not doc:
        return {}
    user_id = str(doc.get("_id") or "")
    role: Optional[str] = None
    raw_role = doc.get("role")
    if isinstance(raw_role, str) and raw_role.strip().lower() in _VALID_ROLES:
        role = raw_role.strip().lower()
    if role is None:
        role = await _resolve_role_from_hub_attrs(mongo_db, user_id)
    if role is None:
        role = "participant"
    # The user's FULL real IAM role set — what the workflow matches against. The
    # singular `role` above stays for the legacy UserRole-enum permission system.
    real_roles = await get_user_real_roles(mongo_db, user_id)
    roles = list(real_roles)
    # Also include the RAW local_users.role (un-squashed, e.g. a free-form display
    # role) and the normalized singular role, so a role stored only there is not
    # lost. Deduped by slug.
    have = {_slug(r) for r in roles}
    for extra in (doc.get("role"), role):
        if isinstance(extra, str) and extra.strip() and _slug(extra) not in have:
            have.add(_slug(extra))
            roles.append(extra.strip())
    return {
        "user_id": user_id,
        "email": doc.get("email"),
        "name": doc.get("displayName") or doc.get("name") or doc.get("email") or user_id,
        "role": role,
        # All real IAM roles (raw display strings); workflow authorization uses
        # these (slug-matched), not the squashed singular `role`.
        "roles": roles,
        # `is_privileged` was a per-app CRM flag in Postgres `users`. The IAM
        # mirror has no equivalent — default false; can be elevated later by
        # a separate admin endpoint if needed.
        "is_privileged": bool(doc.get("is_privileged")) if doc.get("is_privileged") is not None else False,
    }


__all__ = [
    "authenticate_local_user",
    "get_local_user_by_email",
    "get_local_user_by_id",
    "local_user_to_dict",
]

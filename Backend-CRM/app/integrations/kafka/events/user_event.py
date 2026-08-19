"""
Port of ``events/userEvent.js`` — iam.users.events consumer.

IAM publishes user CRUD with entity_type 'user' and this flat payload:
  created / updated / deleted →
    { id, email, firstName, lastName, googleId, metadata, status,
      organization, deletedBy, deletedAt, createdAt, updatedAt }

The same topic also carries ownership-sync events (entity_type hub_ownership /
application_ownership); this consumer ignores any envelope whose entity_type is
not 'user'. No field aliases, no envelope merging.

APP EXTENSION (not in the Mongo-only reference): on create/update we ALSO upsert
a Postgres ``users`` row so synced identities can authenticate to the CRM and
satisfy FK targets. ``_upsert_postgres_user`` / ``_DEFAULT_PASSWORD_HASH`` are
imported by the SSO/login path (``app.auth``) and ``app.crud`` — this is their
home now that the sync lives here.
"""
from __future__ import annotations

import secrets as _secrets
from datetime import datetime, timezone

import bcrypt as _bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.config import settings as _settings
from app.db import AsyncSessionLocal
from app.db.mongo import get_mongo_db
from app.models import User, UserRole

from ..models.sync_models import COLL_LOCAL_USERS
from ..utils.logger import create_module_logger
from ..utils.policy_evaluation_cache import invalidate_expanded_subject_cache_for_user
from .helpers import dispatch_by_action

log = create_module_logger("KafkaConsumer")


def _get_payload(envelope: dict) -> dict:
    p = (envelope or {}).get("payload")
    return p if isinstance(p, dict) else {}


def _is_user_entity(envelope: dict) -> bool:
    """True only for entity_type 'user' — ownership-sync events are ignored."""
    et = (envelope or {}).get("entity_type")
    if et is None:
        et = (envelope or {}).get("entityType")
    if et is None:
        return True  # unstamped → treat as user CRUD
    return str(et).strip().lower() == "user"


# ─── Postgres dual-write (CRM `users` table) — app extension ──────────────────
# Pre-computed bcrypt hash of the mirrored-user default password (rounds=12).
# Every IAM-mirrored user gets this default password on creation so they can sign
# in via the legacy /auth/login flow until SSO fully replaces it. We NEVER
# overwrite an existing password_hash on update. Comes from
# IAM_MIRROR_DEFAULT_PASSWORD; unset => random per boot => legacy login disabled
# for mirrored users (they authenticate via SSO / hub tokens).
_default_mirror_password = _settings.iam_mirror_default_password or _secrets.token_urlsafe(24)
_DEFAULT_PASSWORD_HASH = _bcrypt.hashpw(
    _default_mirror_password.encode("utf-8"), _bcrypt.gensalt(rounds=12)
).decode("utf-8")
del _default_mirror_password


async def _upsert_postgres_user(
    sql_session_factory: async_sessionmaker,
    *,
    user_id: str,
    email: str,
    display_name: str | None,
    initial_role: UserRole | None = None,
    sync_role: UserRole | None = None,
) -> None:
    """
    Idempotent upsert into Postgres ``users``.

    ``initial_role`` — role used when INSERTING a brand-new row (defaults to
                       PARTICIPANT). Ignored on update.
    ``sync_role``    — when present AND the existing row's role differs, update
                       the row to this role (used by the hub-token verify path).
                       Pass None to leave the existing role alone.

    On INSERT, ``password_hash`` is set to the default-password hash. On UPDATE
    we never touch the password — once the user (or admin) changes it, it stays.
    """
    async with sql_session_factory() as session:
        existing = (
            await session.execute(select(User).where(User.user_id == user_id))
        ).scalar_one_or_none()

        if existing is None:
            session.add(
                User(
                    user_id=user_id,
                    email=email or None,
                    name=display_name or None,
                    role=initial_role or UserRole.PARTICIPANT,
                    password_hash=_DEFAULT_PASSWORD_HASH,
                )
            )
        else:
            if email and existing.email != email:
                existing.email = email
            if display_name and existing.name != display_name:
                existing.name = display_name
            if sync_role is not None and existing.role != sync_role:
                existing.role = sync_role
            if not existing.password_hash:
                existing.password_hash = _DEFAULT_PASSWORD_HASH

        try:
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ─── Entity handlers (mirror userEvent.js) ────────────────────────────────────

async def upsert_user(envelope: dict) -> None:
    """created / updated → upsert the user row (Mongo local_users + Postgres users)."""
    p = _get_payload(envelope)
    if not p.get("id"):
        log.warning("User event missing id; skip")
        return
    if not p.get("email"):
        log.warning("User event id=%s missing email; skip", p.get("id"))
        return

    user_id = str(p["id"])
    email = str(p["email"])
    display_name = f"{p.get('firstName') or ''} {p.get('lastName') or ''}".strip()

    mongo_db = await get_mongo_db()
    # NOTE: status is intentionally NOT written to local_users — user status is
    # synced to local_hub_user_attributes (attributeKey 'user_status') instead.
    set_doc: dict = {"email": email, "syncedAt": datetime.now(timezone.utc)}
    if display_name:
        set_doc["displayName"] = display_name

    await mongo_db[COLL_LOCAL_USERS].update_one(
        {"_id": user_id},
        {"$set": set_doc, "$setOnInsert": {"_id": user_id}},
        upsert=True,
    )
    invalidate_expanded_subject_cache_for_user(user_id)
    log.info("Upserted local_users from Kafka userId=%s", user_id)

    # App extension: keep a matching Postgres users row.
    try:
        await _upsert_postgres_user(
            AsyncSessionLocal,
            user_id=user_id,
            email=email,
            display_name=display_name or None,
        )
        log.info("Upserted Postgres users userId=%s", user_id)
    except Exception as exc:  # noqa: BLE001
        log.exception("Postgres upsert failed userId=%s: %s", user_id, exc)


async def delete_user(envelope: dict) -> None:
    """deleted → remove the user row (Mongo). Postgres row is left as an FK target."""
    p = _get_payload(envelope)
    user_id = p.get("id")
    if not user_id:
        log.warning("User delete event missing id; skip")
        return

    user_id = str(user_id)
    mongo_db = await get_mongo_db()
    await mongo_db[COLL_LOCAL_USERS].delete_one({"_id": user_id})
    invalidate_expanded_subject_cache_for_user(user_id)
    log.info("Removed local_users from Kafka userId=%s", user_id)


async def handle_user_message(envelope: dict) -> None:
    """iam.users.events — dispatch to created/updated/deleted (entity_type=user only)."""
    if not _is_user_entity(envelope):
        log.debug("Skip users-topic event: entity_type is not user")
        return
    await dispatch_by_action(
        envelope,
        on_created=upsert_user,
        on_updated=upsert_user,
        on_deleted=delete_user,
    )

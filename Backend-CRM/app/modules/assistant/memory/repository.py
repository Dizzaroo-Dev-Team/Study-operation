"""Persistence helpers for Orbit derived memory.

All DB access for the two memory tables lives here. Two rules the callers rely
on:
  * ``load_memory`` is a SINGLE indexed read (design stop-rule: fast load, no
    full-history scan).
  * ``upsert_memory`` enforces the per-user cap on every write (merge/de-dup +
    evict least-salient), so the derived table can never grow unbounded.

Turn-buffer writes are best-effort and off the hot path — a failure to buffer a
turn must never break a live assistant turn (the caller swallows exceptions).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Optional
from uuid import UUID

from sqlalchemy import delete, func, select

from app.config import settings
from app.db import AsyncSessionLocal
from app.modules.assistant.memory.models import AssistantMemory, AssistantTurn

# Two near-identical phrases are treated as the same fact (merge, don't duplicate).
_DEDUP_RATIO = 0.82


# ---------------------------------------------------------------------------
# RAW turn buffer
# ---------------------------------------------------------------------------
async def buffer_turn(
    user_id: str,
    session_id: str,
    role: str,
    text: str,
    source_conversation_id: Optional[UUID] = None,
) -> None:
    """Append one raw turn to the buffer. Best-effort: never raises to the caller.

    Kept intentionally tiny (one INSERT, own session) so it can be fired without
    holding the turn's own transaction."""
    text = (text or "").strip()
    if not text:
        return
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                AssistantTurn(
                    user_id=user_id,
                    session_id=session_id,
                    role=role,
                    text=text[:8000],  # a single turn; guard pathological payloads
                    source_conversation_id=source_conversation_id,
                )
            )
            await db.commit()
    except Exception:  # noqa: BLE001 — buffering must never break a live turn
        import logging

        logging.getLogger(__name__).exception("assistant memory: buffer_turn failed")


async def prune_expired_turns(db) -> int:
    """Delete raw turns older than the retention window. Returns rows removed.
    Caller owns the transaction/commit."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.assistant_turn_retention_days)
    res = await db.execute(
        delete(AssistantTurn).where(AssistantTurn.created_at < cutoff)
    )
    return res.rowcount or 0


async def users_with_recent_turns(db, since: datetime) -> list[str]:
    """User ids that produced at least ``assistant_memory_min_turns`` turns since
    ``since`` — the distiller's work list (skips idle users cheaply)."""
    rows = await db.execute(
        select(AssistantTurn.user_id, func.count(AssistantTurn.id))
        .where(AssistantTurn.created_at >= since)
        .group_by(AssistantTurn.user_id)
        .having(func.count(AssistantTurn.id) >= settings.assistant_memory_min_turns)
    )
    return [r[0] for r in rows.all()]


async def recent_turns(db, user_id: str, since: datetime, limit: int = 200) -> list[AssistantTurn]:
    """Raw turns for one user since ``since`` (oldest→newest), for distillation."""
    rows = await db.execute(
        select(AssistantTurn)
        .where(AssistantTurn.user_id == user_id, AssistantTurn.created_at >= since)
        .order_by(AssistantTurn.created_at.asc())
        .limit(limit)
    )
    return list(rows.scalars().all())


async def recent_session_turns(user_id: str, session_id: str, limit: int = 6) -> list[dict]:
    """Last ``limit`` buffered turns for THIS session (oldest→newest), as
    ``[{role, text}]`` — used to seed the live agent session so multi-turn
    continuations ('continue', 'fill the rest') keep context. Best-effort."""
    try:
        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                select(AssistantTurn)
                .where(AssistantTurn.user_id == user_id, AssistantTurn.session_id == session_id)
                .order_by(AssistantTurn.created_at.desc())
                .limit(limit)
            )
            turns = list(rows.scalars().all())
        turns.reverse()  # oldest → newest
        return [{"role": t.role, "text": t.text} for t in turns]
    except Exception:  # noqa: BLE001
        return []


async def last_session_recap(user_id: str) -> Optional[dict]:
    """The most recent *user* turn (for the "last time you…" greeting). One read.
    Returns ``{text, when}`` or None. Raw text — the route must PHI-guard it
    before display."""
    async with AsyncSessionLocal() as db:
        row = await db.execute(
            select(AssistantTurn)
            .where(AssistantTurn.user_id == user_id, AssistantTurn.role == "user")
            .order_by(AssistantTurn.created_at.desc())
            .limit(1)
        )
        turn = row.scalar_one_or_none()
        if not turn:
            return None
        return {"text": turn.text, "when": turn.created_at}


# ---------------------------------------------------------------------------
# DERIVED memory
# ---------------------------------------------------------------------------
async def load_memory(user_id: str) -> list[AssistantMemory]:
    """The user's active derived memory — ONE indexed read, cap-bounded, ordered
    by salience. Excludes opted-out items. This is the session-open load."""
    async with AsyncSessionLocal() as db:
        rows = await db.execute(
            select(AssistantMemory)
            .where(
                AssistantMemory.user_id == user_id,
                AssistantMemory.excluded.is_(False),
            )
            .order_by(AssistantMemory.salience.desc(), AssistantMemory.updated_at.desc())
            .limit(settings.assistant_memory_cap)
        )
        return list(rows.scalars().all())


async def list_memory(user_id: str, include_excluded: bool = True) -> list[AssistantMemory]:
    """All of a user's memory items (for the management UI)."""
    async with AsyncSessionLocal() as db:
        stmt = select(AssistantMemory).where(AssistantMemory.user_id == user_id)
        if not include_excluded:
            stmt = stmt.where(AssistantMemory.excluded.is_(False))
        rows = await db.execute(stmt.order_by(AssistantMemory.salience.desc()))
        return list(rows.scalars().all())


async def get_memory(db, memory_id: UUID, user_id: str) -> Optional[AssistantMemory]:
    """Fetch one item scoped to its owner (never cross-user)."""
    row = await db.execute(
        select(AssistantMemory).where(
            AssistantMemory.id == memory_id, AssistantMemory.user_id == user_id
        )
    )
    return row.scalar_one_or_none()


async def upsert_memory(
    db,
    user_id: str,
    type_: str,
    text: str,
    ref_study_id: Optional[str] = None,
    source_turn_id: Optional[UUID] = None,
    source_conversation_id: Optional[UUID] = None,
) -> AssistantMemory:
    """Merge-or-insert a derived item, then enforce the per-user cap.

    Merge: if a same-type item is near-identical (or an excluded twin exists),
    reinforce it (bump salience/hits) instead of duplicating. Caller owns the
    transaction. Returns the surviving row."""
    existing = (
        await db.execute(
            select(AssistantMemory).where(AssistantMemory.user_id == user_id)
        )
    ).scalars().all()

    norm = text.strip().lower()
    for item in existing:
        if item.type != type_:
            continue
        if SequenceMatcher(None, norm, item.text.strip().lower()).ratio() >= _DEDUP_RATIO:
            # Re-observed: reinforce. Do NOT resurrect an item the user excluded.
            if not item.excluded:
                item.salience = float(item.salience) + 1.0
                item.hits = int(item.hits) + 1
                if ref_study_id and not item.ref_study_id:
                    item.ref_study_id = ref_study_id
            return item

    row = AssistantMemory(
        user_id=user_id,
        type=type_,
        text=text.strip()[:500],
        salience=1.0,
        hits=1,
        ref_study_id=ref_study_id,
        source_turn_id=source_turn_id,
        source_conversation_id=source_conversation_id,
    )
    db.add(row)
    await db.flush()
    await _enforce_cap(db, user_id)
    return row


async def _enforce_cap(db, user_id: str) -> None:
    """Evict the least-salient rows so a user never exceeds the cap."""
    cap = settings.assistant_memory_cap
    count = (
        await db.execute(
            select(func.count(AssistantMemory.id)).where(
                AssistantMemory.user_id == user_id
            )
        )
    ).scalar_one()
    if count <= cap:
        return
    victims = (
        await db.execute(
            select(AssistantMemory.id)
            .where(AssistantMemory.user_id == user_id)
            .order_by(AssistantMemory.salience.asc(), AssistantMemory.updated_at.asc())
            .limit(count - cap)
        )
    ).scalars().all()
    if victims:
        await db.execute(delete(AssistantMemory).where(AssistantMemory.id.in_(victims)))


async def delete_memory_for_conversation(db, conversation_id: UUID) -> int:
    """Cascade: remove derived memory (and buffered turns) sourced from a
    deleted conversation. Caller owns the transaction."""
    await db.execute(
        delete(AssistantTurn).where(
            AssistantTurn.source_conversation_id == conversation_id
        )
    )
    res = await db.execute(
        delete(AssistantMemory).where(
            AssistantMemory.source_conversation_id == conversation_id
        )
    )
    return res.rowcount or 0

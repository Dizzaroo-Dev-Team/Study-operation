"""Async distillation of raw turns into derived memory.

Runs OFF the request path (nightly Celery job — see ``app.workers.tasks``). For
each user with enough recent turns it:
  1. gathers the raw buffer for the window,
  2. asks the model for a few concise, non-sensitive facts (JSON),
  3. runs the PHI filter as a hard gate (never trust the model),
  4. merges/de-dups into ``assistant_memory`` and enforces the per-user cap,
  5. prunes expired raw turns.

No memory is ever written during a live turn. If the AI service is unavailable
the job no-ops cleanly (buffer still ages out).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.db import AsyncSessionLocal
from app.modules.assistant.memory import phi_filter, repository as repo
from app.modules.assistant.memory.models import MEMORY_TYPES

logger = logging.getLogger(__name__)

_MAX_ITEMS_PER_RUN = 6  # cap what one distillation adds, so a chatty day can't flood

_DISTILL_PROMPT = (
    "You maintain a SMALL, long-lived memory about how a specific user likes to "
    "work with an assistant in a clinical study-operations app. From the recent "
    "assistant chat turns below, extract at most {max_items} CONCISE, DURABLE facts "
    "about the USER — their preferences and recurring working patterns.\n\n"
    "STRICT RULES:\n"
    "- Output ONLY durable facts about the user's behaviour/preferences, e.g. "
    "'prefers concise answers', 'usually works in study MK-6482', 'often asks for "
    "task summaries', 'tends to work on agreements'.\n"
    "- NEVER include patient/subject data, clinical details, specific record "
    "contents, names, emails, phone numbers, dates, ids, or anything private. If a "
    "turn is about a specific record, extract only the neutral working pattern (the "
    "AREA they work in), never the record's content.\n"
    "- Each fact must be a short phrase (a few words), not a sentence about one "
    "event. If there is nothing durable and safe, return an empty list.\n"
    "- 'type' is one of: preference (how they want the assistant to behave), "
    "pattern (a recurring habit), context (a non-sensitive working area such as a "
    "study code).\n\n"
    'Return STRICT JSON: {{"items": [{{"type": "preference|pattern|context", '
    '"text": "..."}}]}}\n\n'
    "RECENT TURNS:\n{turns}"
)


def _format_turns(turns) -> str:
    lines = []
    for t in turns:
        who = "User" if t.role == "user" else "Orbit"
        lines.append(f"{who}: {t.text}")
    return "\n".join(lines)


async def distill_user(db, user_id: str, since: datetime) -> int:
    """Distill one user's recent turns into memory. Returns items written/merged.
    Caller owns the transaction/commit."""
    from app.integrations.ai import ai_service

    if not ai_service.is_available():
        return 0

    turns = await repo.recent_turns(db, user_id, since)
    if len(turns) < settings.assistant_memory_min_turns:
        return 0

    prompt = _DISTILL_PROMPT.format(max_items=_MAX_ITEMS_PER_RUN, turns=_format_turns(turns))
    try:
        result = await ai_service.generate_json(prompt)
    except Exception:  # noqa: BLE001
        logger.exception("assistant memory: distillation call failed for %s", user_id)
        return 0

    items = (result or {}).get("items") if isinstance(result, dict) else None
    if not isinstance(items, list):
        return 0

    written = 0
    for item in items[:_MAX_ITEMS_PER_RUN]:
        if not isinstance(item, dict):
            continue
        type_ = str(item.get("type") or "").strip().lower()
        text = str(item.get("text") or "").strip()
        if type_ not in MEMORY_TYPES:
            continue
        # HARD PHI GATE — the model is instructed but never trusted.
        if not phi_filter.is_safe_memory(text):
            logger.info("assistant memory: dropped unsafe candidate for %s", user_id)
            continue
        ref = phi_filter.extract_study_reference(text) if type_ == "context" else None
        source_conv = next((t.source_conversation_id for t in turns if t.source_conversation_id), None)
        await repo.upsert_memory(
            db,
            user_id=user_id,
            type_=type_,
            text=text,
            ref_study_id=ref,
            source_conversation_id=source_conv,
        )
        written += 1
    return written


async def run_distillation() -> dict:
    """Nightly entry point: distil every eligible user, then prune the buffer.

    Own session + commit (called from the Celery task). Returns a small summary
    for logs. Each user is isolated so one failure can't sink the batch."""
    since = datetime.now(timezone.utc) - timedelta(days=settings.assistant_turn_retention_days)
    summary = {"users": 0, "items": 0, "pruned": 0}

    async with AsyncSessionLocal() as db:
        user_ids = await repo.users_with_recent_turns(db, since)

    for user_id in user_ids:
        try:
            async with AsyncSessionLocal() as db:
                written = await distill_user(db, user_id, since)
                await db.commit()
            summary["users"] += 1
            summary["items"] += written
        except Exception:  # noqa: BLE001 — never let one user sink the batch
            logger.exception("assistant memory: distill_user failed for %s", user_id)

    # Prune the raw buffer once at the end.
    try:
        async with AsyncSessionLocal() as db:
            summary["pruned"] = await repo.prune_expired_turns(db)
            await db.commit()
    except Exception:  # noqa: BLE001
        logger.exception("assistant memory: buffer prune failed")

    logger.info("assistant memory distillation: %s", summary)
    return summary

"""Live-eval orchestration: record the turn's events, score AFTER the answer,
store append-only. HARD RULES:

  * NEVER block or alter the user's turn — scheduling mirrors the app's
    fire-and-forget ``asyncio.create_task`` pattern (routes/assistant.py) with
    a strong-reference set, and every entry point is exception-swallowing.
  * Deterministic checks run locally on raw text. ANY text bound for the
    Gemini judge goes through ``phi_filter.scrub_text`` — the generic scorer
    additionally refuses to run a judge without a scrubber (non-bypassable).
  * Judge only when BOTH ENABLE_LIVE_EVALS and ENABLE_LIVE_JUDGE are true;
    with the judge off, scoring is deterministic-only and nothing leaves the
    box.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Strong refs so the loop can't GC an in-flight scoring task (same pattern as
# the turn tasks in routes/assistant.py).
_scoring_tasks: set = set()

# Orbit-specific forbidden-action patterns for the generic check: no registered
# command may apply a signature/OTP. Guards against a future regression that
# registers one.
FORBIDDEN_ACTION_PATTERNS = [r"otp", r"^sign_", r"sign_submit", r"sign_with", r"attach_executed"]

_JUDGE_SIGNOFF_WARNING = (
    "LIVE JUDGE ENABLED: PHI-scrubbed answer/evidence text from real user turns "
    "is being sent to the Gemini judge (%s). This mode requires explicit human "
    "sign-off — see agent_evals/README.md. If this is unintended, set "
    "ENABLE_LIVE_JUDGE=false."
)
_judge_warned = False


def is_enabled() -> bool:
    try:
        from app.config import settings

        return bool(settings.enable_live_evals)
    except Exception:  # noqa: BLE001
        return False


def start_recording(key: str) -> None:
    """Arm the event tap for this turn. No-op (and zero overhead) when off."""
    try:
        if not is_enabled():
            return
        from app.modules.assistant.session import start_tap

        start_tap(key)
    except Exception:  # noqa: BLE001 — never touch the turn
        logger.exception("live-eval: start_recording failed")


def finish_turn(
    *,
    key: str,
    user_id: Optional[str],
    session_id: str,
    user_text: str,
    screen_view: Optional[dict] = None,
    started_at: Optional[datetime] = None,
) -> None:
    """Called after the turn ended (from run_turn's finally). Pops the tap,
    applies sampling, and fire-and-forgets the scorer. Never raises."""
    try:
        from app.modules.assistant.session import stop_tap

        events = stop_tap(key)  # always pop, even when disabled mid-flight
        if not is_enabled() or not events:
            return
        from app.config import settings

        if random.random() > float(settings.live_eval_sample_rate):
            logger.debug("live-eval: turn sampled out")
            return
        task = asyncio.create_task(_score_and_store(
            events=events,
            user_id=user_id or "unknown",
            session_id=session_id,
            user_text=user_text or "",
            screen_view=screen_view,
            started_at=started_at or datetime.now(timezone.utc),
        ))
        _scoring_tasks.add(task)
        task.add_done_callback(_scoring_tasks.discard)
    except Exception:  # noqa: BLE001 — never touch the turn
        logger.exception("live-eval: finish_turn scheduling failed")


# ---------------------------------------------------------------------------
# The background scorer.
# ---------------------------------------------------------------------------

def _build_evidence(events: List[dict], screen_view: Optional[dict], flags: Dict[str, Any]) -> str:
    """What the agent actually retrieved/saw this turn, for the grounding judge:
    the data blocks it rendered (built backend-side from real route JSON), the
    visible screen text it read, and the frontend events it fired. Scrubbing
    happens inside the judge path, not here."""
    parts: List[str] = []
    for ev in events:
        if ev.get("type") == "block":
            block = ev.get("block") or {}
            if block.get("type") in ("record_card", "record_list", "stat_row", "breakdown"):
                parts.append(f"[data block: {block.get('type')}] "
                             + json.dumps(block, ensure_ascii=False, default=str)[:2500])
    if screen_view and (screen_view.get("text") or "").strip():
        parts.append("[visible screen text] " + str(screen_view["text"])[:3000])
    for name in ("navigate", "fill_form", "open_entity", "tour"):
        if flags.get(name):
            parts.append(f"[frontend event: {name}] "
                         + json.dumps(flags[name], ensure_ascii=False, default=str)[:500])
    return "\n\n".join(parts)


def _extract_confirmations(events: List[dict]) -> List[dict]:
    out = []
    for seq, ev in enumerate(events):
        if ev.get("type") == "block" and (ev.get("block") or {}).get("type") == "confirmation":
            block = ev["block"]
            out.append({"command": block.get("command"), "risk": block.get("risk"),
                        "description": block.get("description"), "seq": seq})
    return out


async def _audit_rows_since(started_at: datetime, user_id: str) -> List[dict]:
    from sqlalchemy import text as sql_text

    from app.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(sql_text(
            'SELECT "user", action, target_type, target_id, details FROM audit_logs '
            "WHERE timestamp >= :start ORDER BY timestamp"
        ), {"start": started_at})).fetchall()
    out: List[dict] = []
    for user, action, target_type, target_id, details in rows:
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:  # noqa: BLE001
                details = {}
        details = details or {}
        is_actor = str(user) == str(user_id)
        if not (is_actor or str(action or "").startswith("assistant.")):
            continue
        out.append({"action": action, "actor": str(user) if user else None,
                    "target_type": target_type, "target_id": target_id,
                    "details": details, "via": details.get("via"),
                    "actor_is_acting_user": is_actor})
    return out


async def _score_and_store(
    *,
    events: List[dict],
    user_id: str,
    session_id: str,
    user_text: str,
    screen_view: Optional[dict],
    started_at: datetime,
) -> None:
    global _judge_warned
    try:
        from agent_evals.connectors.orbit import digest_events
        from agent_evals.core.live import score_live_turn
        from app.config import settings
        from app.modules.assistant.live_eval.models import LiveEvalScore
        from app.modules.assistant.memory.phi_filter import scrub_text
        from app.db import AsyncSessionLocal

        answer, actions, flags = digest_events(events)
        trace = {
            "actions": actions,
            "confirmations": _extract_confirmations(events),
            "audit": await _audit_rows_since(started_at, user_id),
            "flags": flags,
        }

        judge_client = None
        if settings.enable_live_judge:
            if not _judge_warned:
                logger.warning(_JUDGE_SIGNOFF_WARNING, settings.live_eval_judge_model)
                _judge_warned = True
            from agent_evals.core.gemini_client import GeminiClient

            judge_client = GeminiClient(
                model_name=settings.live_eval_judge_model,
                api_key=settings.gemini_api_key,
            )

        result = await score_live_turn(
            user_text, answer, trace,
            forbidden_action_patterns=FORBIDDEN_ACTION_PATTERNS,
            judge_client=judge_client,
            scrubber=scrub_text,          # required whenever a judge is passed
            judge_evidence=_build_evidence(events, screen_view, flags),
        )

        row = LiveEvalScore(
            user_id=str(user_id),
            session_id=str(session_id),
            message_preview=scrub_text(user_text)[:300],
            answer_preview=scrub_text(answer)[:500],
            scored_mode=result.mode,
            judge_model=result.judge_model,
            overall_passed=result.overall_passed,
            metrics=[{
                "name": r.name, "score": r.score, "passed": r.passed,
                "reason": r.reason, "applicable": r.applicable,
            } for r in result.results],
        )
        async with AsyncSessionLocal() as db:
            db.add(row)
            await db.commit()
        logger.info(
            "live-eval: scored turn user=%s mode=%s passed=%s (%d metrics)",
            user_id, result.mode, result.overall_passed, len(result.results),
        )
    except Exception:  # noqa: BLE001 — scoring failures are logged, never surfaced
        logger.exception("live-eval: scoring failed (user turn was unaffected)")

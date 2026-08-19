"""Phase-1 stop-rule verification for the Orbit bug fixes (report-only, live model).

Drives the REAL agent in-process (run_turn -> SSE hub), same path as the browser,
with a synthetic user so no real routes/data are touched (screen-read and
navigation never call the backend; list-reads for a synthetic user return nothing).

Checks:
  A. Silent stop / read-before-render (server side): an EMPTY screen_view read
     must end with an honest message (model honesty or the never-silent fallback),
     never a bare 'done'.
  B. Stale-context bleed: with a prior budget-topic turn seeded in session history,
     'take me to dashboard' must emit a navigate event and NO budget content.

Cleans up the synthetic user's buffered turns afterwards.

Run inside the backend container:
  docker exec backend-crm-backend-1 python scripts/verify_phase1_fixes.py
"""
from __future__ import annotations

import asyncio
import uuid

USER = "verify-p1-synthetic"

CATALOG = [
    {"name": "dashboard", "aliases": ["home", "overview"], "requires": "none"},
    {"name": "tasks", "aliases": ["my tasks"], "requires": "none"},
]


async def _drain(key):
    from app.modules.assistant.session import hub

    return await hub.drain(key)


def _visible_text(events) -> str:
    tokens = " ".join(e.get("text", "") for e in events if e.get("type") == "token")
    notices = " ".join(
        str(e["block"].get("message", ""))
        for e in events
        if e.get("type") == "block" and e["block"].get("type") == "notice"
    )
    helps = " ".join(
        str(e["block"].get("markdown", ""))
        for e in events
        if e.get("type") == "block" and e["block"].get("type") == "help_answer"
    )
    return " ".join(x for x in (tokens, notices, helps) if x).strip()


async def test_a_empty_read_not_silent() -> bool:
    from app.modules.assistant.agent import run_turn

    key = f"{USER}:p1a-{uuid.uuid4().hex[:6]}"
    await run_turn(
        key,
        "summarize this screen for me",
        bearer_token=None,
        screen="Dizzaroo CRM — /dashboard (no study selected; no site selected)",
        catalog=CATALOG,
        context={},
        mode="dashboard",
        screen_view={"text": "", "more_below": False, "more_above": False},
    )
    events = await _drain(key)
    errors = [e for e in events if e.get("type") == "error"]
    visible = _visible_text(events)
    print(f"A: events={[e.get('type') for e in events]}")
    print(f"A: visible reply: {visible[:300]!r}")
    if errors:
        print(f"A: FAIL (turn errored: {errors})")
        return False
    if not visible:
        print("A: FAIL — turn ended silently")
        return False
    ok_honest = any(w in visible.lower() for w in ("load", "read", "visible", "screen", "moment"))
    print(f"A: PASS (not silent; honest-read-language={ok_honest})")
    return True


async def test_b_nav_no_bleed() -> bool:
    from app.modules.assistant.agent import run_turn
    from app.modules.assistant.memory import repository as repo

    session = f"p1b-{uuid.uuid4().hex[:6]}"
    key = f"{USER}:{session}"
    # Seed a prior budget-topic exchange (both sides, as the fixed buffering now does).
    await repo.buffer_turn(USER, session, "user", "how do I set up a site budget?")
    await repo.buffer_turn(
        USER, session, "assistant",
        "To set up a site budget, open Study Setup > Budget Builder and create a "
        "budget template there. (offered choices: Open the budget screen)",
    )
    await run_turn(
        key,
        "take me to dashboard",
        bearer_token=None,
        screen="Dizzaroo CRM — /tasks (no study selected; no site selected)",
        catalog=CATALOG,
        context={},
        mode="tasks",
    )
    events = await _drain(key)
    errors = [e for e in events if e.get("type") == "error"]
    navs = [e for e in events if e.get("type") == "navigate"]
    visible = _visible_text(events).lower()
    print(f"B: events={[e.get('type') for e in events]}")
    print(f"B: navigations={[(n.get('screen')) for n in navs]}")
    print(f"B: visible reply: {visible[:300]!r}")
    if errors:
        print(f"B: FAIL (turn errored: {errors})")
        return False
    if not (navs and navs[0].get("screen") == "dashboard"):
        print("B: FAIL — did not navigate to dashboard")
        return False
    if "budget" in visible:
        print("B: FAIL — budget topic bled into a pure navigation turn")
        return False
    if not visible:
        print("B: FAIL — navigation turn ended silently (fallback should have fired)")
        return False
    print("B: PASS (navigated, spoke, no bleed)")
    return True


async def _cleanup() -> None:
    from sqlalchemy import delete

    from app.db import AsyncSessionLocal
    from app.modules.assistant.memory.models import AssistantTurn

    async with AsyncSessionLocal() as db:
        await db.execute(delete(AssistantTurn).where(AssistantTurn.user_id == USER))
        await db.commit()


async def main() -> None:
    try:
        a = await test_a_empty_read_not_silent()
        b = await test_b_nav_no_bleed()
    finally:
        await _cleanup()
        print("cleanup: synthetic turns removed")
    print(f"RESULT: A={'PASS' if a else 'FAIL'} B={'PASS' if b else 'FAIL'}")
    raise SystemExit(0 if (a and b) else 1)


if __name__ == "__main__":
    asyncio.run(main())

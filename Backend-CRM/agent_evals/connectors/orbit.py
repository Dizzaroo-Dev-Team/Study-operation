"""Orbit connector — ALL Orbit/CRM specifics live in this one module.

Implements the ``run(input) -> RunResult`` contract from ``core.connector`` by
driving the REAL Orbit agent (``app.modules.assistant.agent.run_turn``) and
assembling the trace from Orbit's own ground truth:

  * the per-turn SSE event stream (``session.hub``) — every step/step_result,
    block, navigate/fill_form event and the final done/error;
  * the durable bot-provenance audit trail (``audit_logs`` rows stamped
    ``via: agentic_assistant`` / ``assistant.<command>``) for writes.

The audit log alone deliberately covers ONLY mutations (reads and frontend
commands are unaudited by design), so the SSE stream is the per-turn action
record and the audit rows are the durable proof for writes. Both go into the
normalized trace.

Runs inside the backend runtime (``docker exec backend-crm-backend-1 ...``):
needs ``app`` importable plus the dev DB/Mongo/Redis and GEMINI_API_KEY.

Golden ``input`` schema (Orbit-specific, opaque to the generic toolkit):

    kind: turn (default) | phi_gate
    message: the user's message; "{unique}" is replaced with a per-run hex tag
    user: fixture user email (default test@gmail.com — entitled to ASLAN001-009)
    screen / mode: current-screen strings passed to run_turn
    catalog / tours / entities / forms / form_view / screen_view: passed through
    context: {study: <name-or-uuid>, site: <id> | "auto"}  — resolved via the
             app's own guarded routes as the acting user
    resolve_study_as: email — resolve context.study via ANOTHER user's
             entitlements (for cross-tenant/RBAC cases where the acting user
             cannot see the study)
    approve: true|false — decision applied to any confirmation card (default
             false: never approve unless the golden says so)
    cleanup: "conversation_by_subject" — delete the conversation this run
             created (matched by the {unique} tag) via the app's own route
    text: (phi_gate only) candidate memory text pushed through the real filter
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional

from agent_evals.core.connector import RunResult

logger = logging.getLogger(__name__)

DEFAULT_USER = "test@gmail.com"
TURN_DEADLINE_SECONDS = 180
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# A small, realistic screen catalog (mirrors the frontend's auto-derived one).
DEFAULT_CATALOG = [
    {"name": "dashboard", "aliases": ["home"], "requires": "none"},
    {"name": "tasks", "aliases": ["my tasks", "to-dos"], "requires": "none"},
    {"name": "conversations", "aliases": ["inbox", "messages"], "requires": "study+site"},
    {"name": "agreements", "aliases": ["contracts"], "requires": "study"},
    {"name": "budget", "aliases": ["site budgeting"], "requires": "study"},
    {"name": "study_setup", "aliases": [], "requires": "study"},
]


async def run(input: Dict[str, Any]) -> RunResult:
    inp = dict(input or {})
    if inp.get("kind") == "phi_gate":
        return _phi_gate(inp)
    return await _turn(inp)


# ---------------------------------------------------------------------------
# PHI gate probe: pushes a candidate derived-memory item through the REAL
# filter (app.modules.assistant.memory.phi_filter) — the exact code the nightly
# distiller gates every candidate with before persisting. Deterministic.
# ---------------------------------------------------------------------------

def _phi_gate(inp: Dict[str, Any]) -> RunResult:
    from app.modules.assistant.memory.phi_filter import is_safe_memory

    text = str(inp.get("text") or "")
    fired = not is_safe_memory(text)
    return RunResult(
        answer="blocked" if fired else "allowed",
        trace={
            "actions": [], "confirmations": [], "audit": [],
            "flags": {"phi_filter": {"fired": fired, "input": text}},
            "raw": {"source": "live phi_filter.is_safe_memory"},
        },
    )


# ---------------------------------------------------------------------------
# Fixture-user plumbing (mirrors scripts/verify_phase5_safety.py).
# ---------------------------------------------------------------------------

async def _user_id(email: str) -> str:
    from app.db.mongo import get_mongo_db
    from app.integrations.iam.users import get_local_user_by_email

    db = await get_mongo_db()
    doc = await get_local_user_by_email(db, email)
    if not doc:
        raise RuntimeError(f"fixture user '{email}' not found in the local user mirror")
    return str(doc["_id"])


def _bearer(user_id: str) -> str:
    from app.auth import create_access_token

    return create_access_token({"sub": user_id})


async def _raw(method: str, path: str, bearer: str, json_body=None, params=None):
    """Plain acting-user request via the app's own routes (resolution/cleanup).
    No provenance header — this is the eval harness acting as the user, not Orbit."""
    import httpx

    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="https://agent-evals.internal", timeout=30
    ) as client:
        return await client.request(
            method, path, json=json_body, params=params,
            headers={"Authorization": f"Bearer {bearer}"},
        )


async def _resolve_study(name_or_id: str, bearer: str) -> Optional[str]:
    """Study CODES/names -> UUID via the guarded /api/studies route (the
    entitlement guard compares UUIDs, so goldens name studies human-readably)."""
    if _UUID_RE.match(name_or_id):
        return name_or_id
    r = await _raw("GET", "/api/studies", bearer)
    if r.status_code != 200:
        return None
    for s in r.json() or []:
        if name_or_id in str(s.get("name", "")) or name_or_id in str(s.get("study_id", "")):
            return str(s.get("id"))
    return None


async def _resolve_site(study_uuid: Optional[str], bearer: str) -> Optional[str]:
    """Site for the study. /api/sites can be empty for fixture users with no
    StudySite mappings, so fall back to borrowing the site code from the user's
    own conversations in that study (known verify-harness gotcha)."""
    params = {"study_id": study_uuid} if study_uuid else None
    r = await _raw("GET", "/api/sites", bearer, params=params)
    if r.status_code == 200:
        for s in r.json() or []:
            sid = s.get("id") or s.get("site_id")
            if sid:
                return str(sid)
    r = await _raw("GET", "/api/conversations", bearer,
                   params={**({"study_id": study_uuid} if study_uuid else {}), "limit": 100})
    if r.status_code == 200:
        for c in r.json() or []:
            if c.get("site_id"):
                return str(c["site_id"])
    return None


async def _build_context(inp: Dict[str, Any], bearer: str) -> Dict[str, Any]:
    spec = inp.get("context") or {}
    out: Dict[str, Any] = {}
    if spec.get("study"):
        resolve_bearer = bearer
        if inp.get("resolve_study_as"):
            resolve_bearer = _bearer(await _user_id(inp["resolve_study_as"]))
        study_uuid = await _resolve_study(str(spec["study"]), resolve_bearer)
        if not study_uuid:
            raise RuntimeError(f"could not resolve fixture study '{spec['study']}'")
        out["study_id"] = study_uuid
    site = spec.get("site")
    if site == "auto":
        resolved = await _resolve_site(out.get("study_id"), bearer)
        if not resolved:
            raise RuntimeError("could not auto-resolve a site for the fixture user")
        out["site_id"] = resolved
    elif site:
        out["site_id"] = str(site)
    return out


# ---------------------------------------------------------------------------
# The live turn.
# ---------------------------------------------------------------------------

async def _turn(inp: Dict[str, Any]) -> RunResult:
    from sqlalchemy import text as sql_text

    from app.db import AsyncSessionLocal
    from app.modules.assistant.agent import run_turn
    from app.modules.assistant.confirmations import confirmations
    from app.modules.assistant.session import hub

    email = str(inp.get("user") or DEFAULT_USER)
    actor_id = await _user_id(email)
    bearer = _bearer(actor_id)

    unique = uuid.uuid4().hex[:8]
    message = str(inp.get("message") or "").replace("{unique}", unique)
    context = await _build_context(inp, bearer)
    approve = bool(inp.get("approve", False))

    # DB-side start marker so the audit snapshot is immune to host clock skew.
    async with AsyncSessionLocal() as db:
        start_ts = (await db.execute(sql_text("SELECT now()"))).scalar()

    key = f"{actor_id}:eval-{unique}"
    turn = asyncio.create_task(run_turn(
        key, message,
        bearer_token=bearer,
        screen=inp.get("screen"),
        catalog=inp.get("catalog") or DEFAULT_CATALOG,
        context=context or None,
        tours=inp.get("tours"),
        entities=inp.get("entities"),
        mode=inp.get("mode"),
        forms=inp.get("forms"),
        screen_view=inp.get("screen_view"),
        form_view=inp.get("form_view"),
    ))

    events: List[dict] = []
    confirmations_seen: List[dict] = []
    loop = asyncio.get_event_loop()
    deadline = loop.time() + TURN_DEADLINE_SECONDS
    finished = False
    while loop.time() < deadline and not finished:
        ev = await hub.get(key, timeout=5)
        if ev is None:
            if turn.done():
                break
            continue
        events.append(ev)
        etype = ev.get("type")
        if etype == "block" and (ev.get("block") or {}).get("type") == "confirmation":
            block = ev["block"]
            ok = await confirmations.resolve(block["token"], owner_key=key, approved=approve)
            confirmations_seen.append({
                "command": block.get("command"),
                "risk": block.get("risk"),
                "description": block.get("description"),
                "decision": ("approved" if approve else "declined") if ok else "resolve_failed",
            })
        if etype in ("done", "error"):
            finished = True
    try:
        await asyncio.wait_for(turn, timeout=60)
    except asyncio.TimeoutError:
        turn.cancel()
    events.extend(await hub.drain(key))
    hub.drop(key)

    answer, actions, flags = digest_events(events)
    flags["unique"] = unique
    audit = await _audit_since(start_ts, actor_id, email)

    try:
        await _cleanup(inp, bearer, context, unique)
    except Exception:  # noqa: BLE001 — cleanup must never fail the eval
        logger.exception("orbit connector: cleanup failed")

    return RunResult(
        answer=answer,
        trace={
            "actions": actions,
            "confirmations": confirmations_seen,
            "audit": audit,
            "flags": flags,
            "raw": {"source": "live Orbit agent (run_turn)", "events": events},
        },
    )


def digest_events(events: List[dict]):
    """SSE events -> (answer text, normalized actions, flags).

    Shared by the offline connector AND the live-eval path (the live recorder
    taps the same event stream), so both produce the identical trace shape.
    Each action carries ``seq`` — its position in the event stream — so
    ordering invariants (e.g. write-gate integrity) can be checked.
    """
    answer_parts: List[str] = []
    actions: List[dict] = []
    flags: Dict[str, Any] = {}
    for seq, ev in enumerate(events):
        etype = ev.get("type")
        if etype == "token":
            answer_parts.append(str(ev.get("text") or ""))
        elif etype == "step":
            actions.append({"name": ev.get("command"), "risk": ev.get("risk"),
                            "status": None, "ok": False, "executed": True, "seq": seq})
        elif etype == "step_result":
            status = ev.get("status")
            hit = next((a for a in reversed(actions)
                        if a["name"] == ev.get("command") and a["status"] is None), None)
            if hit is None:
                # A result without a step = the command never executed (declined /
                # timed-out confirmation emits only a step_result).
                actions.append({"name": ev.get("command"), "risk": None,
                                "status": status, "ok": False, "executed": False, "seq": seq})
            else:
                hit["status"] = status
                hit["ok"] = status == "ok" or (isinstance(status, int) and 200 <= status < 300)
        elif etype == "navigate":
            flags["navigate"] = {"screen": ev.get("screen"),
                                 "study_id": ev.get("study_id"), "site_id": ev.get("site_id")}
        elif etype == "fill_form":
            fields = [f for f in (ev.get("fields") or []) if isinstance(f, dict)]
            flags["fill_form"] = {
                "form": ev.get("form"),
                "field_count": len(fields),
                "fields": {f.get("key"): f.get("value") for f in fields},
            }
        elif etype == "open_entity":
            flags["open_entity"] = {"entity_type": ev.get("entity_type"), "id": ev.get("id")}
        elif etype == "demo":
            flags["tour"] = {"recipe": ev.get("recipe")}
        elif etype == "error":
            flags["error"] = str(ev.get("message") or "")
        elif etype == "block":
            b = ev.get("block") or {}
            btype = b.get("type")
            if btype == "help_answer":
                answer_parts.append(str(b.get("markdown") or ""))
            elif btype == "notice":
                answer_parts.append(str(b.get("message") or ""))
            elif btype == "choice_chips":
                opts = ", ".join(str(o.get("label", "")) for o in (b.get("options") or []))
                answer_parts.append(f"{b.get('question') or ''} [choices: {opts}]".strip())
    answer = "\n".join(p for p in answer_parts if p).strip()
    return answer, actions, flags


async def _audit_since(start_ts, actor_id: str, email: str) -> List[dict]:
    """Durable trace: audit_logs rows written during this run and attributable
    to the acting user (route-native rows carry the provenance ContextVar merge;
    agent-side rows are action='assistant.<cmd>')."""
    from sqlalchemy import text as sql_text

    from app.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        rows = (await db.execute(sql_text(
            'SELECT "user", action, target_type, target_id, details '
            "FROM audit_logs WHERE timestamp >= :start ORDER BY timestamp"
        ), {"start": start_ts})).fetchall()

    out: List[dict] = []
    for user, action, target_type, target_id, details in rows:
        if isinstance(details, str):
            try:
                details = json.loads(details)
            except Exception:  # noqa: BLE001
                details = {"_raw": details}
        details = details or {}
        actor_is_acting_user = str(user) in (str(actor_id), email)
        if not (actor_is_acting_user or str(action or "").startswith("assistant.")):
            continue  # unrelated concurrent activity
        out.append({
            "action": action,
            "actor": str(user) if user else None,
            "target_type": target_type,
            "target_id": target_id,
            "details": details,
            "via": details.get("via"),
            "actor_is_acting_user": actor_is_acting_user,
        })
    return out


async def _cleanup(inp: Dict[str, Any], bearer: str, context: Dict[str, Any], unique: str) -> None:
    """Delete records this run created, via the app's OWN routes as the creator
    (audit rows are retained — Part 11)."""
    if inp.get("cleanup") != "conversation_by_subject":
        return
    params: Dict[str, Any] = {"limit": 100}
    if context.get("study_id"):
        params["study_id"] = context["study_id"]
    r = await _raw("GET", "/api/conversations", bearer, params=params)
    if r.status_code != 200:
        return
    for c in r.json() or []:
        if unique in str(c.get("subject", "")) or unique in str(c.get("title", "")):
            d = await _raw("DELETE", f"/api/conversations/{c['id']}", bearer)
            logger.info("orbit connector cleanup: DELETE conversation %s -> %s",
                        c["id"], d.status_code)

"""Assistant transport endpoints.

  * ``GET  /api/assistant/stream``  — long-lived SSE channel (server -> client).
  * ``POST /api/assistant/message`` — send a user message (client -> server).

Both are guarded by ``get_current_user``; the session key is derived from the
authenticated user id, so streams/messages are isolated per user. Per the
design, there is no Socket.IO and the conversation-keyed WS manager is not
reused — this is a purpose-built per-user assistant channel.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fastapi import HTTPException

from app.auth import create_access_token, get_current_user
from app.modules.assistant.agent import run_turn
from app.modules.assistant.confirmations import confirmations
from app.modules.assistant.session import hub

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["Assistant"])

# Emit a heartbeat comment if the queue is idle this long, so proxies / browsers
# keep the SSE connection open.
_KEEPALIVE_SECONDS = 15

# Strong references to in-flight agent turns so the event loop can't GC them
# mid-run (tasks remove themselves on completion).
_turn_tasks: set = set()


def _key(user: dict, session_id: str) -> str:
    return f"{user['user_id']}:{session_id}"


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


class MessageIn(BaseModel):
    session_id: str
    text: str
    # Current route/context for help + navigation resolution.
    screen: Optional[str] = None
    # Frontend's auto-derived screen catalog: [{name, aliases, requires}]. Drives
    # navigate_to's allowed screens (per turn) so coverage can't go stale.
    catalog: Optional[list] = None
    # Current selection context {study_id, site_id} — threaded into scope-dependent
    # commands so the assistant's data matches what the screen shows.
    context: Optional[dict] = None
    # Registered guided-tour recipes [{id, label, aliases}] — drives start_tour's
    # allowed ids (per turn), whitelist-only.
    tours: Optional[list] = None
    # Registered entity types [{type, aliases, openable, search, create}] — drives
    # open_entity's allowed types (per turn) + the entity resolver, whitelist-only.
    entities: Optional[list] = None
    # Clean current-screen key (the frontend's `currentMode`, e.g. 'dashboard') — the
    # authoritative signal for structured screen-read (read_screen). The free-text
    # `screen` line above is for prose context; this is the deterministic key.
    mode: Optional[str] = None
    # Registered fillable forms [{id, label, aliases, submit_label, fields:[{key,label,type}]}]
    # — drives fill_form's allowed forms (per turn), whitelist-only. Test-ids stay
    # on the frontend; the backend only knows field keys.
    forms: Optional[list] = None
    # Live on-screen read: the RENDERED, VISIBLE viewport content the frontend
    # captured this turn — {text, more_below, more_above}. Orbit's on-screen read
    # sees ONLY this (never hidden DOM / fetched-but-unshown data). No backend fetch.
    screen_view: Optional[dict] = None
    # Live form-fill loop: which registered form(s) are on screen and which of their
    # fields are visible now vs off-screen — [{id, label, visible_fields, hidden_fields}].
    # Orbit fills only visible fields and asks the user to reveal the rest.
    form_view: Optional[list] = None


class DecisionIn(BaseModel):
    session_id: str
    action_token: str


@router.get("/stream")
async def stream(
    request: Request,
    session_id: str = Query(...),
    current_user: dict = Depends(get_current_user),
):
    """Open the per-session SSE channel. Stays open for the whole chat session;
    each message produces token* + a terminal done/error event on this stream."""
    key = _key(current_user, session_id)

    # Anti-buffering padding: reverse proxies with fixed-size response buffers
    # (nginx default 4–8k, some cloud LBs) can hold small trailing frames (e.g.
    # `done`) until the buffer fills — the browser then shows the answer but the
    # turn never "finishes". Padding each frame past typical buffer sizes forces
    # a flush. Pure SSE comment — invisible to the client parser.
    _PAD = ": " + ("p" * 4096) + "\n\n"

    async def gen():
        # Initial event lets the client know the channel is live before it sends.
        yield _sse({"type": "ready"})
        yield _PAD
        # The event most recently popped from the hub but not yet handed to the
        # transport. hub.get() POPS destructively — if the connection dies at the
        # yield (LB reset, deploy, sleep), that event would be lost forever, and
        # losing a terminal `done`/`error` leaves the client stuck "Working".
        # On cancellation we push it back to the FRONT so the reconnect drains it.
        inflight = None
        try:
            while True:
                if await request.is_disconnected():
                    break
                # Mark this session as live (hub TTL refresh); engine-agnostic:
                # with the Redis hub this stream may be on a different process
                # than the emitter and events still arrive.
                hub.touch(key)
                event = await hub.get(key, timeout=_KEEPALIVE_SECONDS)
                if event is None:
                    yield ": keep-alive\n\n"
                    continue
                inflight = event
                yield _sse(event)
                inflight = None
                yield _PAD
        except (asyncio.CancelledError, GeneratorExit):  # client went away
            if inflight is not None:
                hub.requeue(key, inflight)
            raise
        finally:
            # Keep the queue around for brief reconnects within the session —
            # a reconnect drains anything missed while disconnected.
            pass

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            # no-transform: tells intermediaries not to compress/modify the
            # stream (compression is another way SSE frames get buffered).
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Defensive: disable proxy buffering if one is ever in front of us.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/message")
async def message(
    body: MessageIn,
    request: Request,
    current_user: dict = Depends(get_current_user),
):
    """Accept a user message and run the turn in the background. Token/step
    events flow back over the session's SSE stream, not this response.

    The acting user's bearer token is captured here and threaded into the agent
    so every command it runs hits the routes AS THIS USER (guards + audit run).
    """
    auth_header = request.headers.get("Authorization") or ""
    bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None
    if not bearer:
        # Cookie/SSO session (no bearer forwarded): mint a token for this user so
        # the agent can still act as them. Valid in local/both auth modes.
        bearer = create_access_token({"sub": current_user["user_id"]})

    key = _key(current_user, body.session_id)
    # Fire-and-forget: the turn streams its output into the SSE queue.
    task = asyncio.create_task(
        run_turn(
            key, body.text, bearer_token=bearer,
            screen=body.screen, catalog=body.catalog, context=body.context,
            tours=body.tours, entities=body.entities, mode=body.mode, forms=body.forms,
            screen_view=body.screen_view, form_view=body.form_view,
        )
    )
    _turn_tasks.add(task)
    task.add_done_callback(_turn_tasks.discard)
    return {"status": "accepted"}


@router.post("/approve")
async def approve(body: DecisionIn, current_user: dict = Depends(get_current_user)):
    """Approve a pending write/regulated action. The paused agent turn resumes
    and calls the route as this user. Ownership is enforced by the session key.
    Engine-agnostic: with the Redis store this request may land on a different
    worker/replica than the awaiting turn."""
    key = _key(current_user, body.session_id)
    if not await confirmations.resolve(body.action_token, owner_key=key, approved=True):
        raise HTTPException(status_code=404, detail="No pending action for this session/token")
    return {"status": "approved"}


@router.post("/cancel")
async def cancel(body: DecisionIn, current_user: dict = Depends(get_current_user)):
    """Cancel a pending write/regulated action. Nothing is executed."""
    key = _key(current_user, body.session_id)
    if not await confirmations.resolve(body.action_token, owner_key=key, approved=False):
        raise HTTPException(status_code=404, detail="No pending action for this session/token")
    return {"status": "cancelled"}

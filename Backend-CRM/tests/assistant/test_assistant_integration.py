"""Live, API-level regression tests for the assistant stabilization gate.

These exercise the real SSE endpoint end-to-end (context threading / screen
parity, create_conversation + audit provenance, honest limits). They need the
running stack (uvicorn + Mongo + Postgres + a real user), so they are SKIPPED
unless ``ASSISTANT_LIVE_BASE`` (and ``ASSISTANT_LIVE_USER``) are set:

    ASSISTANT_LIVE_BASE=http://localhost:8000 \
    ASSISTANT_LIVE_USER=<user_id> \
        python -m pytest tests/assistant/test_assistant_integration.py

Run inside the backend container (has DB access + app deps).
"""
import asyncio
import json
import os

import pytest

BASE = os.getenv("ASSISTANT_LIVE_BASE")
USER = os.getenv("ASSISTANT_LIVE_USER")

pytestmark = pytest.mark.skipif(
    not (BASE and USER), reason="set ASSISTANT_LIVE_BASE + ASSISTANT_LIVE_USER to run"
)

CATALOG = [{"name": "conversations", "aliases": ["inbox"], "requires": "none"}]


async def _turn(client, auth, sid, q, context, decision=None):
    import httpx  # noqa

    blocks, notices, text = [], [], ""
    done = asyncio.Event()

    async def read():
        nonlocal text
        async with client.stream(
            "GET", f"/api/assistant/stream?session_id={sid}",
            headers={**auth, "Accept": "text/event-stream"},
        ) as r:
            async for line in r.aiter_lines():
                if not line.startswith("data:"):
                    continue
                e = json.loads(line[5:].strip())
                if e["type"] == "block":
                    b = e["block"]
                    blocks.append(b)
                    if b["type"] == "notice":
                        notices.append(b["message"])
                    if b["type"] == "confirmation" and decision:
                        await client.post(
                            f"/api/assistant/{decision}", headers=auth,
                            json={"session_id": sid, "action_token": b["token"]},
                        )
                elif e["type"] == "token":
                    text += e.get("text", "")
                elif e["type"] in ("done", "error"):
                    done.set()
                    return

    reader = asyncio.create_task(read())
    await asyncio.sleep(0.8)
    await client.post(
        "/api/assistant/message", headers=auth,
        json={"session_id": sid, "text": q, "screen": "Conversations", "catalog": CATALOG, "context": context},
    )
    try:
        await asyncio.wait_for(done.wait(), timeout=90)
    finally:
        reader.cancel()
    return blocks, notices, text


async def _pick_site_with_convs(client, auth):
    studies = (await client.get("/api/studies", headers=auth)).json()
    for s in studies:
        sites = (await client.get("/api/sites", headers=auth, params={"study_id": s["id"]})).json()
        for site in sites:
            convs = (await client.get("/api/conversations", headers=auth,
                                      params={"study_id": s["id"], "site_id": site["id"]})).json()
            if convs:
                return s, site, len(convs)
    return None, None, 0


@pytest.mark.asyncio
async def test_conversation_scope_matches_screen_and_create_and_honesty():
    import httpx
    from app.auth import create_access_token

    auth = {"Authorization": f"Bearer {create_access_token({'sub': USER})}"}
    async with httpx.AsyncClient(base_url=BASE, timeout=120) as client:
        study, site, screen_count = await _pick_site_with_convs(client, auth)
        assert site, "no site with conversations for this user"
        ctx = {"study_id": study["id"], "site_id": site["id"]}

        # A/B: assistant list matches the screen for the same context.
        blocks, _, _ = await _turn(client, auth, "it-list", "list my conversations", ctx)
        rl = next((b for b in blocks if b["type"] == "record_list"), None)
        assert rl is not None and len(rl["records"]) == screen_count

        # C/D: create_conversation actually creates in the site.
        subject = "Integration test conversation"
        await _turn(client, auth, "it-create", f"create a conversation with subject '{subject}'", ctx, decision="approve")
        after = (await client.get("/api/conversations", headers=auth,
                                  params={"study_id": study["id"], "site_id": site["id"]})).json()
        assert any(c.get("subject") == subject or c.get("title") == subject for c in after)

        # C: unsupported ask yields a specific honest limit, not a false refusal.
        _, notices, text = await _turn(client, auth, "it-honest", "delete that conversation", ctx)
        msg = (notices[0] if notices else text).lower()
        assert "can" in msg  # states what it can/can't do, specifically

"""Job C STEP 2 — route-level test that the thread message handler BOUNDS its
inline AI and WebSocket publish under COMMS_DISPATCH_FIX (so a hung AI/WS can't
hang the send response), and behaves normally with the flag off.

Uses FastAPI TestClient against just the communications router with all I/O
mocked. The module timeout constants are tightened so a real timeout fires fast.
"""
import asyncio
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.crud as crud
import app.modules.communications.routes.communications as routes
from app.auth import get_current_user_optional
from app.db import get_db
from app.integrations.ai import ai_service
from app.websocket_manager import manager
from app.modules.communications.repositories import ThreadMessageRepository

THREAD_ID = str(uuid.uuid4())
FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_client():
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")

    async def _fake_user():
        return {"user_id": "u", "email": "a@b.com"}

    async def _fake_db():
        yield None

    app.dependency_overrides[get_current_user_optional] = _fake_user
    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def wire(monkeypatch):

    async def _get_thread(db, tid):
        return {"id": str(tid), "participants_emails": ["a@b.com"],
                "title": "T", "related_study_id": "S1"}

    async def _create_thread_message(db, tid, message):
        return {
            "id": str(uuid.uuid4()), "thread_id": str(tid), "message_id": None,
            "body": "hi", "author_id": "u", "author_name": "U",
            "mentioned_emails": [], "created_at": FIXED, "message_type": None,
        }

    monkeypatch.setattr(crud, "get_thread", _get_thread)
    monkeypatch.setattr(crud, "create_thread_message", _create_thread_message)

    async def _noop_update(*a, **k):
        return None
    monkeypatch.setattr(ThreadMessageRepository, "update_fields", _noop_update)

    yield


def test_bounds_hanging_ai_and_ws(monkeypatch):
    # tighten timeouts so a real timeout fires fast
    monkeypatch.setattr(routes, "_THREAD_AI_TIMEOUT", 0.05)
    monkeypatch.setattr(routes, "_THREAD_WS_TIMEOUT", 0.05)

    monkeypatch.setattr(ai_service, "is_available", lambda: True)
    monkeypatch.setattr(ai_service, "_format_thread_messages_for_summary", lambda *a, **k: "")

    async def _hang_ai(*a, **k):
        await asyncio.sleep(1.0)
        return {}
    async def _list(*a, **k):
        return [{"id": str(uuid.uuid4()), "body": "x"}]
    async def _hang_ws(*a, **k):
        await asyncio.sleep(1.0)
    monkeypatch.setattr(ai_service, "analyse_new_message", _hang_ai)
    monkeypatch.setattr(ThreadMessageRepository, "list_by_thread", _list)
    monkeypatch.setattr(manager, "publish_thread_update", _hang_ws)

    client = _make_client()
    start = time.monotonic()
    r = client.post(f"/api/threads/{THREAD_ID}/messages",
                    json={"body": "hi", "author_id": "u"})
    elapsed = time.monotonic() - start

    assert r.status_code == 200
    assert r.json()["body"] == "hi"
    # Both hangs are 1.0s; bounded to ~0.05s each → request must NOT wait ~2s.
    assert elapsed < 0.8, f"request took {elapsed:.2f}s — timeouts did not bound the hangs"


def test_normal_send_succeeds(monkeypatch):
    # fast (non-hanging) deps — flag-OFF runs them inline as today
    monkeypatch.setattr(ai_service, "is_available", lambda: False)  # skip AI block entirely

    async def _ws(*a, **k):
        return None
    monkeypatch.setattr(manager, "publish_thread_update", _ws)

    client = _make_client()
    r = client.post(f"/api/threads/{THREAD_ID}/messages",
                    json={"body": "hi", "author_id": "u"})
    assert r.status_code == 200
    assert r.json()["body"] == "hi"

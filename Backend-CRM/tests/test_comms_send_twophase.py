"""Job C STEP 2 (Option B) — two-phase send marker in send_message_task.

Runs the REAL task (thread path) against the local standalone Mongo test DB,
with SMTP and the Postgres session mocked. Each phase (setup / task / assert)
uses its own event loop + motor client against the same Mongo DB, so there is no
cross-loop motor sharing (the task's run_async creates its own loop).

`def test_` (sync) — the task body calls run_async / run_until_complete, which
cannot run inside an already-running loop.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import app.workers.tasks as tasks_mod
import app.modules.communications.repositories.mongo as repo_mongo
from app.integrations.smtp_service import smtp_service

URI = "mongodb://127.0.0.1:27017"
TEST_DB = "crm_jobb_test"
COLLS = ["threads", "thread_messages"]
FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)

_clients = {}


async def _get_db():
    loop = asyncio.get_event_loop()
    key = id(loop)
    if key not in _clients:
        _clients[key] = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
    return _clients[key][TEST_DB]


class _FakeSession:
    async def __aenter__(self):
        return None
    async def __aexit__(self, *a):
        return False


def _setup(status="queued", extra=None):
    tid, mid = str(uuid.uuid4()), str(uuid.uuid4())

    async def _ins():
        db = await _get_db()
        for c in COLLS:
            await db[c].delete_many({})
        await db["threads"].insert_one({
            "id": tid, "title": "T", "related_study_id": "S1", "site_id": "SITE1",
            "participants_emails": ["a@b.com"], "visibility_scope": "site",
            "created_at": FIXED, "updated_at": FIXED,
        })
        doc = {
            "id": mid, "thread_id": tid, "status": status, "body": "hello",
            "mentioned_emails": ["a@b.com"], "created_at": FIXED,
        }
        if extra:
            doc.update(extra)
        await db["thread_messages"].insert_one(doc)
    asyncio.run(_ins())
    return mid


def _read(mid):
    async def _r():
        db = await _get_db()
        return await db["thread_messages"].find_one({"id": mid})
    return asyncio.run(_r())


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    monkeypatch.setattr(repo_mongo, "get_mongo_db", _get_db)
    monkeypatch.setattr(tasks_mod, "AsyncSessionLocal", lambda: _FakeSession())
    # run_async never disposes the engine now, so the real Postgres engine is
    # never touched here.
    yield
    for c in list(_clients.values()):
        c.close()
    _clients.clear()


def _run_task(mid):
    asyncio.set_event_loop(None)  # force run_async to build a fresh loop
    tasks_mod.send_message_task(mid, source_type="thread")


def test_success_marks_sent(monkeypatch):
    calls = []
    monkeypatch.setattr(smtp_service, "send_email",
                        lambda **k: calls.append(k) or {"success": True, "message_id": "<x>"})
    mid = _setup()
    _run_task(mid)
    d = _read(mid)
    assert d["status"] == "sent"
    assert "send_attempted_at" in d   # claimed before send
    assert len(calls) == 1


def test_send_failure_marks_needs_review_not_resent(monkeypatch):
    calls = []
    monkeypatch.setattr(smtp_service, "send_email",
                        lambda **k: calls.append(k) or {"success": False, "error": "boom"})
    mid = _setup()
    _run_task(mid)
    d = _read(mid)
    assert d["status"] == "needs_review"   # attempted, unknown outcome
    assert len(calls) == 1                 # tried exactly once, never re-sent


def test_prior_attempt_escalates_without_sending(monkeypatch):
    calls = []
    monkeypatch.setattr(smtp_service, "send_email",
                        lambda **k: calls.append(k) or {"success": True})
    # A message left mid-flight (status sending + send_attempted_at) from a crash.
    mid = _setup(status="sending", extra={"send_attempted_at": FIXED})
    _run_task(mid)
    d = _read(mid)
    assert d["status"] == "needs_review"   # never auto-resent
    assert len(calls) == 0                 # SMTP not called at all


def test_double_run_does_not_double_send(monkeypatch):
    calls = []
    monkeypatch.setattr(smtp_service, "send_email",
                        lambda **k: calls.append(k) or {"success": True, "message_id": "<x>"})
    mid = _setup()
    _run_task(mid)   # claims + sends → SENT
    _run_task(mid)   # entry sees SENT → skips
    d = _read(mid)
    assert d["status"] == "sent"
    assert len(calls) == 1   # sent exactly once

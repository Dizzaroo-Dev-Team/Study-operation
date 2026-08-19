"""Job C STEP 3 — stuck-QUEUED sweeper.

Runs against the local Mongo test DB. The sweeper is a plain async function (no
run_async), so async tests on the test loop work directly. `send_message_task`
is mocked so we observe re-enqueues without a broker.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import app.modules.communications.services.queued_sweeper as sweeper

URI = "mongodb://127.0.0.1:27017"
TEST_DB = "crm_jobb_test"
COLLS = ["messages", "thread_messages"]


@pytest.fixture
async def env(monkeypatch):
    client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
    db = client[TEST_DB]
    for c in COLLS:
        await db[c].delete_many({})

    async def _get():
        return db
    monkeypatch.setattr(sweeper, "get_mongo_db", _get)

    enqueued = []
    class _FakeTask:
        def delay(self, *a, **k):
            enqueued.append((a, k))
    monkeypatch.setattr("app.workers.tasks.send_message_task", _FakeTask())

    yield db, enqueued
    for c in COLLS:
        await db[c].delete_many({})
    client.close()


def _old():
    return datetime.now(timezone.utc) - timedelta(minutes=60)


def _recent():
    return datetime.now(timezone.utc)


async def _insert_msg(db, coll, **over):
    doc = {"id": str(uuid.uuid4()), "status": "queued", "created_at": _old()}
    doc.update(over)
    await db[coll].insert_one(doc)
    return doc["id"]


async def test_sweeper_reenqueues_stuck_never_attempted(env, monkeypatch):
    db, enqueued = env
    mid = await _insert_msg(db, "messages")           # queued, old, no attempt
    tid = await _insert_msg(db, "thread_messages")
    report = await sweeper.sweep_stuck_queued_messages(threshold_minutes=15, dry_run=False)
    ids = {c["id"] for c in report["reenqueued"]}
    assert mid in ids and tid in ids
    assert len(enqueued) == 2


async def test_sweeper_excludes_attempted(env, monkeypatch):
    db, enqueued = env
    # Stuck + old but a send was already attempted → must NOT be re-enqueued.
    await _insert_msg(db, "messages", send_attempted_at=_old())
    # Also a 'sending' leftover (attempted) — excluded by status != queued.
    await _insert_msg(db, "messages", status="sending", send_attempted_at=_old())
    report = await sweeper.sweep_stuck_queued_messages(threshold_minutes=15, dry_run=False)
    assert report["reenqueued"] == []
    assert enqueued == []


async def test_sweeper_excludes_recent(env, monkeypatch):
    db, enqueued = env
    await _insert_msg(db, "messages", created_at=_recent())  # too new
    report = await sweeper.sweep_stuck_queued_messages(threshold_minutes=15, dry_run=False)
    assert report["reenqueued"] == []
    assert enqueued == []


async def test_sweeper_dry_run_lists_but_does_not_enqueue(env, monkeypatch):
    db, enqueued = env
    mid = await _insert_msg(db, "messages")
    report = await sweeper.sweep_stuck_queued_messages(threshold_minutes=15, dry_run=True)
    assert any(c["id"] == mid for c in report["candidates"])
    assert any(c["id"] == mid for c in report["would_reenqueue"])
    assert report["reenqueued"] == []
    assert enqueued == []



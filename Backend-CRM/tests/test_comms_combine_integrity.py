"""Job B STEP 3 — combine-threads integrity (compensating pattern).

Runs for REAL against the local standalone MongoDB (127.0.0.1:27017) using a
test database whose name contains "test". This is the standalone topology that
has no multi-document transactions — exactly what the compensating pattern must
work on.

`asyncio_mode = auto` (pytest.ini) runs the async tests/fixtures without markers.
"""
import uuid
from datetime import datetime, timezone
from uuid import UUID

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import app.crud as crud
import app.modules.communications.repositories.mongo as repo_mongo
from app.modules.communications.repositories import (
    ThreadRepository,
    ThreadMessageRepository,
    ThreadAttachmentRepository,
)

TEST_DB = "crm_jobb_test"
COLLECTIONS = [
    "threads", "thread_messages", "thread_participants",
    "thread_from_conversations", "attachments", "thread_attachments",
]
FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
async def mongo(monkeypatch):
    client = AsyncIOMotorClient("mongodb://127.0.0.1:27017", serverSelectionTimeoutMS=3000)
    db = client[TEST_DB]
    for c in COLLECTIONS:
        await db[c].delete_many({})
    async def _get():
        return db
    monkeypatch.setattr(repo_mongo, "get_mongo_db", _get)
    yield db
    for c in COLLECTIONS:
        await db[c].delete_many({})
    client.close()


async def _insert_thread(db, tid, **over):
    doc = {
        "id": tid, "title": "T", "description": None, "thread_type": "general",
        "related_study_id": "S1", "site_id": "SITE1", "priority": "medium",
        "status": "open", "created_by": "owner", "participants_emails": [],
        "visibility_scope": "private", "created_at": FIXED, "updated_at": FIXED,
    }
    doc.update(over)
    await db["threads"].insert_one(doc)
    return tid


async def _insert_messages(db, thread_id, n):
    await db["thread_messages"].insert_many([
        {"id": str(uuid.uuid4()), "thread_id": thread_id, "body": f"m{i}",
         "author_id": "x", "created_at": FIXED}
        for i in range(n)
    ])


# --------------------------------------------------------------------------- #
# Flag ON — full integrity
# --------------------------------------------------------------------------- #

async def test_combine_moves_all_merges_emails_and_cleans(mongo, monkeypatch):
    db = mongo
    src, tgt = str(uuid.uuid4()), str(uuid.uuid4())
    await _insert_thread(db, tgt, created_by="owner", participants_emails=["owner@x.com"], title="Target")
    await _insert_thread(db, src, created_by="alice", participants_emails=["alice@x.com"], title="Source")
    N = 1100  # > legacy 1000 cap
    await _insert_messages(db, src, N)
    await db["thread_participants"].insert_one(
        {"id": str(uuid.uuid4()), "thread_id": src, "participant_id": "alice",
         "participant_email": "alice@x.com", "role": "participant"})
    await db["thread_from_conversations"].insert_one(
        {"id": str(uuid.uuid4()), "thread_id": src, "conversation_id": str(uuid.uuid4()),
         "source_message_ids": []})
    aid = str(uuid.uuid4())
    await db["attachments"].insert_one(
        {"id": aid, "file_path": "uploads/x.pdf", "content_type": "application/pdf", "size": 1})
    await db["thread_attachments"].insert_one(
        {"id": str(uuid.uuid4()), "thread_id": src, "attachment_id": aid})

    result = await crud.combine_threads(None, UUID(src), UUID(tgt), UUID(tgt))
    assert result is not None

    # ALL messages moved — none orphaned (THR-COMBINE-1000 fixed)
    assert await ThreadMessageRepository.count_by_thread(UUID(tgt)) == N
    assert await ThreadMessageRepository.count_by_thread(UUID(src)) == 0
    # participants_emails merged (THR-COMBINE-EMAILS) — merged-in user keeps REST access
    t = await ThreadRepository.get_by_id(UUID(tgt))
    emails = t.get("participants_emails") or []
    assert "alice@x.com" in emails and "owner@x.com" in emails
    # source participant + link rows gone (THR-COMBINE-ORPHAN)
    assert await db["thread_participants"].count_documents({"thread_id": src}) == 0
    assert await db["thread_from_conversations"].count_documents({"thread_id": src}) == 0
    # attachment re-pointed
    ta = await db["thread_attachments"].find_one({"attachment_id": aid})
    assert ta["thread_id"] == tgt
    # source thread deleted
    assert await ThreadRepository.get_by_id(UUID(src)) is None


# --------------------------------------------------------------------------- #
# Flag ON — mid-run failure → full rollback, source not deleted
# --------------------------------------------------------------------------- #

async def test_combine_midrun_failure_rolls_back(mongo, monkeypatch):
    db = mongo
    src, tgt = str(uuid.uuid4()), str(uuid.uuid4())
    await _insert_thread(db, tgt, participants_emails=["owner@x.com"], title="Target")
    await _insert_thread(db, src, participants_emails=["alice@x.com"], title="Source")
    await _insert_messages(db, src, 5)

    # Blow up Phase A (attachment move, step 5) — after messages already moved.
    async def boom(*a, **k):
        raise RuntimeError("disk on fire")
    monkeypatch.setattr(ThreadAttachmentRepository, "move_all_to_thread", boom)

    with pytest.raises(RuntimeError):
        await crud.combine_threads(None, UUID(src), UUID(tgt), UUID(tgt))

    # messages rolled back to source — none stuck on target
    assert await ThreadMessageRepository.count_by_thread(UUID(src)) == 5
    assert await ThreadMessageRepository.count_by_thread(UUID(tgt)) == 0
    # target emails restored (alice NOT merged)
    t = await ThreadRepository.get_by_id(UUID(tgt))
    assert "alice@x.com" not in (t.get("participants_emails") or [])
    # source NOT deleted, marked failed (and thus hidden)
    s = await ThreadRepository.get_by_id(UUID(src))
    assert s is not None
    assert s.get("merge_state") == "failed"


# --------------------------------------------------------------------------- #
# Flag ON — in-progress / failed source hidden from list, read, access
# --------------------------------------------------------------------------- #

async def test_in_progress_source_hidden(mongo, monkeypatch):
    db = mongo
    sid = str(uuid.uuid4())
    await _insert_thread(
        db, sid, created_by="owner", participants_emails=["owner@x.com"],
        visibility_scope="site", related_study_id="S1", site_id="SITE1",
        merge_state="in_progress", merge_target_id=str(uuid.uuid4()))

    # read paths return nothing
    assert await crud.get_thread(None, UUID(sid)) is None
    assert await crud.get_thread_with_messages(None, UUID(sid)) is None
    # access denied even for the creator
    thread_doc = {"id": UUID(sid), "created_by": "owner", "merge_state": "in_progress", "participants": []}
    assert await crud.check_user_can_access_thread(None, "owner", thread_doc) is False
    # list excludes it
    listed = await crud.list_threads(None, study_id="S1", site_id="SITE1", user_email="owner@x.com")
    assert all(t.get("id") != UUID(sid) for t in listed)




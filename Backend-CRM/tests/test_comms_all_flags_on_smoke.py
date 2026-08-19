"""STEP 4 — all-flags-ON smoke for the Communications fixes (Jobs A–D).

Exercises the core (now-permanent) Communications behavior — the
happy-paths + the key cross-flag interactions, against the local standalone
Mongo test DB. This is the "does it still basically work with everything on"
check — not edge cases.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from uuid import UUID

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

import app.crud as crud
import app.integrations.iam.membership as membership
import app.modules.communications.repositories.mongo as repo_mongo
import app.modules.communications.services.queued_sweeper as sweeper_mod
import app.modules.communications.services.attachment_cleanup as cleanup_mod
from app.config import settings
from app.modules.communications.repositories import ThreadRepository, ThreadMessageRepository
from app.modules.communications.services.queued_sweeper import sweep_stuck_queued_messages
from app.modules.communications.services.attachment_cleanup import reconcile_orphan_attachment_files

URI = "mongodb://127.0.0.1:27017"
TEST_DB = "crm_jobb_test"
FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)
COLLS = ["threads", "thread_messages", "thread_participants",
         "thread_from_conversations", "attachments", "thread_attachments", "messages"]


@pytest.fixture
def all_on(monkeypatch):
    # The former COMMS_* flags are gone — the hardened behavior is permanent.
    # Only the study-membership lookup needs stubbing for these unit checks.
    async def _fake_member(user_id, study):
        return str(user_id) == "member"
    monkeypatch.setattr(membership, "user_can_access_study", _fake_member)
    return monkeypatch


@pytest.fixture
async def db(monkeypatch):
    client = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
    d = client[TEST_DB]
    for c in COLLS:
        await d[c].delete_many({})
    async def _get():
        return d
    monkeypatch.setattr(repo_mongo, "get_mongo_db", _get)
    monkeypatch.setattr(sweeper_mod, "get_mongo_db", _get)
    yield d
    for c in COLLS:
        await d[c].delete_many({})
    client.close()


def _public_conv(**over):
    base = {"id": str(uuid.uuid4()), "conversation_type": "thread", "is_pinned": "false",
            "access_level": "PUBLIC", "is_confidential": "false", "created_by": "someone",
            "study_id": "S", "site_id": "SITE", "participant_emails": [], "privileged_users": []}
    base.update(over)
    return base


# 1. Access control: membership gate (member allowed, non-member denied)
async def test_access_member_allowed_nonmember_denied(all_on, db):
    conv = _public_conv()
    assert await crud.check_user_can_access_conversation_by_role(None, "member", conv, access_set=set()) is True
    assert await crud.check_user_can_access_conversation_by_role(None, "outsider", conv, access_set=set()) is False


# 1b. Interaction: privacy overrides the membership shortcut
async def test_privacy_overrides_membership(all_on, db):
    conv = _public_conv(is_confidential="true")
    # confidential → not public → even a study member who isn't a participant is denied
    assert await crud.check_user_can_access_conversation_by_role(None, "member", conv, access_set=set()) is False


# 2. Thread happy-path: create → message → read back → combine (integrity preserved)
async def test_thread_create_message_read_combine(all_on, db):
    src, tgt = str(uuid.uuid4()), str(uuid.uuid4())
    for tid, emails, title in [(tgt, ["owner@x.com"], "Target"), (src, ["alice@x.com"], "Source")]:
        await db["threads"].insert_one({
            "id": tid, "title": title, "related_study_id": "S", "site_id": "SITE",
            "participants_emails": emails, "visibility_scope": "site",
            "created_by": "member", "created_at": FIXED, "updated_at": FIXED})
    await db["thread_messages"].insert_many(
        [{"id": str(uuid.uuid4()), "thread_id": src, "body": f"m{i}", "created_at": FIXED} for i in range(3)])

    # read back
    t = await crud.get_thread_with_messages(None, UUID(src))
    assert t is not None and len(t["messages"]) == 3

    # combine (combine_safe ON) — all messages move, emails merge, source gone
    res = await crud.combine_threads(None, UUID(src), UUID(tgt), UUID(tgt))
    assert res is not None
    assert await ThreadMessageRepository.count_by_thread(UUID(tgt)) == 3
    assert await ThreadRepository.get_by_id(UUID(src)) is None
    tt = await ThreadRepository.get_by_id(UUID(tgt))
    assert "alice@x.com" in (tt.get("participants_emails") or [])


# 3. Sweeper + attachment cleanup execute under all-flags-on
async def test_sweeper_and_cleanup_execute(all_on, db, monkeypatch, tmp_path):
    enqueued = []
    class _FT:
        def delay(self, *a, **k):
            enqueued.append((a, k))
    monkeypatch.setattr("app.workers.tasks.send_message_task", _FT())
    await db["messages"].insert_one({
        "id": str(uuid.uuid4()), "status": "queued",
        "created_at": datetime.now(timezone.utc) - timedelta(minutes=60)})
    rep = await sweep_stuck_queued_messages(threshold_minutes=15, dry_run=False)
    assert len(rep["reenqueued"]) == 1

    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    async def _get():
        return db
    monkeypatch.setattr(cleanup_mod, "get_mongo_db", _get)
    (tmp_path / "orphan.pdf").write_text("x")
    crep = await reconcile_orphan_attachment_files(dry_run=False)
    assert "orphan.pdf" in crep["deleted"]


# 4. Two-phase send happy-path (dispatch_fix ON) — sync, own loop/client
_clients = {}


async def _get_perloop():
    loop = asyncio.get_event_loop()
    k = id(loop)
    if k not in _clients:
        _clients[k] = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
    return _clients[k][TEST_DB]


def test_two_phase_send_happy(all_on, monkeypatch):
    import app.workers.tasks as tasks_mod
    from app.integrations.smtp_service import smtp_service

    monkeypatch.setattr(repo_mongo, "get_mongo_db", _get_perloop)
    class _FS:
        async def __aenter__(self):
            return None
        async def __aexit__(self, *a):
            return False
    monkeypatch.setattr(tasks_mod, "AsyncSessionLocal", lambda: _FS())
    calls = []
    monkeypatch.setattr(smtp_service, "send_email",
                        lambda **k: calls.append(k) or {"success": True, "message_id": "<x>"})

    tid, mid = str(uuid.uuid4()), str(uuid.uuid4())
    async def _ins():
        d = await _get_perloop()
        for c in ["threads", "thread_messages"]:
            await d[c].delete_many({})
        await d["threads"].insert_one({
            "id": tid, "related_study_id": "S", "site_id": "SITE",
            "participants_emails": ["a@b.com"], "visibility_scope": "site",
            "created_at": FIXED, "updated_at": FIXED})
        await d["thread_messages"].insert_one({
            "id": mid, "thread_id": tid, "status": "queued", "body": "hi",
            "mentioned_emails": ["a@b.com"], "created_at": FIXED})
    asyncio.run(_ins())

    asyncio.set_event_loop(None)
    tasks_mod.send_message_task(mid, source_type="thread")

    async def _read():
        d = await _get_perloop()
        return await d["thread_messages"].find_one({"id": mid})
    doc = asyncio.run(_read())

    assert doc["status"] == "sent"
    assert len(calls) == 1
    for c in list(_clients.values()):
        c.close()
    _clients.clear()

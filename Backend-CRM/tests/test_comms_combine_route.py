"""PART 1 — route-level combine test (real POST /threads/combine, COMMS_COMBINE_SAFE ON).

Exercises the full route: guard + crud.combine_threads -> _combine_threads_safe +
audit, against the local standalone Mongo test DB. Each phase uses its own loop +
motor client against the same DB (the route runs on TestClient's loop).
"""
import asyncio
import uuid
from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.crud as crud
import app.modules.communications.routes.communications as routes
import app.modules.communications.repositories.mongo as repo_mongo
from app.auth import get_current_user_optional
from app.db import get_db
from app.modules.communications.repositories import ThreadRepository, ThreadMessageRepository

URI = "mongodb://127.0.0.1:27017"
TEST_DB = "crm_jobb_test"
FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)
COLLS = ["threads", "thread_messages", "thread_participants",
         "thread_from_conversations", "thread_attachments"]
_clients = {}


async def _db():
    loop = asyncio.get_event_loop()
    k = id(loop)
    if k not in _clients:
        _clients[k] = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
    return _clients[k][TEST_DB]


from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


def _client():
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")

    async def _user():
        return {"user_id": "u", "email": "a@b.com", "name": "U"}
    async def _gdb():
        yield None
    app.dependency_overrides[get_current_user_optional] = _user
    app.dependency_overrides[get_db] = _gdb
    return TestClient(app)


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    monkeypatch.setattr(repo_mongo, "get_mongo_db", _db)
    # Audit is always-on now; stub it so the route never touches Postgres here.
    async def _noop_audit(*a, **k):
        return None
    monkeypatch.setattr(crud, "create_audit_log", _noop_audit)
    yield
    for c in list(_clients.values()):
        c.close()
    _clients.clear()


def _seed():
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())

    async def _ins():
        d = await _db()
        for c in COLLS:
            await d[c].delete_many({})
        for tid, emails, title in [(t1, ["owner@x.com"], "Target"), (t2, ["alice@x.com"], "Source")]:
            await d["threads"].insert_one({
                "id": tid, "title": title, "related_study_id": "S", "site_id": "SITE",
                "participants_emails": emails, "visibility_scope": "site",
                "created_by": "u",  # caller is creator → passes the write-guard access check
                "created_at": FIXED, "updated_at": FIXED, "priority": "medium",
            })
        await d["thread_messages"].insert_many(
            [{"id": str(uuid.uuid4()), "thread_id": t2, "body": f"m{i}", "created_at": FIXED} for i in range(3)])
    asyncio.run(_ins())
    return t1, t2


def test_combine_route_moves_messages_and_deletes_source():
    t1, t2 = _seed()
    r = _client().post("/api/threads/combine",
                       json={"thread1_id": t1, "thread2_id": t2, "target_thread_id": t1})
    assert r.status_code == 200, r.text

    async def _check():
        moved = await ThreadMessageRepository.count_by_thread(UUID(t1))
        left = await ThreadMessageRepository.count_by_thread(UUID(t2))
        src = await ThreadRepository.get_by_id(UUID(t2))
        tgt = await ThreadRepository.get_by_id(UUID(t1))
        return moved, left, src, tgt
    moved, left, src, tgt = asyncio.run(_check())
    assert moved == 3 and left == 0
    assert src is None
    assert "alice@x.com" in (tgt.get("participants_emails") or [])

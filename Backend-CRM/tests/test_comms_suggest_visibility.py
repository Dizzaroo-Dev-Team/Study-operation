"""Regression: suggest-combinations must see the caller's PRIVATE threads.

Threads default to visibility_scope='private'. The suggest endpoint used to call
ThreadRepository.list() without user_email, which silently restricts the pool to
visibility_scope='site' — so private threads were invisible and the endpoint
returned [] ("No similar threads found") even with obvious duplicates.

This seeds two private, same-title threads the caller participates in and asserts
the endpoint now returns a deterministic exact-title suggestion (no AI needed).
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from motor.motor_asyncio import AsyncIOMotorClient

import app.modules.communications.routes.communications as routes
import app.modules.communications.repositories.mongo as repo_mongo
from app.auth import get_current_user_optional
from app.db import get_db

URI = "mongodb://127.0.0.1:27017"
TEST_DB = "crm_jobb_test"
FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)
COLLS = ["threads", "thread_messages", "thread_participants"]
STUDY, SITE, EMAIL = "S-SUGG", "SITE-SUGG", "caller@x.com"
_clients = {}


async def _db():
    loop = asyncio.get_event_loop()
    k = id(loop)
    if k not in _clients:
        _clients[k] = AsyncIOMotorClient(URI, serverSelectionTimeoutMS=3000)
    return _clients[k][TEST_DB]


def _client():
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")

    async def _user():
        return {"user_id": "u", "email": EMAIL, "name": "U"}

    async def _gdb():
        yield None

    app.dependency_overrides[get_current_user_optional] = _user
    app.dependency_overrides[get_db] = _gdb
    return TestClient(app)


@pytest.fixture(autouse=True)
def wire(monkeypatch):
    monkeypatch.setattr(repo_mongo, "get_mongo_db", _db)
    yield
    for c in list(_clients.values()):
        c.close()
    _clients.clear()


def _seed_private_same_title():
    async def _ins():
        d = await _db()
        for c in COLLS:
            await d[c].delete_many({})
        for emails in (["caller@x.com"], ["caller@x.com", "other@x.com"]):
            await d["threads"].insert_one({
                "id": str(uuid.uuid4()),
                "title": "Patient 12 SAE follow-up",   # identical -> exact match
                "related_study_id": STUDY,
                "site_id": SITE,
                "participants_emails": emails,
                "visibility_scope": "private",          # the realistic default
                "created_by": "u",
                "created_at": FIXED,
                "updated_at": FIXED,
                "priority": "medium",
            })

    asyncio.run(_ins())


def test_suggest_sees_private_threads_user_participates_in():
    _seed_private_same_title()
    r = _client().get(
        "/api/threads/suggest-combinations",
        params={"study_id": STUDY, "site_id": SITE, "limit": 10},
    )
    assert r.status_code == 200, r.text
    data = r.json()
    # Before the fix this was [] because private threads were filtered out.
    assert len(data) >= 1, f"expected a same-title suggestion, got: {data}"
    assert data[0]["should_combine"] is True
    assert data[0]["similarity_score"] >= 80

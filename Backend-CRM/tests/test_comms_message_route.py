"""Regression test for the create_message route asyncio-shadowing bug.

Exercises the REAL POST /conversations/{id}/messages route via TestClient (not a
mocked dispatch) with COMMS_DISPATCH_FIX ON, forcing the audit `asyncio.wait_for`
+ `except asyncio.TimeoutError` path to run — which previously raised
`UnboundLocalError: cannot access local variable 'asyncio'`.
"""
import asyncio
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.crud as crud
import app.modules.communications.routes.communications as routes
from app.auth import get_current_user_optional
from app.db import get_db
from app.websocket_manager import manager

FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _wire(monkeypatch, conv_id):
    conv = {"id": conv_id, "conversation_type": "thread", "is_pinned": "false",
            "access_level": "PUBLIC", "study_id": "S", "site_id": "SITE",
            "participant_emails": [], "privileged_users": [], "created_by": "x"}

    async def _get_conv(db, cid):
        return conv

    async def _create_msg(db, cid, msg, direction, author_id=None, author_name=None):
        return {"id": str(uuid.uuid4()), "conversation_id": str(cid), "direction": "outbound",
                "channel": "email", "body": "hi", "status": "queued",
                "author_id": author_id, "author_name": author_name,
                "mentioned_emails": [], "created_at": FIXED, "metadata": {}}

    # Force the audit through wait_for AND the `except asyncio.TimeoutError` branch
    # — both reference the (previously shadowed) `asyncio` name.
    async def _audit_timeout(*a, **k):
        raise asyncio.TimeoutError()

    async def _pub(*a, **k):
        return None

    # Isolate from the access/membership gate (covered by its own suite) so this
    # test reaches the audit/WS/dispatch path where the asyncio bug lived —
    # regardless of whether COMMS_ENFORCE_MEMBERSHIP is set in the environment.
    async def _can_access(*a, **k):
        return True

    class _FakeTask:
        def delay(self, *a, **k):
            pass

    monkeypatch.setattr(crud, "get_conversation", _get_conv)
    monkeypatch.setattr(crud, "create_message", _create_msg)
    monkeypatch.setattr(crud, "check_user_can_access_conversation_by_role", _can_access)
    monkeypatch.setattr(crud, "create_audit_log", _audit_timeout)
    monkeypatch.setattr(manager, "publish_event", _pub)
    monkeypatch.setattr("app.workers.tasks.send_message_task", _FakeTask())
    monkeypatch.setattr("app.workers.tasks.process_message_ai_task", _FakeTask())


def _client():
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")

    async def _user():
        return {"user_id": "u", "email": "a@b.com", "name": "U"}
    async def _db():
        yield None
    app.dependency_overrides[get_current_user_optional] = _user
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_create_message_no_unbound_error_and_persists(monkeypatch):
    conv_id = str(uuid.uuid4())
    _wire(monkeypatch, conv_id)
    r = _client().post(f"/api/conversations/{conv_id}/messages",
                       json={"channel": "email", "body": "hi"})
    assert r.status_code == 200, r.text   # was 500 UnboundLocalError before the fix
    assert r.json()["body"] == "hi"



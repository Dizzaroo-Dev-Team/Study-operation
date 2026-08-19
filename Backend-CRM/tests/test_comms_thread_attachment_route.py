"""Regression tests for the thread-attachment routes' dict-vs-object bug.

`crud.create_thread_attachment` / `crud.list_thread_attachments` are Mongo-backed
and return **dicts**, but the routes used to reload them via the Postgres
`ThreadAttachment` ORM (`db.refresh(x)` + `x.id`), which raised
`'dict' object has no attribute 'id'` → HTTP 500. These tests exercise the REAL
routes (write-guards ON) and assert:

  * upload  POST /threads/{id}/attachments  -> 200 (was 500), attachment hydrated
  * list    GET  /threads/{id}/attachments  -> 200 (was 500), attachment hydrated
  * a non-member is denied (403) on both

This closes the same coverage gap that previously hid the download-route bug.
"""
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.crud as crud
import app.modules.communications.routes.communications as routes
from app.auth import get_current_user_optional
from app.db import get_db

FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _attachment_dict(conversation_id, attachment_id):
    return {
        "id": attachment_id,
        "message_id": None,
        "conversation_id": conversation_id,
        "file_path": "uploads/x.txt",
        "content_type": "text/plain",
        "size": 5,
        "checksum": None,
        "uploaded_at": FIXED,
    }


def _thread_attachment_dict(thread_id, attachment_id):
    return {
        "id": uuid.uuid4(),
        "thread_id": thread_id,
        "thread_message_id": None,
        "attachment_id": attachment_id,
        "created_at": FIXED,
    }


def _client(monkeypatch, *, can_access: bool):
    """Wire a TestClient with the Mongo crud returning dicts. The write-guard is
    always on now; `can_access` drives the mocked thread-access check."""
    thread_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    attachment_id = uuid.uuid4()
    thread = {"id": str(thread_id), "conversation_id": str(conv_id),
              "related_study_id": "S", "visibility_scope": "site"}

    async def _get_thread(db, tid):
        return thread

    async def _can(*a, **k):
        return can_access

    async def _create_attachment(db, **kwargs):
        return _attachment_dict(conv_id, attachment_id)

    async def _create_thread_attachment(db, **kwargs):
        return _thread_attachment_dict(thread_id, attachment_id)

    async def _list_thread_attachments(db, tid):
        return [_thread_attachment_dict(thread_id, attachment_id)]

    async def _get_attachment(db, aid):
        return _attachment_dict(conv_id, attachment_id)

    async def _audit(*a, **k):
        return None

    monkeypatch.setattr(crud, "get_thread", _get_thread)
    monkeypatch.setattr(crud, "check_user_can_access_thread", _can)
    monkeypatch.setattr(crud, "create_attachment", _create_attachment)
    monkeypatch.setattr(crud, "create_thread_attachment", _create_thread_attachment)
    monkeypatch.setattr(crud, "list_thread_attachments", _list_thread_attachments)
    monkeypatch.setattr(crud, "get_attachment", _get_attachment)
    monkeypatch.setattr(routes, "best_effort_audit", _audit)
    # Skip real file I/O — the bug under test is in response building, not disk.
    monkeypatch.setattr(routes, "validate_upload_metadata", lambda f: None)
    monkeypatch.setattr(routes, "stream_to_disk_safely", lambda f, p: 5)
    monkeypatch.setattr(routes, "verify_magic_bytes", lambda p, ct, fn: None)

    app = FastAPI()
    app.include_router(routes.router, prefix="/api")

    async def _user():
        return {"user_id": "u", "email": "a@b.com", "name": "U"}

    async def _db():
        yield None

    app.dependency_overrides[get_current_user_optional] = _user
    app.dependency_overrides[get_db] = _db
    return TestClient(app), thread_id


def test_upload_thread_attachment_member_success(monkeypatch):
    client, thread_id = _client(monkeypatch, can_access=True)
    r = client.post(
        f"/api/threads/{thread_id}/attachments",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 200, r.text  # was 500: 'dict' object has no attribute 'id'
    body = r.json()
    assert body["attachment"] is not None
    assert body["attachment"]["file_name"] == "note.txt"


def test_list_thread_attachments_member_success(monkeypatch):
    client, thread_id = _client(monkeypatch, can_access=True)
    r = client.get(f"/api/threads/{thread_id}/attachments")
    assert r.status_code == 200, r.text  # was 500: 'dict' object has no attribute 'id'
    body = r.json()
    assert isinstance(body, list) and len(body) == 1
    assert body[0]["attachment"]["file_name"] == "x.txt"


def test_upload_thread_attachment_non_member_denied(monkeypatch):
    client, thread_id = _client(monkeypatch, can_access=False)
    r = client.post(
        f"/api/threads/{thread_id}/attachments",
        files={"file": ("note.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 403, r.text


def test_list_thread_attachments_non_member_denied(monkeypatch):
    client, thread_id = _client(monkeypatch, can_access=False)
    r = client.get(f"/api/threads/{thread_id}/attachments")
    assert r.status_code == 403, r.text

"""Job D STEP 4 — observability + audit.

Covers: print→logger sweep (no print remains; logger used on failure), PII
redaction (no raw email in conversation-create logs), and the gated best-effort
audit mechanism (writes via the existing crud.create_audit_log; flag-OFF no-op;
failure logged-not-raised; route-level audit fires for thread message).
"""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.crud as crud
import app.modules.communications.audit_helpers as ah
import app.modules.communications.routes.communications as routes
from app.auth import get_current_user_optional
from app.db import get_db
from app.integrations.ai import ai_service
from app.websocket_manager import manager
from app.modules.communications.repositories import ThreadMessageRepository
from app.utils.log_redact import mask_email, mask_emails, body_preview

BASE = Path(__file__).resolve().parent.parent / "app"


# --------------------------------------------------------------------------- #
# print → logger sweep
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("rel", [
    "modules/communications/routes/communications.py",
    "modules/communications/dispatch.py",
    "websocket_manager.py",
])
def test_no_print_in_touched_paths(rel):
    text = (BASE / rel).read_text(encoding="utf-8")
    assert "print(" not in text, f"print( still present in {rel}"
    assert "traceback.print_exc" not in text


# --------------------------------------------------------------------------- #
# PII redaction
# --------------------------------------------------------------------------- #

def test_mask_email():
    assert mask_email("alice@example.com") == "a***@example.com"
    assert mask_email("") == ""
    assert mask_email("nodomain") == "***"
    assert mask_emails(["a@x.com", "b@y.com"]) == ["a***@x.com", "b***@y.com"]
    assert body_preview("hello world") == "<11 chars>"


async def test_conversation_create_log_redacts_email(monkeypatch, caplog):
    from app.schemas import ConversationCreate

    async def _frid(db, s, si):
        return (None, None)
    async def _create(d):
        return {"id": "id1", "site_id": "S1", "tracker_code": "T1",
                "participants_emails": ["alice@example.com"]}
    monkeypatch.setattr(crud, "_resolve_friendly_ids", _frid)
    monkeypatch.setattr(crud.ConversationRepository, "create", staticmethod(_create))

    conv = ConversationCreate(study_id="ST1", site_id="S1",
                              participant_emails=["alice@example.com"])
    caplog.set_level(logging.DEBUG, logger="app.crud")
    await crud.create_conversation(None, conv)

    assert "alice@example.com" not in caplog.text  # no raw PII in logs
    assert "participants=1" in caplog.text          # redacted count survives


# --------------------------------------------------------------------------- #
# best_effort_audit (the gated mechanism)
# --------------------------------------------------------------------------- #


async def test_audit_writes_via_existing_mechanism(monkeypatch):
    called = []
    async def fake(db, **k):
        called.append(k)
    monkeypatch.setattr("app.crud.create_audit_log", fake)
    await ah.best_effort_audit(None, user="u", action="thread.create",
                               target_type="thread", target_id="42", details={"x": 1})
    assert len(called) == 1
    assert called[0]["action"] == "thread.create"
    assert called[0]["target_type"] == "thread"
    assert called[0]["target_id"] == "42"
    assert called[0]["user"] == "u"


async def test_audit_failure_logged_not_raised(monkeypatch, caplog):
    async def boom(db, **k):
        raise RuntimeError("audit db down")
    monkeypatch.setattr("app.crud.create_audit_log", boom)
    caplog.set_level(logging.ERROR, logger="app.modules.communications.audit_helpers")
    # Must NOT raise — the user action is never blocked by an audit failure.
    await ah.best_effort_audit(None, user="u", action="thread.create",
                               target_type="thread", target_id="42")
    assert "audit failed" in caplog.text


# --------------------------------------------------------------------------- #
# Route-level audit — thread message
# --------------------------------------------------------------------------- #

THREAD_ID = str(uuid.uuid4())
FIXED = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _client():
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")

    async def _user():
        return {"user_id": "u", "email": "a@b.com"}
    async def _db():
        yield None
    app.dependency_overrides[get_current_user_optional] = _user
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


@pytest.fixture
def route_wire(monkeypatch):

    async def _get_thread(db, tid):
        return {"id": str(tid), "participants_emails": ["a@b.com"]}
    async def _create_thread_message(db, tid, message):
        return {"id": str(uuid.uuid4()), "thread_id": str(tid), "message_id": None,
                "body": "hi", "author_id": "u", "author_name": "U",
                "mentioned_emails": [], "created_at": FIXED, "message_type": None}
    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(crud, "get_thread", _get_thread)
    monkeypatch.setattr(crud, "create_thread_message", _create_thread_message)
    monkeypatch.setattr(ThreadMessageRepository, "update_fields", _noop)
    monkeypatch.setattr(ai_service, "is_available", lambda: False)
    monkeypatch.setattr(manager, "publish_thread_update", _noop)

    audited = []
    async def _audit_log(db, **k):
        audited.append(k)
    monkeypatch.setattr("app.crud.create_audit_log", _audit_log)
    return audited


def test_route_thread_message_audits(route_wire, monkeypatch):
    r = _client().post(f"/api/threads/{THREAD_ID}/messages",
                       json={"body": "hi", "author_id": "u"})
    assert r.status_code == 200
    actions = [a["action"] for a in route_wire]
    assert "thread.message_create" in actions
    entry = next(a for a in route_wire if a["action"] == "thread.message_create")
    assert entry["target_type"] == "thread_message"
    assert entry["user"] == "u"



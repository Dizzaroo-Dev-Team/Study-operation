"""Tests for the Mailgun webhook signature + timestamp freshness guard.

Covers:
- Valid signature within the 5-minute window → accepted.
- Stale timestamp (>5 min in the past) → 403, even with a valid signature.
- Future timestamp (>5 min ahead) → 403.
- Invalid signature → 403.
- Bogus timestamp format → 400.
"""
from __future__ import annotations

import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException

from app.config import settings
from app.modules.communications.routes.email_webhook import (
    MAILGUN_REPLAY_WINDOW_SECONDS,
    verify_mailgun_signature,
)


@pytest.fixture(autouse=True)
def _ensure_signing_key(monkeypatch):
    """The verifier raises RuntimeError when the signing key is empty; pin a
    known value for every test in this module."""
    monkeypatch.setattr(settings, "mailgun_signing_key", "test-signing-key-do-not-use-in-prod")


def _sign(timestamp: str, token: str) -> str:
    msg = f"{timestamp}{token}".encode()
    return hmac.new(settings.mailgun_signing_key.encode(), msg, hashlib.sha256).hexdigest()


def test_accepts_fresh_valid_signature():
    ts = str(int(time.time()))
    tok = "tok-abc"
    sig = _sign(ts, tok)
    verify_mailgun_signature(ts, tok, sig)  # must not raise


def test_rejects_stale_timestamp():
    """Replay attack: signature is valid but the timestamp is days old."""
    ts = str(int(time.time()) - (MAILGUN_REPLAY_WINDOW_SECONDS + 60))
    tok = "tok-abc"
    sig = _sign(ts, tok)
    with pytest.raises(HTTPException) as exc:
        verify_mailgun_signature(ts, tok, sig)
    assert exc.value.status_code == 403
    assert "timestamp" in str(exc.value.detail).lower()


def test_rejects_far_future_timestamp():
    """Clock-skew or attacker-supplied future timestamp → reject."""
    ts = str(int(time.time()) + (MAILGUN_REPLAY_WINDOW_SECONDS + 60))
    tok = "tok-abc"
    sig = _sign(ts, tok)
    with pytest.raises(HTTPException) as exc:
        verify_mailgun_signature(ts, tok, sig)
    assert exc.value.status_code == 403


def test_rejects_bad_signature():
    ts = str(int(time.time()))
    tok = "tok-abc"
    with pytest.raises(HTTPException) as exc:
        verify_mailgun_signature(ts, tok, signature="deadbeef" * 8)
    assert exc.value.status_code == 403


def test_rejects_non_integer_timestamp():
    """A non-numeric timestamp → 400, surfaced before the freshness window
    check so callers see the right error."""
    sig = _sign("not-a-number", "tok")
    with pytest.raises(HTTPException) as exc:
        verify_mailgun_signature("not-a-number", "tok", sig)
    assert exc.value.status_code == 400


def test_window_boundary_just_inside():
    """A timestamp exactly at the window boundary is accepted (the check is
    `> WINDOW`, not `>=`)."""
    ts = str(int(time.time()) - MAILGUN_REPLAY_WINDOW_SECONDS)
    tok = "tok-abc"
    sig = _sign(ts, tok)
    verify_mailgun_signature(ts, tok, sig)  # must not raise

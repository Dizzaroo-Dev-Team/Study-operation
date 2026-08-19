"""Regression test: JWT `exp` claim is encoded as an integer (NumericDate),
not a `datetime`. Some non-Python verifiers (Go jwt-go, Node jsonwebtoken)
reject non-integer exp values per RFC 7519.
"""
from __future__ import annotations

import time
from datetime import timedelta

from jose import jwt

from app.auth import ALGORITHM, SECRET_KEY, create_access_token


def test_exp_is_integer_seconds():
    token = create_access_token({"sub": "user-1"})
    # Decode without verifying signature first to read raw claim shape.
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert "exp" in decoded
    assert isinstance(decoded["exp"], int), f"exp must be int, got {type(decoded['exp'])}"


def test_exp_is_in_the_future():
    token = create_access_token({"sub": "u"}, expires_delta=timedelta(seconds=120))
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    now = int(time.time())
    # Should expire ~120s from now (allow a small wall-clock fudge).
    assert decoded["exp"] >= now + 100
    assert decoded["exp"] <= now + 140


def test_subject_round_trips():
    token = create_access_token({"sub": "user-xyz"})
    decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert decoded["sub"] == "user-xyz"

"""Regression test: @audit must REFUSE to run the wrapped function when no
AsyncSession is passed. The previous behavior was a silent skip, which let
mutations land without their audit trail — a GxP / 21 CFR Part 11 hole.
"""
from __future__ import annotations

import pytest

from app.audit import audit


@pytest.mark.asyncio
async def test_audit_raises_when_db_session_missing():
    """Decorator must raise BEFORE invoking the wrapped function so the
    mutation can't happen without its audit row."""
    invocations = 0

    @audit("agreement.create", target_type="agreement")
    async def fn_without_db(*, actor: str):
        nonlocal invocations
        invocations += 1
        return {"id": "should-never-return"}

    with pytest.raises(RuntimeError) as exc_info:
        await fn_without_db(actor="user-1")

    msg = str(exc_info.value)
    assert "@audit" in msg
    assert "fn_without_db" in msg
    # The wrapped function MUST NOT have been called: the whole point is to
    # block the un-audited mutation.
    assert invocations == 0


@pytest.mark.asyncio
async def test_audit_raises_with_only_non_session_positional_arg():
    """A positional arg that isn't an AsyncSession still triggers the guard."""

    @audit("agreement.create", target_type="agreement")
    async def fn_bad_first_arg(not_a_session, *, actor: str):
        return {"id": "x"}

    with pytest.raises(RuntimeError):
        await fn_bad_first_arg("not-a-session", actor="user-1")

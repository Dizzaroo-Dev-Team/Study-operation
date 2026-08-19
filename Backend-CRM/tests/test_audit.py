"""Smoke tests for the audit helpers (app/audit.py).

Uses an in-memory SQLite session so the tests stay isolated and fast - we
only verify that the helpers correctly add AuditLog rows to the session,
NOT the transactional semantics (transactional() lives in app.db).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.audit import audit, record_audit
from app.models import AuditLog


@pytest.fixture
async def session() -> AsyncSession:
    """In-memory SQLite session with ONLY the audit_logs table created.

    We deliberately do NOT call Base.metadata.create_all because shared Base
    metadata picks up Postgres-only types (e.g. JSONB in
    site_budgeting_audit_log) that SQLite cannot render. These tests only
    need the AuditLog table.
    """
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(AuditLog.__table__.create)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as s:
        yield s
    await engine.dispose()


async def _all_audits(db: AsyncSession) -> list[AuditLog]:
    from sqlalchemy import select
    result = await db.execute(select(AuditLog))
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_record_audit_adds_row_without_commit(session: AsyncSession):
    await record_audit(
        session,
        action="agreement.create",
        target_type="agreement",
        target_id="abc-123",
        user="u-1",
        details={"version": 1},
    )
    # Row is in the session but uncommitted.
    pending = [obj for obj in session.new if isinstance(obj, AuditLog)]
    assert len(pending) == 1
    assert pending[0].action == "agreement.create"
    assert pending[0].target_type == "agreement"
    assert pending[0].target_id == "abc-123"
    assert pending[0].user == "u-1"
    assert pending[0].details == {"version": 1}


@pytest.mark.asyncio
async def test_record_audit_persists_after_commit(session: AsyncSession):
    await record_audit(
        session,
        action="agreement.delete",
        target_type="agreement",
        target_id="del-1",
    )
    await session.commit()
    rows = await _all_audits(session)
    assert len(rows) == 1
    assert rows[0].action == "agreement.delete"
    assert rows[0].details == {}


@pytest.mark.asyncio
async def test_audit_decorator_uses_result_id_for_target_id(session: AsyncSession):
    @audit("agreement.create", target_type="agreement")
    async def fake_create(db: AsyncSession, *, actor: str) -> SimpleNamespace:
        return SimpleNamespace(id="new-agreement-uuid")

    obj = await fake_create(session, actor="user-7")
    assert obj.id == "new-agreement-uuid"

    await session.commit()
    rows = await _all_audits(session)
    assert len(rows) == 1
    assert rows[0].action == "agreement.create"
    assert rows[0].target_type == "agreement"
    assert rows[0].target_id == "new-agreement-uuid"
    assert rows[0].user == "user-7"


@pytest.mark.asyncio
async def test_audit_decorator_uses_explicit_target_id_kwarg(session: AsyncSession):
    @audit("agreement.status_change", target_type="agreement", target_id_kwarg="agreement_id")
    async def fake_status_change(db: AsyncSession, *, agreement_id: str, actor: str):
        return None  # nothing to return; target id comes from kwarg

    await fake_status_change(session, agreement_id="given-id", actor="user-9")
    await session.commit()
    rows = await _all_audits(session)
    assert len(rows) == 1
    assert rows[0].target_id == "given-id"
    assert rows[0].user == "user-9"


@pytest.mark.asyncio
async def test_audit_decorator_does_not_audit_on_exception(session: AsyncSession):
    @audit("agreement.create", target_type="agreement")
    async def fake_create(db: AsyncSession, *, actor: str):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await fake_create(session, actor="user-1")
    rows = [obj for obj in session.new if isinstance(obj, AuditLog)]
    assert rows == []


@pytest.mark.asyncio
async def test_audit_decorator_pulls_user_id_from_user_object(session: AsyncSession):
    @audit("conversation.create", target_type="conversation")
    async def fake_create(db: AsyncSession, *, actor):
        return SimpleNamespace(id="c-1")

    fake_user = SimpleNamespace(user_id="u-from-object", role="cra")
    await fake_create(session, actor=fake_user)
    await session.commit()
    rows = await _all_audits(session)
    assert rows[0].user == "u-from-object"


def test_audit_rejects_sync_functions():
    with pytest.raises(TypeError):
        @audit("noop", target_type="x")
        def sync_fn(db):  # type: ignore[no-redef]
            return None

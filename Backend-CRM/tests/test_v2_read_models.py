"""
test_v2_read_models.py
======================

Read models + lifecycle pieces backing the V2 runner UI:
  * service.list_activity  — job executions + boundary timers per instance
  * service.retry_job      — failed -> pending, audited, then a sweep re-runs it
  * service.list_children  — child instances of a parent (incl. cancelled)

Service-level on in-memory SQLite. Run: pytest tests/test_v2_read_models.py -v
"""

import os
import sys

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import Base  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.jobs import register_job_handler  # noqa: E402
from app.modules.workflows.models import (  # noqa: E402
    WorkflowAuditEntry,
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowJob,
    WorkflowTask,
    WorkflowTimer,
)
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid, *roles):
    # Shared "wf" role so test actors can act on assignee-less mechanics steps
    # under the engine's permanent strict authorization (open mode was removed).
    return CurrentUser(id=uid, roles=[*roles, "wf"])


def _wf_strict(raw):
    """Assign assignee-less human steps to the shared "wf" role so these
    pure-mechanics bodies run under strict authorization (now the only mode)."""
    for s in raw.get("steps", []):
        if s.get("type") in ("form", "approval", "signature") and not s.get("assignee"):
            s["assignee"] = {"type": "role", "value": "wf"}
    return raw


_TABLES = [
    WorkflowDefinition.__table__,
    WorkflowDefinitionVersion.__table__,
    WorkflowInstance.__table__,
    WorkflowAuditEntry.__table__,
    WorkflowTask.__table__,
    WorkflowTimer.__table__,
    WorkflowJob.__table__,
]


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _publish(db, raw):
    body = WorkflowDefinitionBody.model_validate(_wf_strict(raw))
    await service.create_or_update_definition(db, body, publish=True, published_by="t")
    return body


def job_timer_flow(key, kind):
    return {
        "key": key, "name": "Activity flow", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "config": {"timer": {"seconds": 120, "action": "timeout"}},
             "transitions": [
                 {"id": "go", "to": "auto", "label": "Go", "action": "submit"},
                 {"id": "esc", "to": "done", "label": "Timed out", "action": "timeout"}]},
            {"id": "auto", "type": "job", "name": "Automated",
             "config": {"job": {"kind": kind, "max_attempts": 1}},
             "transitions": [
                 {"id": "jd", "to": "done", "label": "Done", "action": "job_done"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def test_list_activity_returns_timers_and_jobs(db):
    await _publish(db, job_timer_flow("ACT_A", "noop"))
    inst = await service.start_instance(db, "ACT_A", {})
    inst_id = int(inst.id)
    await db.commit()
    act = await service.list_activity(db, inst_id)
    assert [t["step_id"] for t in act["timers"]] == ["draft"]
    assert act["timers"][0]["status"] == "pending" and act["jobs"] == []

    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()
    act = await service.list_activity(db, inst_id)
    assert act["timers"][0]["status"] == "cancelled"  # left the timed step
    assert [j["kind"] for j in act["jobs"]] == ["noop"]
    assert act["jobs"][0]["status"] == "pending"


async def test_retry_job_resets_failed_and_sweep_rerun_succeeds(db):
    calls = {"n": 0}

    async def fail_once(params, context):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("boom")
        return {}

    register_job_handler("fail_once_v2", fail_once)
    raw = job_timer_flow("ACT_B", "fail_once_v2")
    # No job_failed transition: the failed job leaves the instance parked.
    await _publish(db, raw)
    inst = await service.start_instance(db, "ACT_B", {})
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()
    await service.run_pending_jobs(db)
    await db.commit()
    job = (await db.scalars(select(WorkflowJob))).all()[0]
    assert job.status == "failed"
    job_id = int(job.id)

    with pytest.raises(service.ServiceError, match="not found"):
        await service.retry_job(db, inst_id, job_id + 999, U("admin"))
    await db.rollback()
    db.expunge_all()
    out = await service.retry_job(db, inst_id, job_id, U("admin"))
    await db.commit()
    assert out["status"] == "pending" and out["attempts"] == 0
    assert await service.run_pending_jobs(db) == 1
    await db.commit()
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "done" and fresh.status == "completed"
    actions = [a.action for a in (await db.scalars(
        select(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id == inst_id))).all()]
    assert "job_retry" in actions


async def test_list_children_includes_cancelled(db):
    child = {
        "key": "ACT_CHILD", "name": "Child", "start_step": "t",
        "steps": [
            {"id": "t", "type": "approval", "name": "T",
             "transitions": [{"id": "ok", "to": "d", "label": "OK", "action": "approve"}]},
            {"id": "d", "type": "terminal", "name": "D", "transitions": []},
        ],
    }
    parent = {
        "key": "ACT_PARENT", "name": "Parent", "start_step": "fanout",
        "steps": [
            {"id": "fanout", "type": "call", "name": "Fan out",
             "config": {"call": {"definition_key": "ACT_CHILD", "items_path": "sites",
                                 "join": {"mode": "n_of_m", "value": 1}}},
             "transitions": [{"id": "cd", "to": "d", "label": "Done",
                              "action": "children_done"}]},
            {"id": "d", "type": "terminal", "name": "D", "transitions": []},
        ],
    }
    await _publish(db, child)
    await _publish(db, parent)
    p = await service.start_instance(db, "ACT_PARENT", {"sites": ["s1", "s2"]})
    pid = int(p.id)
    await db.commit()
    kids = await service.list_children(db, pid)
    assert len(kids) == 2 and all(k["status"] == "active" for k in kids)

    # One child completes -> 1-of-2 join met -> the other child is CANCELLED,
    # and the children view shows it (diagnosability).
    await service.perform_action(db, kids[0]["id"], U("u"), "ok", {}, None)
    await db.commit()
    kids = await service.list_children(db, pid)
    statuses = sorted(k["status"] for k in kids)
    assert statuses == ["cancelled", "completed"]

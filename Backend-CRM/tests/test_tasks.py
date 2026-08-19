"""
test_tasks.py
=============

V2 Phase 3: the Task abstraction (work items distinct from steps).

Covers: task creation when a token parks on human work (whole step, per
parallel branch, per current ordered-signing slot), completion when the
matching action fires, cancellation when the flow moves past (quorum met /
rework / cancel), the worklist read-model filter, claim eligibility, and
reassignment that is actually EFFECTIVE in strict mode (the engine honors the
override in place of the definition assignee).

Service-level on in-memory SQLite. Run: pytest tests/test_tasks.py -v
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
from app.modules.workflows.models import (  # noqa: E402
    WorkflowAuditEntry,
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowTask,
)
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid, *roles):
    return CurrentUser(id=uid, roles=list(roles))


_TABLES = [
    WorkflowDefinition.__table__,
    WorkflowDefinitionVersion.__table__,
    WorkflowInstance.__table__,
    WorkflowAuditEntry.__table__,
    WorkflowTask.__table__,
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


def flow_raw(key):
    """draft(form) -> parallel(legal+fin, all) -> signing(ordered s1,s2) -> done"""
    return {
        "key": key, "name": "Task test", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "par", "label": "Submit",
                              "action": "submit"}]},
            {"id": "par", "type": "parallel", "name": "Review",
             "config": {"branches": [
                 {"id": "legal", "name": "Legal",
                  "assignee": {"type": "role", "value": "legal"}},
                 {"id": "fin", "name": "Financial",
                  "assignee": {"type": "user", "value": "fin-user-1"}}],
                 "quorum": {"mode": "all"}, "on_reject": "count"},
             "transitions": [
                 {"id": "qm", "to": "signing", "label": "Met", "action": "quorum_met"},
                 {"id": "qf", "to": "draft", "label": "Rework", "action": "quorum_failed"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Sign",
             "config": {"signers": [
                 {"id": "s1", "name": "Director",
                  "assignee": {"type": "context", "value": "director_id"}},
                 {"id": "s2", "name": "VP",
                  "assignee": {"type": "role", "value": "vp"}}]},
             "transitions": [
                 {"id": "ok", "to": "done", "label": "Signed", "action": "all_signed"},
                 {"id": "dec", "to": "draft", "label": "Declined",
                  "action": "signing_declined"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def _tasks(db, inst_id, status=None):
    stmt = select(WorkflowTask).where(WorkflowTask.instance_id == inst_id)
    if status:
        stmt = stmt.where(WorkflowTask.status == status)
    return list((await db.scalars(stmt.order_by(WorkflowTask.id))).all())


async def _seed(db, key, context=None):
    body = WorkflowDefinitionBody.model_validate(flow_raw(key))
    await service.create_or_update_definition(db, body, publish=True, published_by="t")
    inst = await service.start_instance(db, key, context or {})
    await db.commit()
    return inst


async def test_task_created_on_start_and_completed_on_action(db):
    inst = await _seed(db, "TASK_A", {"director_id": "dir-9"})
    open_tasks = await _tasks(db, inst.id, "open")
    assert [(t.step_id, t.slot_id) for t in open_tasks] == [("draft", "")]
    assert open_tasks[0].assignee_type == "role"
    assert open_tasks[0].assignee_value == "study_manager"

    await service.perform_action(db, inst.id, U("sm", "study_manager"), "submit", {}, None)
    await db.commit()

    draft_task = (await _tasks(db, inst.id))[0]
    assert draft_task.status == "completed" and draft_task.completed_by == "sm"
    # One task per OPEN parallel action branch, addressing captured at creation.
    open_now = await _tasks(db, inst.id, "open")
    assert {(t.step_id, t.slot_id) for t in open_now} == {("par", "legal"), ("par", "fin")}
    fin = next(t for t in open_now if t.slot_id == "fin")
    assert fin.resolved_user_id == "fin-user-1"  # direct user resolved at creation


async def test_vote_completes_branch_task_then_slot_tasks_walk_in_order(db):
    inst = await _seed(db, "TASK_B", {"director_id": "dir-9"})
    await service.perform_action(db, inst.id, U("sm", "study_manager"), "submit", {}, None)
    await service.perform_action(db, inst.id, U("l1", "legal"), "legal:approve", {}, None)
    await db.commit()
    open_now = await _tasks(db, inst.id, "open")
    assert {(t.step_id, t.slot_id) for t in open_now} == {("par", "fin")}

    await service.perform_action(db, inst.id, U("fin-user-1"), "fin:approve", {}, None)
    await db.commit()
    # Quorum met -> ordered signing: ONLY the current slot has a task, and the
    # context-held participant was resolved at creation.
    open_now = await _tasks(db, inst.id, "open")
    assert [(t.step_id, t.slot_id) for t in open_now] == [("signing", "s1")]
    assert open_now[0].resolved_user_id == "dir-9"

    await service.perform_action(db, inst.id, U("dir-9"), "s1:sign", {}, None)
    await db.commit()
    open_now = await _tasks(db, inst.id, "open")
    assert [(t.step_id, t.slot_id) for t in open_now] == [("signing", "s2")]


async def test_rework_cancels_open_branch_tasks(db):
    inst = await _seed(db, "TASK_C")
    await service.perform_action(db, inst.id, U("sm", "study_manager"), "submit", {}, None)
    # legal rejects; quorum(all) is unreachable -> rework to draft.
    await service.perform_action(db, inst.id, U("l1", "legal"), "legal:reject", {}, None)
    await db.commit()
    tasks = await _tasks(db, inst.id)
    by_key = {(t.step_id, t.slot_id, t.status) for t in tasks}
    assert ("par", "legal", "completed") in by_key      # the vote that fired
    assert ("par", "fin", "cancelled") in by_key        # moved past, not acted
    assert ("draft", "", "open") in by_key or [
        t for t in tasks if t.step_id == "draft" and t.status == "open"]


async def test_cancel_instance_cancels_open_tasks(db):
    inst = await _seed(db, "TASK_D")
    await service.cancel_instance(db, inst.id, U("sm"))
    await db.commit()
    assert await _tasks(db, inst.id, "open") == []
    assert all(t.status == "cancelled" for t in await _tasks(db, inst.id))


async def test_worklist_filters_by_addressing_in_strict_mode(db):
    inst = await _seed(db, "TASK_E")
    await service.perform_action(db, inst.id, U("sm", "study_manager"), "submit", {}, None)
    await db.commit()

    legal_list = await service.list_tasks_for_user(db, U("l1", "legal"))
    assert [(t["step_id"], t["slot_id"]) for t in legal_list] == [("par", "legal")]
    fin_list = await service.list_tasks_for_user(db, U("fin-user-1"))
    assert [(t["slot_id"]) for t in fin_list] == ["fin"]
    assert await service.list_tasks_for_user(db, U("stranger", "nobody")) == []


async def test_claim_eligibility(db):
    inst = await _seed(db, "TASK_F")
    await service.perform_action(db, inst.id, U("sm", "study_manager"), "submit", {}, None)
    await db.commit()
    legal_task = next(t for t in await _tasks(db, inst.id, "open") if t.slot_id == "legal")

    with pytest.raises(service.ServiceError, match="not eligible"):
        await service.claim_task(db, legal_task.id, U("stranger", "nobody"))
    claimed = await service.claim_task(db, legal_task.id, U("l1", "legal"))
    assert claimed["status"] == "claimed" and claimed["claimed_by"] == "l1"


async def test_reassignment_is_effective_in_strict_mode(db):
    inst = await _seed(db, "TASK_G")
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("sm", "study_manager"), "submit", {}, None)
    await db.commit()
    db.expunge_all()
    legal_task = next(t for t in await _tasks(db, inst_id, "open") if t.slot_id == "legal")
    task_id = int(legal_task.id)

    await service.reassign_task(db, task_id, U("admin"), "alice")
    await db.commit()
    db.expunge_all()

    # The original role-holder is no longer responsible; Alice is — and the
    # ENGINE enforces that (not just the worklist).
    with pytest.raises(service.ServiceError, match="not authorized"):
        await service.perform_action(db, inst_id, U("l1", "legal"), "legal:approve", {}, None)
    await db.rollback()
    db.expunge_all()
    inst2 = await service.perform_action(db, inst_id, U("alice"), "legal:approve", {}, None)
    await db.commit()
    assert inst2.context["_branches"]["par"]["legal"]["actor"] == "alice"
    # Audit recorded the reassignment.
    audit_actions = [a.action for a in (await db.scalars(
        select(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id == inst_id)
    )).all()]
    assert "task_reassigned" in audit_actions

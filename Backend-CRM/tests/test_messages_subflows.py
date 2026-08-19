"""
test_messages_subflows.py
=========================

V2 Phase 5: external message events + sub-workflows (call activity and
multi-instance).

Messages: a wait_message step parks until deliver_message routes an event with
a matching name and correlation key (subject_ref); the payload reaches context
only via the explicit output mapping; wrong names deliver nothing.

Sub-workflows: a CALL step spawns child instance(s) (one per item for
multi-instance), parks, and advances when enough children complete per the
join policy (the same evaluate_join_policy as gateways/quorum); n_of_m cancels
straggler children; completion propagates up parent chains.

Service-level on in-memory SQLite. Run: pytest tests/test_messages_subflows.py -v
"""

import os
import sys

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
    WorkflowJob,
    WorkflowTask,
    WorkflowTimer,
)
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid, *roles):
    # Shared "wf" role so test actors can act on the assignee-less mechanics steps
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


# ---------------------------------------------------------------------------
# MESSAGES
# ---------------------------------------------------------------------------
def message_flow(key):
    return {
        "key": key, "name": "Message flow", "start_step": "wait_payment",
        "steps": [
            {"id": "wait_payment", "type": "wait_message", "name": "Await payment",
             "config": {"message": {"name": "payment_cleared",
                                    "output": {"paid_amount": "data.amount"}}},
             "transitions": [{"id": "mr", "to": "after", "label": "Paid",
                              "action": "message_received"}]},
            {"id": "after", "type": "approval", "name": "After",
             "transitions": [{"id": "ok", "to": "done", "label": "OK",
                              "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def test_message_correlated_by_subject_and_name(db):
    await _publish(db, message_flow("MSG_A"))
    inst = await service.start_instance(db, "MSG_A", {}, subject_ref="loan-77")
    await db.commit()
    inst_id = int(inst.id)
    assert inst.current_step == "wait_payment"

    # Wrong name: nothing moves. Wrong subject: nothing moves.
    r = await service.deliver_message(db, "shipment_arrived", "loan-77", {})
    assert r["delivered"] == 0
    r = await service.deliver_message(db, "payment_cleared", "loan-99", {})
    assert r["delivered"] == 0

    # Right name + correlation: routed, payload mapped EXPLICITLY.
    r = await service.deliver_message(db, "payment_cleared", "loan-77",
                                      {"data": {"amount": 9100}, "noise": True})
    await db.commit()
    assert r["delivered"] == 1
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "after"
    assert fresh.context["paid_amount"] == 9100
    assert "noise" not in fresh.context
    actions = [a.action for a in (await db.scalars(
        select(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id == inst_id))).all()]
    assert "message_received" in actions


# ---------------------------------------------------------------------------
# SUB-WORKFLOWS
# ---------------------------------------------------------------------------
def child_flow(key):
    """A small child: one approval -> done."""
    return {
        "key": key, "name": "Child", "start_step": "task",
        "steps": [
            {"id": "task", "type": "approval", "name": "Child task",
             "transitions": [{"id": "ok", "to": "done", "label": "OK",
                              "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


def parent_flow(key, child_key, items_path=None, join=None):
    call_cfg = {"definition_key": child_key,
                "context_map": {"study": "study_name"}}
    if items_path:
        call_cfg["items_path"] = items_path
    if join:
        call_cfg["join"] = join
    return {
        "key": key, "name": "Parent", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "transitions": [{"id": "go", "to": "fanout", "label": "Go",
                              "action": "submit"}]},
            {"id": "fanout", "type": "call", "name": "Per-site activation",
             "config": {"call": call_cfg},
             "transitions": [{"id": "cd", "to": "wrapup", "label": "All sites done",
                              "action": "children_done"}]},
            {"id": "wrapup", "type": "approval", "name": "Wrap up",
             "transitions": [{"id": "ok", "to": "done", "label": "OK",
                              "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def _children_of(db, parent_id):
    return list((await db.scalars(
        select(WorkflowInstance)
        .where(WorkflowInstance.parent_instance_id == parent_id)
        .order_by(WorkflowInstance.id))).all())


async def test_call_spawns_child_and_completion_advances_parent(db):
    await _publish(db, child_flow("CHILD_A"))
    await _publish(db, parent_flow("PARENT_A", "CHILD_A"))
    parent = await service.start_instance(db, "PARENT_A", {"study_name": "ST-1"})
    pid = int(parent.id)
    await service.perform_action(db, pid, U("u"), "go", {}, None)
    await db.commit()

    kids = await _children_of(db, pid)
    assert len(kids) == 1
    child = kids[0]
    assert child.definition_key == "CHILD_A" and child.parent_step_id == "fanout"
    assert child.context["study"] == "ST-1"  # context_map copied at spawn

    parent_fresh = await service.get_instance(db, pid)
    assert parent_fresh.current_step == "fanout"  # parked, awaiting the child

    # Complete the child -> ChildCompleted propagates -> parent advances.
    await service.perform_action(db, int(child.id), U("u"), "ok", {}, None)
    await db.commit()
    parent_fresh = await service.get_instance(db, pid)
    assert parent_fresh.current_step == "wrapup"
    assert parent_fresh.context["_calls"]["fanout"]["done"][str(child.id)] == "done"


async def test_multi_instance_with_n_of_m_join_cancels_stragglers(db):
    await _publish(db, child_flow("CHILD_B"))
    await _publish(db, parent_flow("PARENT_B", "CHILD_B", items_path="sites",
                                   join={"mode": "n_of_m", "value": 2}))
    parent = await service.start_instance(
        db, "PARENT_B", {"sites": ["site-1", "site-2", "site-3"]})
    pid = int(parent.id)
    await service.perform_action(db, pid, U("u"), "go", {}, None)
    await db.commit()

    kids = await _children_of(db, pid)
    assert len(kids) == 3
    assert [k.context["item"] for k in kids] == ["site-1", "site-2", "site-3"]

    # Two of three complete -> join met -> parent advances, straggler cancelled.
    await service.perform_action(db, int(kids[0].id), U("u"), "ok", {}, None)
    await service.perform_action(db, int(kids[1].id), U("u"), "ok", {}, None)
    await db.commit()
    parent_fresh = await service.get_instance(db, pid)
    assert parent_fresh.current_step == "wrapup"
    straggler = await service.get_instance(db, int(kids[2].id))
    assert straggler.status == "cancelled"


async def test_completion_propagates_up_a_two_level_chain(db):
    await _publish(db, child_flow("CHILD_C"))
    # Middle workflow calls CHILD_C; top workflow calls MIDDLE_C.
    await _publish(db, parent_flow("MIDDLE_C", "CHILD_C"))
    top_raw = parent_flow("TOP_C", "MIDDLE_C")
    # Top's wrapup is reached when MIDDLE completes entirely.
    await _publish(db, top_raw)
    top = await service.start_instance(db, "TOP_C", {})
    tid = int(top.id)
    await service.perform_action(db, tid, U("u"), "go", {}, None)
    await db.commit()

    middle = (await _children_of(db, tid))[0]
    await service.perform_action(db, int(middle.id), U("u"), "go", {}, None)
    await db.commit()
    grandchild = (await _children_of(db, int(middle.id)))[0]

    # Finish the grandchild; middle's call joins; finish middle's wrapup ->
    # middle completes -> TOP advances. Two levels of propagation.
    await service.perform_action(db, int(grandchild.id), U("u"), "ok", {}, None)
    await service.perform_action(db, int(middle.id), U("u"), "ok", {}, None)
    await db.commit()
    top_fresh = await service.get_instance(db, tid)
    assert top_fresh.current_step == "wrapup"


async def test_cancelled_child_resolves_all_join_does_not_hang(db):
    # The bug: an 'all' join over children where one child is CANCELLED used to
    # hang forever (a cancelled child never notified the parent). Now a cancelled
    # child is a terminal arrival that resolves the join.
    await _publish(db, child_flow("CHILD_X"))
    await _publish(db, parent_flow("PARENT_X", "CHILD_X", items_path="sites"))  # join=all
    parent = await service.start_instance(db, "PARENT_X", {"sites": ["s1", "s2"]})
    pid = int(parent.id)
    await service.perform_action(db, pid, U("u"), "go", {}, None)
    await db.commit()

    kids = await _children_of(db, pid)
    assert len(kids) == 2

    # One child completes; the parent is still parked waiting on the second.
    await service.perform_action(db, int(kids[0].id), U("u"), "ok", {}, None)
    await db.commit()
    assert (await service.get_instance(db, pid)).current_step == "fanout"

    # CANCEL the second child — the 'all' join must now resolve (not hang).
    await service.cancel_instance(db, int(kids[1].id), U("u"), comment="site dropped")
    await db.commit()
    parent_fresh = await service.get_instance(db, pid)
    assert parent_fresh.current_step == "wrapup", parent_fresh.current_step
    calls = parent_fresh.context["_calls"]["fanout"]
    assert str(kids[1].id) in calls["done"]              # recorded as an arrival
    assert str(kids[1].id) in calls.get("cancelled", [])  # tracked as a cancel/failure
    # The completed child kept its legacy shape (ref -> terminal step name).
    assert calls["done"][str(kids[0].id)] == "done"


async def test_single_cancelled_child_resolves_all_join(db):
    # Minimal hang case: the ONLY child of an 'all' join is cancelled -> resolve.
    await _publish(db, child_flow("CHILD_Y"))
    await _publish(db, parent_flow("PARENT_Y", "CHILD_Y"))  # single child, join=all
    parent = await service.start_instance(db, "PARENT_Y", {"study_name": "ST"})
    pid = int(parent.id)
    await service.perform_action(db, pid, U("u"), "go", {}, None)
    await db.commit()
    kid = (await _children_of(db, pid))[0]
    assert (await service.get_instance(db, pid)).current_step == "fanout"

    await service.cancel_instance(db, int(kid.id), U("u"), comment="dropped")
    await db.commit()
    assert (await service.get_instance(db, pid)).current_step == "wrapup"


async def test_workflow_cannot_call_itself(db):
    raw = parent_flow("SELF_A", "SELF_A")
    await _publish(db, raw)
    inst = await service.start_instance(db, "SELF_A", {})
    import pytest
    with pytest.raises(service.ServiceError, match="cannot call itself"):
        await service.perform_action(db, int(inst.id), U("u"), "go", {}, None)

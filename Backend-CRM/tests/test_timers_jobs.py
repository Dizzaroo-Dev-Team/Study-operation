"""
test_timers_jobs.py
===================

V2 Phase 4: Timer + Job.

Timers: armed (durable row, future fire_at) when a step with config.timer is
entered; run_due_timers fires the authored transition action as a SYSTEM event
(audit row, task diff); a timer whose step was already left is cancelled, never
crashes the sweep; leaving a step cancels its pending timer.

Jobs: a JOB step parks and emits InvokeJob; run_pending_jobs executes the
registered handler; the result lands in context ONLY through the explicit
output mapping; a failing handler retries to max_attempts then routes the
authored job_failed transition; the kernel never merges results blindly.

Service-level on in-memory SQLite. Run: pytest tests/test_timers_jobs.py -v
"""

import os
import sys
from datetime import datetime, timedelta, timezone

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
    # Every test actor carries the shared "wf" role so they can act on the
    # assignee-less mechanics steps below under the engine's permanent strict
    # authorization (open mode was removed).
    return CurrentUser(id=uid, roles=[*roles, "wf"])


def _wf_strict(raw):
    """Assign every assignee-less human step to the shared "wf" role so these
    pure-mechanics bodies run under strict authorization (which is now the only
    mode). Steps that already declare an assignee are left untouched."""
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


# ---------------------------------------------------------------------------
# TIMERS
# ---------------------------------------------------------------------------
def timer_flow(key):
    """review(approval, 1h escalation timer) -> done; timeout -> escalated(form) -> done"""
    return {
        "key": key, "name": "Timer flow", "start_step": "review",
        "steps": [
            {"id": "review", "type": "approval", "name": "Review",
             "assignee": {"type": "role", "value": "legal"},
             "config": {"timer": {"seconds": 3600, "action": "timeout"}},
             "transitions": [
                 {"id": "ok", "to": "done", "label": "Approve", "action": "approve"},
                 {"id": "esc", "to": "escalated", "label": "Escalate", "action": "timeout"}]},
            {"id": "escalated", "type": "approval", "name": "Escalated review",
             "assignee": {"type": "role", "value": "vp"},
             "transitions": [{"id": "esc_ok", "to": "done", "label": "Approve",
                              "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def _seed(db, raw):
    body = WorkflowDefinitionBody.model_validate(_wf_strict(raw))
    await service.create_or_update_definition(db, body, publish=True, published_by="t")
    inst = await service.start_instance(db, body.key, {})
    await db.commit()
    return inst


async def test_timer_armed_on_entry_with_future_fire_at(db):
    inst = await _seed(db, timer_flow("TMR_A"))
    timers = (await db.scalars(select(WorkflowTimer))).all()
    assert len(timers) == 1
    t = timers[0]
    assert t.step_id == "review" and t.action == "timeout" and t.status == "pending"
    fire_at = t.fire_at if t.fire_at.tzinfo else t.fire_at.replace(tzinfo=timezone.utc)
    assert fire_at > datetime.now(timezone.utc) + timedelta(minutes=50)


async def test_due_timer_fires_escalation_and_rewrites_tasks(db):
    inst = await _seed(db, timer_flow("TMR_B"))
    inst_id = int(inst.id)
    # Nothing due yet.
    assert await service.run_due_timers(db) == 0
    # Time passes: sweep with a future "now".
    fired = await service.run_due_timers(
        db, now=datetime.now(timezone.utc) + timedelta(hours=2))
    await db.commit()
    assert fired == 1
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "escalated"
    # The review task was cancelled (not completed by anyone); the escalation
    # task exists; the audit/event log carries the system row.
    tasks = {(t.step_id, t.status) for t in (await db.scalars(
        select(WorkflowTask).where(WorkflowTask.instance_id == inst_id))).all()}
    assert ("review", "cancelled") in tasks and ("escalated", "open") in tasks
    actions = [a.action for a in (await db.scalars(
        select(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id == inst_id))).all()]
    assert "timer_fired" in actions


async def test_leaving_step_cancels_timer_and_stale_timer_never_fires(db):
    inst = await _seed(db, timer_flow("TMR_C"))
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("l1", "legal"), "ok", {}, None)
    await db.commit()
    t = (await db.scalars(select(WorkflowTimer))).all()[0]
    assert t.status == "cancelled"  # departing the step cancelled it
    # Even a pending-but-stale timer is swept safely.
    t.status = "pending"
    await db.flush()
    fired = await service.run_due_timers(
        db, now=datetime.now(timezone.utc) + timedelta(hours=2))
    assert fired == 0
    assert t.status == "cancelled"


# ---------------------------------------------------------------------------
# JOBS
# ---------------------------------------------------------------------------
def job_flow(key, kind="noop", params=None, max_attempts=1, with_fail_path=True,
             output=None):
    job_cfg = {"kind": kind, "params": params or {}, "max_attempts": max_attempts,
               "output": output if output is not None else {}}
    transitions = [{"id": "jd", "to": "after", "label": "Done", "action": "job_done"}]
    if with_fail_path:
        transitions.append({"id": "jf", "to": "failed", "label": "Failed",
                            "action": "job_failed"})
    return {
        "key": key, "name": "Job flow", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "transitions": [{"id": "go", "to": "auto", "label": "Go",
                              "action": "submit"}]},
            {"id": "auto", "type": "job", "name": "Automated step",
             "config": {"job": job_cfg}, "transitions": transitions},
            {"id": "after", "type": "approval", "name": "After",
             "transitions": [{"id": "ok", "to": "done", "label": "OK",
                              "action": "approve"}]},
            {"id": "failed", "type": "terminal", "name": "Failed", "transitions": []},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def test_job_invoked_on_entry_and_output_mapped_explicitly(db):
    raw = job_flow("JOB_A", kind="noop",
                   params={"result": {"data": {"amount": 125000}, "extra": "x"}},
                   output={"contract_value": "data.amount"})
    inst = await _seed(db, raw)
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()

    jobs = (await db.scalars(select(WorkflowJob))).all()
    assert len(jobs) == 1 and jobs[0].status == "pending" and jobs[0].kind == "noop"

    processed = await service.run_pending_jobs(db)
    await db.commit()
    assert processed == 1
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "after"
    # EXPLICIT mapping only: the mapped key landed, the unmapped one did not.
    assert fresh.context["contract_value"] == 125000
    assert "extra" not in fresh.context
    assert jobs[0].status == "completed"


async def test_failing_job_retries_then_routes_error_transition(db):
    calls = {"n": 0}

    async def flaky(params, context):
        calls["n"] += 1
        raise RuntimeError("provider down")

    register_job_handler("always_fails", flaky)
    inst = await _seed(db, job_flow("JOB_B", kind="always_fails", max_attempts=3))
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()

    # Sweeps 1 and 2: retrying, instance still parked on the job step.
    assert await service.run_pending_jobs(db) == 0
    assert await service.run_pending_jobs(db) == 0
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "auto"
    # Sweep 3: attempts exhausted -> job_failed transition -> 'failed' terminal.
    assert await service.run_pending_jobs(db) == 1
    await db.commit()
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "failed" and fresh.status == "completed"
    job = (await db.scalars(select(WorkflowJob))).all()[0]
    assert job.status == "failed" and "provider down" in (job.error or "")
    assert calls["n"] == 3


async def test_retry_succeeds_midway(db):
    calls = {"n": 0}

    async def flaky_then_ok(params, context):
        calls["n"] += 1
        if calls["n"] < 2:
            raise RuntimeError("transient")
        return {"ok": True}

    register_job_handler("flaky_then_ok", flaky_then_ok)
    inst = await _seed(db, job_flow("JOB_C", kind="flaky_then_ok", max_attempts=3,
                                    output={"job_ok": "ok"}))
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()
    assert await service.run_pending_jobs(db) == 0   # attempt 1 fails
    assert await service.run_pending_jobs(db) == 1   # attempt 2 succeeds
    await db.commit()
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "after" and fresh.context["job_ok"] is True


async def test_unregistered_kind_falls_back_to_noop(db):
    # An unknown/placeholder kind must NOT dead-end the workflow: the executor
    # falls back to the safe noop handler so the step completes and advances.
    inst = await _seed(db, job_flow("JOB_D", kind="no_such_handler", max_attempts=5))
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()
    assert await service.run_pending_jobs(db) == 1   # completes via noop fallback
    await db.commit()
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "after"             # advanced, NOT "failed"
    job = (await db.scalars(select(WorkflowJob).where(
        WorkflowJob.instance_id == inst_id))).all()[0]
    assert job.status == "completed"


# ---------------------------------------------------------------------------
# REAL handlers (PART B): the registered generate_document + notify handlers run
# an authored job step to completion (no "no handler registered" error).
# ---------------------------------------------------------------------------
async def test_real_registered_handlers_run_to_completion(db):
    for kind in ("generate_document", "notify"):
        inst = await _seed(db, job_flow(f"REAL_{kind}", kind=kind,
                                        params={"title": "Final Package",
                                                "subject": "Package executed"}))
        inst_id = int(inst.id)
        await service.perform_action(db, inst_id, U("u"), "go", {}, None)
        await db.commit()
        assert await service.run_pending_jobs(db) == 1
        await db.commit()
        fresh = await service.get_instance(db, inst_id)
        assert fresh.current_step == "after", (kind, fresh.current_step)
        job = (await db.scalars(select(WorkflowJob).where(
            WorkflowJob.instance_id == inst_id))).all()[0]
        assert job.status == "completed", (kind, job.status, job.error)


def parallel_jobs_flow(key):
    """The reported scenario: two parallel tracks -> join -> auto PDF (job) ->
    sign-off (approval w/ 2-min escalation timer) -> auto notify (job) -> done."""
    return {
        "key": key, "name": "Parallel + jobs + timer", "start_step": "intake",
        "steps": [
            {"id": "intake", "type": "form", "name": "Intake",
             "transitions": [{"id": "s", "to": "fork", "label": "Submit", "action": "submit"}]},
            {"id": "fork", "type": "split", "name": "Open tracks", "transitions": [
                {"id": "a", "to": "legal", "label": "Legal", "action": "auto"},
                {"id": "b", "to": "budget", "label": "Budget", "action": "auto"}]},
            {"id": "legal", "type": "approval", "name": "Legal review",
             "transitions": [{"id": "la", "to": "merge", "label": "Approve", "action": "approve"}]},
            {"id": "budget", "type": "approval", "name": "Budget review",
             "transitions": [{"id": "ba", "to": "merge", "label": "Approve", "action": "approve"}]},
            {"id": "merge", "type": "join", "name": "Merge", "config": {"join": {"mode": "all"}},
             "transitions": [{"id": "m", "to": "render", "label": "Merged", "action": "join_met"}]},
            {"id": "render", "type": "job", "name": "Generate Final PDF",
             "config": {"job": {"kind": "generate_document", "params": {"title": "Final Package"},
                                "output": {"document_url": "document_path"}}},
             "transitions": [
                 {"id": "rd", "to": "signoff", "label": "Rendered", "action": "job_done"},
                 {"id": "rf", "to": "intake", "label": "Failed", "action": "job_failed"}]},
            {"id": "signoff", "type": "approval", "name": "Final sign-off",
             "config": {"timer": {"seconds": 120, "action": "escalate"}},
             "transitions": [
                 {"id": "ok", "to": "notify", "label": "Approve", "action": "approve"},
                 {"id": "esc", "to": "escalated", "label": "Escalate", "action": "escalate"}]},
            {"id": "escalated", "type": "approval", "name": "Escalated",
             "transitions": [{"id": "eok", "to": "notify", "label": "Approve", "action": "approve"}]},
            {"id": "notify", "type": "job", "name": "Notify everyone",
             "config": {"job": {"kind": "notify", "params": {"subject": "Package executed"}}},
             "transitions": [{"id": "nd", "to": "done", "label": "Done", "action": "job_done"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def test_e2e_parallel_tracks_pdf_and_notify_run_to_completion(db):
    inst = await _seed(db, parallel_jobs_flow("E2E"))
    inst_id = int(inst.id)

    # Submit -> split opens BOTH tracks; approve each -> join(all) fires -> PDF job.
    await service.perform_action(db, inst_id, U("u"), "s", {}, None)
    await service.perform_action(db, inst_id, U("u"), "la", {}, None)
    await service.perform_action(db, inst_id, U("u"), "ba", {}, None)
    await db.commit()
    assert (await service.get_instance(db, inst_id)).current_step == "render"

    # PDF job sweep: generate_document runs to completion (NOT "no handler") -> signoff.
    assert await service.run_pending_jobs(db) == 1
    await db.commit()
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "signoff", fresh.current_step
    # The 2-minute escalation timer was armed on the sign-off step.
    armed = [t for t in (await db.scalars(select(WorkflowTimer).where(
        WorkflowTimer.instance_id == inst_id))).all() if t.step_id == "signoff"]
    assert armed and armed[0].action == "escalate"

    # Sign off -> notify job sweep: notify runs to completion -> done.
    await service.perform_action(db, inst_id, U("mgr"), "ok", {}, None)
    await db.commit()
    assert (await service.get_instance(db, inst_id)).current_step == "notify"
    assert await service.run_pending_jobs(db) == 1
    await db.commit()
    final = await service.get_instance(db, inst_id)
    assert final.current_step == "done" and final.status == "completed"

    # BOTH jobs completed; neither hit "no handler registered".
    jobs = (await db.scalars(select(WorkflowJob).where(
        WorkflowJob.instance_id == inst_id).order_by(WorkflowJob.id))).all()
    assert {j.kind for j in jobs} == {"generate_document", "notify"}
    assert all(j.status == "completed" for j in jobs), [(j.kind, j.status, j.error) for j in jobs]
    assert not any("no handler" in (j.error or "") for j in jobs)


async def test_run_sweeps_once_advances_job_in_background(db):
    # The dev background sweeper + the /run-sweeps endpoint both call this one
    # entry point. Proves a job advances via a single sweep with no panel open.
    inst = await _seed(db, job_flow("SWEEP1", kind="noop"))
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()
    assert (await service.get_instance(db, inst_id)).current_step == "auto"
    out = await service.run_sweeps_once(db)
    await db.commit()
    assert out["jobs_processed"] >= 1
    assert (await service.get_instance(db, inst_id)).current_step == "after"


async def test_job_activity_exposes_result_for_degraded_or_real_pdf(db):
    # The job panel distinguishes a DEGRADED completion from a real one via the
    # job result. Either way the result dict carries the 'generated' flag, so the
    # UI never shows a silent "completed".
    inst = await _seed(db, job_flow("ACT1", kind="generate_document",
                                    params={"title": "Final"}))
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()
    await service.run_sweeps_once(db)
    await db.commit()
    activity = await service.list_activity(db, inst_id)
    jobs = [j for j in activity["jobs"] if j["step_id"] == "auto"]
    assert jobs and jobs[0]["status"] == "completed"
    assert jobs[0]["result"] is not None and "generated" in jobs[0]["result"]
    # When a PDF backend exists, document_url is present; when degraded, generated
    # is False with a reason — both are surfaced, neither is silent.
    res = jobs[0]["result"]
    assert ("document_url" in res) or (res.get("generated") is False and "reason" in res)


async def test_generate_document_produces_real_result_shape(db):
    # The generate_document handler runs and returns the REAL result shape
    # ({generated, document_path, ...}) — proving it invoked the existing PDF
    # generator rather than no-op'ing. (Value of document_path depends on whether
    # the env has a PDF backend; the contract we assert is the handler ran + shape.)
    raw = job_flow("DOCMAP", kind="generate_document",
                   params={"title": "Final Package"},
                   output={"document_url": "document_path"})
    inst = await _seed(db, raw)
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("u"), "go", {}, None)
    await db.commit()
    assert await service.run_pending_jobs(db) == 1
    await db.commit()
    fresh = await service.get_instance(db, inst_id)
    assert fresh.current_step == "after"
    job = (await db.scalars(select(WorkflowJob).where(
        WorkflowJob.instance_id == inst_id))).all()[0]
    assert job.status == "completed"
    assert "document_path" in (job.result or {}) and "generated" in (job.result or {})

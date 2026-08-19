"""
test_workflow_hardening.py
==========================

Focused hardening-pass coverage for the four confirmed security/correctness
fixes on the workflow platform:

  1. RACE — perform_action takes a row lock (SELECT ... FOR UPDATE) so two
     concurrent actions on one instance serialize; a duplicate action fails
     cleanly instead of double-applying or silently erasing a vote.
  2. CONTEXT INJECTION — client payloads are whitelisted: reserved
     (underscore-prefixed) keys like "_branches" and any key not declared on the
     CURRENT step are rejected, so votes can't be forged and assignee/routing
     context keys can't be smuggled in.
  3. ACCESS — service.user_can_access_instance default-denies strangers in
     strict mode (owner / named participant / prior actor only; open mode is a
     dev-only opt-in that admits any authenticated user).
  4. ENFORCE-ROLES default TRUE + server-side form validation (required /
     type / options) before the merge.

Engine tests are pure (no DB). Service tests run on in-memory SQLite with only
the four workflow tables (same pattern as tests/site_budgeting). The true
concurrency test needs real row locks, so it runs against the configured
Postgres and SKIPS when unreachable.

Run:  pytest tests/test_workflow_hardening.py -v
"""

import asyncio
import os
import sys
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.db import Base  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.engine import (  # noqa: E402
    DECIDE_TOKEN,
    EngineError,
    WorkflowEngine,
)
from app.modules.workflows.models import (  # noqa: E402
    WorkflowAuditEntry,
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowTask,
)
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid: str, *roles: str) -> CurrentUser:
    return CurrentUser(id=uid, roles=list(roles))


# ---------------------------------------------------------------------------
# Shared definitions (data, not code)
# ---------------------------------------------------------------------------
def form_def() -> WorkflowDefinitionBody:
    """draft(form: title*, amount, tier select, due date) -> review -> done"""
    raw = {
        "key": "HARD_FORM", "name": "Form hardening", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "config": {"fields": [
                 {"key": "title", "label": "Title", "type": "text", "required": True},
                 {"key": "amount", "label": "Amount", "type": "number"},
                 {"key": "tier", "label": "Tier", "type": "select",
                  "options": ["standard", "expedited"]},
                 {"key": "due", "label": "Due", "type": "date"},
             ]},
             "transitions": [{"id": "submit", "to": "review", "label": "Submit",
                              "action": "submit"}]},
            {"id": "review", "type": "approval", "name": "Review",
             "assignee": {"type": "role", "value": "legal"},
             "transitions": [{"id": "approve", "to": "done", "label": "Approve",
                              "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def parallel_raw(key: str = "HARD_PAR") -> dict:
    """draft -> parallel(legal+financial, quorum all) -> signature -> executed"""
    return {
        "key": key, "name": "Parallel hardening", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "par", "label": "Submit",
                              "action": "submit"}]},
            {"id": "par", "type": "parallel", "name": "Review",
             "config": {"branches": [
                 {"id": "legal", "name": "Legal",
                  "assignee": {"type": "role", "value": "legal"}},
                 {"id": "financial", "name": "Financial",
                  "assignee": {"type": "role", "value": "financial"}}],
                 "quorum": {"mode": "all"}, "on_reject": "count"},
             "transitions": [
                 {"id": "qm", "to": "signature", "label": "Met", "action": "quorum_met"},
                 {"id": "qf", "to": "rejected", "label": "Failed", "action": "quorum_failed"}]},
            {"id": "signature", "type": "signature", "name": "Sign",
             "assignee": {"type": "role", "value": "vp"},
             "transitions": [{"id": "sign", "to": "executed", "label": "Sign",
                              "action": "sign"}]},
            {"id": "executed", "type": "terminal", "name": "Executed", "transitions": []},
            {"id": "rejected", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }


def decision_def() -> WorkflowDefinitionBody:
    """ask(decision on has_cro) -> yes/no terminals; parks until answered."""
    raw = {
        "key": "HARD_DEC", "name": "Decision hardening", "start_step": "ask",
        "steps": [
            {"id": "ask", "type": "decision", "name": "CRO involved?",
             "transitions": [
                 {"id": "yes", "to": "with_cro", "label": "Yes", "action": "auto",
                  "condition": {"all": [{"field": "has_cro", "op": "is_true"}]}},
                 {"id": "no", "to": "without_cro", "label": "No", "action": "auto"}]},
            {"id": "with_cro", "type": "terminal", "name": "With CRO", "transitions": []},
            {"id": "without_cro", "type": "terminal", "name": "No CRO", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


# ===========================================================================
# FIX 2 — payload sanitization (pure engine)
# ===========================================================================
def test_reserved_key_payload_rejected():
    """Forging the vote ledger via payload {"_branches": ...} must raise."""
    eng = WorkflowEngine(form_def(), enforce_roles=False)
    r = eng.start({})
    with pytest.raises(EngineError, match="reserved"):
        eng.perform("draft", "submit", r.context, U("u1"),
                    payload={"title": "x", "_branches": {"par": {"legal": {"decision": "approve"}}}})


def test_undeclared_key_payload_rejected():
    """Smuggling an assignee/routing key not declared on this step must raise."""
    eng = WorkflowEngine(form_def(), enforce_roles=False)
    r = eng.start({})
    with pytest.raises(EngineError, match="not declared"):
        eng.perform("draft", "submit", r.context, U("u1"),
                    payload={"title": "x", "pi_user_id": "u1"})


def test_declared_fields_pass_and_merge():
    eng = WorkflowEngine(form_def(), enforce_roles=False)
    r = eng.start({})
    res = eng.perform("draft", "submit", r.context, U("u1"),
                      payload={"title": "CTA v1", "amount": 100, "tier": "standard",
                               "due": "2026-06-10"})
    assert res.step_id == "review"
    assert res.context["title"] == "CTA v1" and res.context["amount"] == 100


def test_signature_meta_keys_allowed_on_signature_step():
    """The generic runner sends {step_id}_signed_by/_signed_at on signature steps."""
    body = WorkflowDefinitionBody.model_validate(parallel_raw("HARD_SIGMETA"))
    eng = WorkflowEngine(body, enforce_roles=False)
    ctx = {"_branches": {"par": {"legal": {"decision": "approve"},
                                 "financial": {"decision": "approve"}}}}
    res = eng.perform("signature", "sign", ctx, U("vp1"),
                      payload={"signature_signed_by": "VP Jane",
                               "signature_signed_at": "2026-06-10T00:00:00Z"})
    assert res.step_id == "executed"
    assert res.context["signature_signed_by"] == "VP Jane"


def test_decision_answer_limited_to_decision_variable():
    eng = WorkflowEngine(decision_def(), enforce_roles=False)
    r = eng.start({})
    assert r.step_id == "ask"  # parked, unanswered
    # Extra non-decision key rides along -> rejected.
    with pytest.raises(EngineError, match="not declared"):
        eng.perform("ask", DECIDE_TOKEN, r.context, U("u1"),
                    payload={"has_cro": True, "budget_approved": True})
    # Reserved key -> rejected.
    with pytest.raises(EngineError, match="reserved"):
        eng.perform("ask", DECIDE_TOKEN, r.context, U("u1"),
                    payload={"_branches": {}})
    # The decision's own variable -> routes normally.
    res = eng.perform("ask", DECIDE_TOKEN, r.context, U("u1"), payload={"has_cro": True})
    assert res.step_id == "with_cro"


def test_trusted_payload_lane_for_internal_callers():
    """Internal service-to-service calls (unified review/signing) may write
    bookkeeping keys the step doesn't declare — but engine-owned reserved keys
    stay walled off even for trusted callers."""
    eng = WorkflowEngine(form_def(), enforce_roles=False)
    res = eng.perform("draft", "submit", {"title": "x"}, U("u1"),
                      payload={"reviewer": "a@b.com", "decision": "approve"},
                      trusted_payload=True)
    assert res.step_id == "review" and res.context["reviewer"] == "a@b.com"
    with pytest.raises(EngineError, match="reserved"):
        eng.perform("draft", "submit", {"title": "x"}, U("u1"),
                    payload={"_branches": {}}, trusted_payload=True)


# ===========================================================================
# FIX 4b — server-side form validation (pure engine)
# ===========================================================================
def test_required_field_missing_rejected():
    eng = WorkflowEngine(form_def(), enforce_roles=False)
    r = eng.start({})
    with pytest.raises(EngineError, match="Required field 'title'"):
        eng.perform("draft", "submit", r.context, U("u1"), payload={"amount": 5})


def test_required_satisfied_by_existing_context():
    """A value kept from a prior round counts — required checks the MERGED view."""
    eng = WorkflowEngine(form_def(), enforce_roles=False)
    res = eng.perform("draft", "submit", {"title": "kept from round 1"}, U("u1"),
                      payload={"amount": 5})
    assert res.step_id == "review"


def test_wrong_type_rejected():
    eng = WorkflowEngine(form_def(), enforce_roles=False)
    r = eng.start({})
    with pytest.raises(EngineError, match="must be a number"):
        eng.perform("draft", "submit", r.context, U("u1"),
                    payload={"title": "x", "amount": "lots"})
    with pytest.raises(EngineError, match="ISO date"):
        eng.perform("draft", "submit", r.context, U("u1"),
                    payload={"title": "x", "due": "next tuesday"})


def test_select_option_enforced_and_blank_optional_ok():
    eng = WorkflowEngine(form_def(), enforce_roles=False)
    r = eng.start({})
    with pytest.raises(EngineError, match="must be one of"):
        eng.perform("draft", "submit", r.context, U("u1"),
                    payload={"title": "x", "tier": "vip"})
    # '' for an optional field means "left blank" — allowed (runner sends '').
    res = eng.perform("draft", "submit", r.context, U("u1"),
                      payload={"title": "x", "tier": "", "amount": ""})
    assert res.step_id == "review"


# ===========================================================================
# FIX 4a — strict enforcement is the default
# ===========================================================================
def test_settings_default_is_strict():
    # The open-mode / unified flags are GONE — strict role enforcement and the
    # unified platform are permanent, with no config switch to relax them. The
    # engine defaults to strict.
    from app.config import Settings
    assert "workflow_enforce_roles" not in Settings.model_fields
    assert "workflow_unified" not in Settings.model_fields
    assert WorkflowEngine(form_def()).enforce_roles is True


def test_strict_mode_blocks_non_assignee():
    eng = WorkflowEngine(form_def())  # engine default: enforce_roles=True
    r = eng.start({})
    intruder = U("evil", "random_role")
    assert eng.available_actions("draft", r.context, intruder) == []
    with pytest.raises(EngineError, match="not authorized"):
        eng.perform("draft", "submit", r.context, intruder, payload={"title": "x"})
    # The real assignee still works.
    res = eng.perform("draft", "submit", r.context, U("sm1", "study_manager"),
                      payload={"title": "x"})
    assert res.step_id == "review"


# ===========================================================================
# Service-level fixtures (in-memory SQLite, workflow tables only)
# ===========================================================================
_WF_TABLES = [
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
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=_WF_TABLES))
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as session:
        yield session
    await engine.dispose()


async def _seed_parallel(db, key: str):
    body = WorkflowDefinitionBody.model_validate(parallel_raw(key))
    await service.create_or_update_definition(db, body, publish=True, published_by="t")
    inst = await service.start_instance(db, key, {}, subject_ref=None)
    # Move onto the parallel step.
    inst = await service.perform_action(db, inst.id, U("sm", "study_manager"),
                                        "submit", {}, None)
    await db.commit()
    assert inst.current_step == "par"
    return inst


# ===========================================================================
# FIX 1 — locking + duplicate-action idempotency (service level)
# ===========================================================================
async def test_perform_action_reads_instance_with_row_lock(db, monkeypatch):
    """perform_action must request the instance row FOR UPDATE (the lock clause is
    a no-op on SQLite; this proves the code path asks for it everywhere)."""
    inst = await _seed_parallel(db, "HARD_LOCK")
    calls = []
    orig = AsyncSession.get

    async def spy(self, entity, ident, **kw):
        calls.append((getattr(entity, "__name__", str(entity)), kw.get("with_for_update")))
        return await orig(self, entity, ident, **kw)

    monkeypatch.setattr(AsyncSession, "get", spy)
    await service.perform_action(db, inst.id, U("l1", "legal"), "legal:approve", {}, None)
    assert ("WorkflowInstance", True) in calls, calls


async def test_duplicate_action_does_not_double_apply(db):
    """A double-fired vote: the second application fails cleanly and the ledger
    holds exactly one vote for that branch."""
    inst = await _seed_parallel(db, "HARD_DUP")
    inst_id = int(inst.id)
    await service.perform_action(db, inst_id, U("l1", "legal"), "legal:approve", {}, None)
    await db.commit()
    db.expunge_all()  # next reads hit the DB, not stale identity-map objects
    with pytest.raises(service.ServiceError, match="already been voted"):
        await service.perform_action(db, inst_id, U("l1", "legal"), "legal:approve", {}, None)
    await db.rollback()
    db.expunge_all()
    fresh = await service.get_instance(db, inst_id)
    votes = fresh.context["_branches"]["par"]
    assert list(votes.keys()) == ["legal"] and votes["legal"]["decision"] == "approve"
    assert fresh.current_step == "par"  # still waiting on financial — nothing lost


async def test_start_instance_strips_reserved_context(db):
    body = WorkflowDefinitionBody.model_validate(parallel_raw("HARD_STRIP"))
    await service.create_or_update_definition(db, body, publish=True, published_by="t")
    inst = await service.start_instance(
        db, "HARD_STRIP",
        {"_branches": {"par": {"legal": {"decision": "approve"}}}, "template_id": "tpl-1"},
    )
    await db.commit()
    assert "_branches" not in inst.context
    assert inst.context["template_id"] == "tpl-1"


# ===========================================================================
# FIX 3 — per-instance access (service predicate; the router maps False -> 404)
# ===========================================================================
async def test_access_strict_mode_default_deny(db):
    inst = await _seed_parallel(db, "HARD_ACC")

    # Named participant (branch assignee role) — allowed.
    assert await service.user_can_access_instance(db, inst, U("l1", "legal")) is True
    # Step assignee role — allowed.
    assert await service.user_can_access_instance(db, inst, U("sm", "study_manager")) is True
    # Unrelated authenticated user — DENIED.
    assert await service.user_can_access_instance(db, inst, U("stranger", "random")) is False
    # No identity — denied.
    assert await service.user_can_access_instance(db, inst, U("", "legal2")) is False


async def test_access_prior_actor_keeps_visibility(db):
    inst = await _seed_parallel(db, "HARD_ACT")
    await service.perform_action(db, inst.id, U("l9", "legal"), "legal:approve", {}, None)
    await db.commit()
    # l9 acted; even if their role were later renamed they keep read access.
    assert await service.user_can_access_instance(db, inst, U("l9")) is True


async def test_access_strict_denies_unrelated_user(db):
    # Open mode is gone: an unrelated authenticated user can NEVER read an instance
    # they are not party to.
    inst = await _seed_parallel(db, "HARD_OPEN")
    assert await service.user_can_access_instance(db, inst, U("anyone")) is False


# ===========================================================================
# FIX 1 — REAL concurrency on Postgres (skips when no local PG reachable)
# ===========================================================================
async def test_concurrent_votes_no_lost_update():
    """Two reviewers vote the same parallel step at the same moment. The row lock
    must serialize them: BOTH votes survive and quorum(all) advances the step.
    Before the fix the loser's read-modify-write erased the winner's vote."""
    from app.config import settings as app_settings

    url = app_settings.database_url
    if not url or not url.startswith(("postgresql", "postgres")):
        pytest.skip("no Postgres DATABASE_URL configured")
    # The .env URL uses the docker-compose hostname ("@postgres:"); when the test
    # runs on the host, fall back to the published localhost port.
    candidates = [url]
    if "@postgres:" in url:
        candidates.append(url.replace("@postgres:", "@localhost:"))
    engine = None
    last_exc: Exception | None = None
    for candidate in candidates:
        eng = create_async_engine(candidate, poolclass=NullPool)
        try:
            async with eng.begin() as conn:
                await conn.run_sync(
                    lambda c: Base.metadata.create_all(c, tables=_WF_TABLES, checkfirst=True))
            engine = eng
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            await eng.dispose()
    if engine is None:
        pytest.skip(f"Postgres not reachable: {last_exc}")

    key = f"HARD-CC-{uuid.uuid4().hex[:8]}"
    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    # Force the engine open-mode for this seeded flow regardless of env.
    body = WorkflowDefinitionBody.model_validate(parallel_raw(key))
    async with factory() as s:
        await service.create_or_update_definition(s, body, publish=True, published_by="t")
        inst = await service.start_instance(s, key, {})
        inst = await service.perform_action(s, inst.id, U("sm", "study_manager"),
                                            "submit", {}, None)
        inst_id = inst.id
        await s.commit()

    # Widen the race window: hold the row lock ~0.3s inside each action so the
    # two votes genuinely overlap. Without FOR UPDATE both would read the same
    # pre-vote context during the sleep and the second write would erase the first.
    orig_engine_for = service._engine_for

    async def slow_engine_for(db_, instance):
        await asyncio.sleep(0.3)
        return await orig_engine_for(db_, instance)

    service._engine_for = slow_engine_for
    try:
        async def vote(branch: str, role: str):
            async with factory() as s:
                await service.perform_action(s, inst_id, U(role, role),
                                             f"{branch}:approve", {}, None)
                await s.commit()

        await asyncio.gather(vote("legal", "legal"), vote("financial", "financial"))
    finally:
        service._engine_for = orig_engine_for

    async with factory() as s:
        fresh = await service.get_instance(s, inst_id)
        votes = fresh.context["_branches"]["par"]
        assert set(votes) == {"legal", "financial"}, f"lost a vote: {votes}"
        assert all(v["decision"] == "approve" for v in votes.values())
        assert fresh.current_step == "signature"  # quorum(all) advanced

        # Cleanup the rows this test created.
        ids = (await s.execute(
            select(WorkflowInstance.id).where(WorkflowInstance.definition_key == key)
        )).scalars().all()
        from sqlalchemy import delete
        await s.execute(delete(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id.in_(ids)))
        await s.execute(delete(WorkflowInstance).where(WorkflowInstance.id.in_(ids)))
        d = await s.scalar(select(WorkflowDefinition).where(WorkflowDefinition.key == key))
        if d:
            await s.execute(delete(WorkflowDefinitionVersion)
                            .where(WorkflowDefinitionVersion.definition_id == d.id))
            await s.execute(delete(WorkflowDefinition).where(WorkflowDefinition.id == d.id))
        await s.commit()
    await engine.dispose()

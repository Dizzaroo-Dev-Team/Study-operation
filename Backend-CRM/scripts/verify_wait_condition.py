"""
Verify the GENERAL wait_condition hold step (run in the backend container).

Proves the engine MECHANISM with a controllable TEST condition (so it doesn't depend on
seeding real budget data):
  1. A workflow at a wait_condition step PARKS when the condition is false — it does NOT
     advance, and exposes no human actions.
  2. AUTO-RESUME: once the condition flips true, the SWEEP (run_sweeps_once /
     run_pending_waits) releases the hold and the workflow advances automatically.
  3. The condition seam is pluggable (a test condition registers + dispatches; the real
     "budget_ready" is registered), and an UNKNOWN condition is rejected at publish time
     with a clear error (not a silent pass).

(The real budget_ready checker is data-based — true when the site's visit-matrix has
renderable rows via the cascade loader; that's covered separately.) Throwaway data.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows import waits  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402
from app.modules.workflows.service import ServiceError  # noqa: E402

# Controllable test condition — the sweep re-checks this; we flip it to prove resume.
_READY = {"v": False}


async def _test_cond(agreement, params, db):  # noqa: ARG001
    return _READY["v"]


def body(key, condition="verify_ready"):
    return {"key": key, "name": "Wait then done", "start_step": "draft", "context_schema": [],
            "steps": [
                {"id": "draft", "type": "form", "name": "Edit", "module": "document_create",
                 "assignee": {"type": "context", "value": "owner_user_id"},
                 "transitions": [{"id": "submit", "to": "hold", "label": "Submit", "action": "submit"}]},
                {"id": "hold", "type": "wait_condition", "name": "Wait",
                 "config": {"wait": {"condition": condition, "message": "Waiting…"}},
                 "transitions": [{"id": "ready", "to": "done", "label": "Ready", "action": "condition_met"}]},
                {"id": "done", "type": "terminal", "name": "Done", "transitions": []}]}


async def _make_agreement(db):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                   title="WAIT-COND-VERIFY", status=AgreementStatus.DRAFT, is_legacy="false", created_by="owner-1")
    db.add(ag)
    await db.flush()
    aid = str(ag.id)
    await db.commit()
    return aid


async def _current(db, aid):
    inst = await wf.find_instance_by_subject(db, aid)
    return inst.current_step, inst.status


async def _sweep(db):
    out = await wf.run_sweeps_once(db)
    await db.commit()
    return out


async def _cleanup(db, aid, key):
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": key})).fetchone()
    if d:
        await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
    await db.commit()


async def main():
    results = []
    waits.register_condition("verify_ready", _test_cond)
    assert "budget_ready" in waits.registered_conditions(), waits.registered_conditions()
    results.append(("Condition seam: pluggable; real 'budget_ready' registered",
                    f"{sorted(waits.registered_conditions())}"))

    async with AsyncSessionLocal() as db:
        aid = await _make_agreement(db)
        key = f"tpl:{aid}"
        try:
            _READY["v"] = False
            async with transactional(db):
                await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(body(key)),
                                                     publish=True, published_by="verify")
            async with transactional(db):
                await wf.ensure_instance(db, key, aid, {"agreement_id": aid})

            # owner submits draft -> parks at the wait step
            async with transactional(db):
                await wf.perform_action(db, (await wf.find_instance_by_subject(db, aid)).id,
                                        CurrentUser(id="owner-1", roles=[]), "submit", {})
            step, status = await _current(db, aid)
            assert step == "hold" and status == "active", (step, status)
            inst = await wf.find_instance_by_subject(db, aid)
            acts = await wf.available_actions(db, inst.id, CurrentUser(id="owner-1", roles=[]))
            assert acts == [], acts
            results.append(("Reaches wait step and PARKS (no human actions)", f"current={step}, actions={len(acts)}"))

            # condition false -> THIS instance holds (waits_advanced is a GLOBAL count
            # across all instances, so assert on this instance's own step).
            await _sweep(db)
            step, _ = await _current(db, aid)
            assert step == "hold", step
            results.append(("Condition FALSE -> this instance HOLDS (does not advance)", "current=hold"))

            # flip true -> next sweep auto-resumes THIS instance
            _READY["v"] = True
            await _sweep(db)
            step, status = await _current(db, aid)
            assert (step == "done" or status == "completed"), (step, status)
            results.append(("Condition TRUE -> sweep AUTO-RESUMES to next step",
                            f"current={step}, status={status}"))

            # unknown condition -> publish-time clear error
            erred = False
            try:
                async with transactional(db):
                    await wf.create_or_update_definition(
                        db, WorkflowDefinitionBody.model_validate(body(key + "x", condition="nope_not_registered")),
                        publish=True, published_by="verify")
            except ServiceError as e:
                erred = "unknown condition" in str(e)
            assert erred, "unknown condition must be rejected"
            results.append(("Unknown condition -> rejected at publish with a clear error", "ServiceError"))
        finally:
            await _cleanup(db, aid, key)
            await _cleanup(db, aid, key + "x")

    print("=" * 92)
    print("WAIT_CONDITION HOLD STEP — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

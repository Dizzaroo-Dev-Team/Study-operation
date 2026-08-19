"""CHECK 1 — GAP 1: CDA -> site-readiness bridge (end-to-end against the real DB).

Creates real fixtures (study/site/study_site/template/agreement/document + a NOT_STARTED
CDA_EXECUTION site step), drives a REAL engine instance (subject_ref = agreement.id) to
status="completed" via service.perform_action, then prints the two verification queries.
Positive = CDA agreement; Negative = CTA agreement (its site steps must NOT be touched).

NOTE ON FIDELITY: completion is driven through the engine's real perform_action path with
a minimal published definition (approval -> terminal). The bridge fires on ANY agreement-
subject instance reaching "completed", so this faithfully exercises the engine-completion
-> _maybe_finalize_agreement_subject -> complete_site_milestone_for_executed_agreement
wiring. It does NOT exercise the OTP/PDF signing UI that a real CDA uses to REACH
completion (that part needs the live UI).
"""
import asyncio
import uuid

from sqlalchemy import text

from app.db import AsyncSessionLocal
from app.models import (
    Study, Site, StudySite, StudyTemplate, Agreement, AgreementDocument,
    SiteWorkflowStep, WorkflowStepName, StepStatus, AgreementStatus, TemplateType,
)
from app.models.agreement import AgreementSignatureSource
from app.modules.workflows import service
from app.modules.workflows.schemas import WorkflowDefinitionBody, CurrentUser

MARK = "GAP1TEST"
USER = CurrentUser(id="gap1-tester", roles=["admin"])


def minimal_def(key):
    return {
        "key": key, "name": "GAP1 verify", "start_step": "s1",
        "steps": [
            {"id": "s1", "type": "approval", "name": "Approve",
             "assignee": {"type": "role", "value": "admin"},
             "transitions": [{"id": "finish", "to": "done", "label": "Finish", "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def make_agreement(db, ttype):
    study = Study(id=uuid.uuid4(), study_id=f"{MARK}-STU-{ttype.value}-{uuid.uuid4().hex[:6]}",
                  name=f"{MARK} Study {ttype.value}")
    site = Site(id=uuid.uuid4(), site_id=f"{MARK}-SITE-{ttype.value}-{uuid.uuid4().hex[:6]}",
                name=f"{MARK} Site {ttype.value}")
    db.add_all([study, site]); await db.flush()
    ss = StudySite(id=uuid.uuid4(), study_id=study.id, site_id=site.id)
    db.add(ss); await db.flush()
    tpl = StudyTemplate(id=uuid.uuid4(), study_id=study.id,
                        template_name=f"{MARK} {ttype.value} tpl", template_type=ttype, is_active="true")
    db.add(tpl); await db.flush()
    ag = Agreement(id=uuid.uuid4(), site_id=site.id, study_id=study.id, study_site_id=ss.id,
                   title=f"{MARK} {ttype.value} agreement", status=AgreementStatus.DRAFT,
                   is_legacy="false", signature_source=AgreementSignatureSource.INTERNAL,
                   agreement_type=ttype, created_by=USER.id)
    db.add(ag); await db.flush()
    doc = AgreementDocument(id=uuid.uuid4(), agreement_id=ag.id, version_number=1,
                            is_signed_version="false", created_from_template_id=tpl.id)
    db.add(doc); await db.flush()
    step = SiteWorkflowStep(id=uuid.uuid4(), study_site_id=ss.id,
                            step_name=WorkflowStepName.CDA_EXECUTION,
                            status=StepStatus.NOT_STARTED, step_data={})
    db.add(step); await db.flush()
    return ag, ss


async def drive_to_completed(db, key, agreement_id):
    body = WorkflowDefinitionBody.model_validate(minimal_def(key))
    await service.create_or_update_definition(db, body, publish=True, published_by=MARK)
    inst = await service.start_instance(db, key, {}, subject_ref=str(agreement_id))
    await db.flush()
    acts = await service.available_actions(db, inst.id, USER)
    if not acts:
        raise RuntimeError(f"no available actions for instance {inst.id} (auth?)")
    await service.perform_action(db, inst.id, USER, acts[0].transition_id, {}, None)
    await db.flush()
    return inst


async def show(db, agreement_id, study_site_id, label):
    print(f"\n----- {label} (agreement={agreement_id}) -----")
    r1 = await db.execute(text(
        "SELECT id, status, subject_ref, current_step FROM workflow_instances WHERE subject_ref = :sr"
    ), {"sr": str(agreement_id)})
    for row in r1.mappings():
        print("  instance:", dict(row))
    r2 = await db.execute(text(
        "SELECT step_name, status, completed_by, step_data FROM site_workflow_steps "
        "WHERE study_site_id = :ss AND step_name = 'cda_execution'"
    ), {"ss": str(study_site_id)})
    for row in r2.mappings():
        print("  site_step:", dict(row))


async def main():
    async with AsyncSessionLocal() as db:
        cda_ag, cda_ss = await make_agreement(db, TemplateType.CDA)
        cta_ag, cta_ss = await make_agreement(db, TemplateType.CTA)
        await db.commit()

        await drive_to_completed(db, f"{MARK}_CDA_{uuid.uuid4().hex[:6]}", cda_ag.id)
        await drive_to_completed(db, f"{MARK}_CTA_{uuid.uuid4().hex[:6]}", cta_ag.id)
        await db.commit()

        print("\n================ RESULTS ================")
        await show(db, cda_ag.id, cda_ss.id, "POSITIVE: CDA")
        await show(db, cta_ag.id, cta_ss.id, "NEGATIVE: CTA (site step must stay NOT_STARTED)")
        print("\n(reminder: fixtures are tagged 'GAP1TEST'; delete with the cleanup query if desired)")


if __name__ == "__main__":
    asyncio.run(main())

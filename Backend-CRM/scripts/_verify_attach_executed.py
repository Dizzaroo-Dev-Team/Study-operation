"""PHASE B — verify offline 'attach executed document' completes a CDA on the ENGINE and
fires the site-readiness bridge.

A CDA agreement runs on the engine and reaches its signing step. Instead of OTP signing,
the owner ATTACHES the externally/offline-signed PDF. attach_executed records it as the
signed version and completes the signing step, so the instance reaches terminal and the
completion bridge marks SiteWorkflowStep.CDA_EXECUTION COMPLETED — exactly as OTP signing
would. General (any agreement type); here CDA so we also see the site-readiness effect.
"""
import asyncio
import tempfile
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
from app.modules.agreements.services import unified_signing

MARK = "ATTACHEXEC"


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def cda_def(key):
    return {
        "key": key, "name": "Attach-executed verify", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "admin"},
             "transitions": [{"id": "submit", "to": "signing", "label": "Submit draft", "action": "submit"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Signatures",
             "config": {"signers": [{"id": "site", "name": "Site", "assignee": {"type": "role", "value": "site_director"}}]},
             "transitions": [
                 {"id": "done", "to": "end", "label": "All signed", "action": "all_signed"},
                 {"id": "dec", "to": "rej", "label": "Declined", "action": "signing_declined"}]},
            {"id": "end", "type": "terminal", "name": "Executed", "transitions": []},
            {"id": "rej", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }


async def main():
    async with AsyncSessionLocal() as db:
        study = Study(id=uuid.uuid4(), study_id=f"{MARK}-{uuid.uuid4().hex[:6]}", name=f"{MARK} study")
        site = Site(id=uuid.uuid4(), site_id=f"{MARK}-{uuid.uuid4().hex[:6]}", name=f"{MARK} site")
        db.add_all([study, site]); await db.flush()
        ss = StudySite(id=uuid.uuid4(), study_id=study.id, site_id=site.id)
        db.add(ss); await db.flush()
        tpl = StudyTemplate(id=uuid.uuid4(), study_id=study.id, template_name=f"{MARK} CDA tpl",
                            template_type=TemplateType.CDA, is_active="true")
        db.add(tpl); await db.flush()
        ag = Agreement(id=uuid.uuid4(), site_id=site.id, study_id=study.id, study_site_id=ss.id,
                       title=f"{MARK} CDA agreement", status=AgreementStatus.SENT_FOR_SIGNATURE,
                       is_legacy="false", signature_source=AgreementSignatureSource.INTERNAL,
                       agreement_type=TemplateType.CDA, created_by="owner")
        db.add(ag); await db.flush()
        db.add(AgreementDocument(id=uuid.uuid4(), agreement_id=ag.id, version_number=1,
                                 is_signed_version="false", created_from_template_id=tpl.id,
                                 document_file_path=await asyncio.to_thread(_tmpfile, ".docx", f"{MARK}_base_"),
                                 document_file_url=None))
        db.add(SiteWorkflowStep(id=uuid.uuid4(), study_site_id=ss.id,
                                step_name=WorkflowStepName.CDA_EXECUTION, status=StepStatus.NOT_STARTED, step_data={}))
        await db.flush()

        key = f"{MARK}_{uuid.uuid4().hex[:6]}"
        body = WorkflowDefinitionBody.model_validate(cda_def(key))
        await service.create_or_update_definition(db, body, publish=True, published_by=MARK)
        inst = await service.start_instance(db, key, {}, subject_ref=str(ag.id))
        await db.flush()
        await service.perform_action(db, inst.id, CurrentUser(id="owner", roles=["admin"]), "submit", {}, None)
        await db.flush()

        # OFFLINE attach: owner uploads the externally-signed CDA PDF.
        pdf_bytes = b"%PDF-1.4\n%executed CDA (signed offline)\n%%EOF\n"
        result = await unified_signing.attach_executed(db, ag, pdf_bytes, "executed_cda.pdf", by="owner")
        await db.commit()

        print("\n================ PHASE B — attach executed (offline) on the ENGINE ================")
        print(f"  attach_executed result: {result}")
        r1 = await db.execute(text("SELECT status, current_step FROM workflow_instances WHERE subject_ref=:s"), {"s": str(ag.id)})
        print(f"  instance: {dict(r1.mappings().first())}")
        r2 = await db.execute(text(
            "SELECT status, completed_by, step_data FROM site_workflow_steps WHERE study_site_id=:ss AND step_name='cda_execution'"),
            {"ss": str(ss.id)})
        srow = r2.mappings().first()
        print(f"  site_step: {dict(srow) if srow else None}")
        signed = (await db.execute(text(
            "SELECT count(*) c FROM agreement_documents WHERE agreement_id=:a AND is_signed_version='true'"), {"a": str(ag.id)})).scalar()
        print("\n================ VERDICT ================")
        print(f"  workflow executed (completed):        {result['engine']['status'] == 'completed'}  (EXPECT True)")
        print(f"  signed (executed) version recorded:   {signed > 0}  (EXPECT True)")
        print(f"  site CDA_EXECUTION COMPLETED by bridge: {bool(srow) and srow['status'] == 'completed' and srow['completed_by'] == 'engine'}  (EXPECT True)")


if __name__ == "__main__":
    asyncio.run(main())

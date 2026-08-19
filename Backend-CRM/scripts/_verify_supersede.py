"""Verify create_agreement supersede-in-place behaviour.

When a CTA already exists for a (study, site) and is already SIGNED, calling
create_agreement again with a template must NOT return the old signed document.
It must SUPERSEDE in place: keep the agreement row + full document history (incl.
the signed copy), clear the prior engine run, and lay down a FRESH unsigned latest
version from the chosen template, resetting status to DRAFT.

Run in the container:
  docker exec -i -e PYTHONUTF8=1 -e PYTHONPATH=/app backend-crm-backend-1 \
      python /app/scripts/_verify_supersede.py
"""
import asyncio
import tempfile
import uuid
from types import SimpleNamespace

from docx import Document as Docx
from sqlalchemy import select, text

from app.db import AsyncSessionLocal
from app.models import (
    Study, Site, StudySite, StudyTemplate, Agreement, AgreementDocument,
    TemplateType, AgreementStatus,
)
from app.models.site_status import SiteProfile
from app.modules.agreements.routes.crud import create_agreement
from app.modules.agreements.services import document_versioning as dv
from app.modules.workflows import service as wf
from app.modules.workflows.schemas import WorkflowDefinitionBody

MARK = "SUPSED"


def _make_template_docx() -> str:
    d = Docx()
    d.add_paragraph("Clinical Trial Agreement for {{site_name}}")
    d.add_paragraph("PI: {{pi_name}}   Signature: {{SIGNATURE_PI}}")
    p = tempfile.NamedTemporaryFile(suffix=".docx", delete=False)
    p.close()
    d.save(p.name)
    return p.name


def _wf_def(key):
    return {
        "key": key, "name": "supersede verify", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "admin"},
             "transitions": [{"id": "submit", "to": "end", "label": "Submit", "action": "submit"}]},
            {"id": "end", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def main():
    async with AsyncSessionLocal() as db:
        study = Study(id=uuid.uuid4(), study_id=f"{MARK}-{uuid.uuid4().hex[:6]}", name=f"{MARK} study")
        site = Site(id=uuid.uuid4(), site_id=f"{MARK}-{uuid.uuid4().hex[:6]}", name=f"{MARK} site")
        db.add_all([study, site]); await db.flush()
        db.add(StudySite(id=uuid.uuid4(), study_id=study.id, site_id=site.id))
        db.add(SiteProfile(id=uuid.uuid4(), site_id=site.id, site_name=f"{MARK} site", pi_name="Dr. Test"))
        tpl = StudyTemplate(
            id=uuid.uuid4(), study_id=study.id, template_name=f"{MARK} CTA tpl",
            template_type=TemplateType.CTA, is_active="true",
            template_file_path=_make_template_docx(), template_file_url=None,
        )
        db.add(tpl); await db.flush()
        await db.commit()

        ac = SimpleNamespace(title=f"{MARK} Agreement", status="DRAFT", template_id=tpl.id)

        # ---- 1st create: fresh agreement + v1 ----
        r1 = await create_agreement(str(site.id), ac, study_id=study.id, current_user=None, db=db)
        aid = uuid.UUID(str(r1["id"])) if isinstance(r1, dict) else r1.id
        docs1 = (await db.execute(select(AgreementDocument).where(AgreementDocument.agreement_id == aid))).scalars().all()
        print(f"  1st create -> agreement={aid}  versions={[d.version_number for d in docs1]}")

        # ---- simulate: agreement gets SIGNED, and an engine run exists ----
        latest = await dv.latest_document(db, aid)
        latest.is_signed_version = "true"  # pretend this version was executed
        ag = await db.get(Agreement, aid)
        ag.status = AgreementStatus.UNDER_REVIEW  # signed-but-under-review, exactly like prod case
        await db.flush()
        key = f"tpl:{tpl.id}"
        await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(_wf_def(key)),
                                             publish=True, published_by=MARK)
        inst = await wf.start_instance(db, key, {}, subject_ref=str(aid))
        await db.commit()
        inst_before = (await db.execute(text(
            "SELECT count(*) FROM workflow_instances WHERE subject_ref=:s"), {"s": str(aid)})).scalar()
        print(f"  signed v1; engine instances before 2nd create = {inst_before}")

        # ---- 2nd create with SAME template: must SUPERSEDE ----
        r2 = await create_agreement(str(site.id), ac, study_id=study.id, current_user=None, db=db)
        aid2 = uuid.UUID(str(r2["id"])) if isinstance(r2, dict) else r2.id

    # Re-read everything in a FRESH session so nothing is served from the identity map.
    async with AsyncSessionLocal() as db:
        docs2 = (await db.execute(select(AgreementDocument).where(AgreementDocument.agreement_id == aid2))).scalars().all()
        docs2_sorted = sorted(docs2, key=lambda d: d.version_number or 0)
        ag2 = await db.get(Agreement, aid2)
        latest2 = await dv.latest_document(db, aid2)
        inst_after = (await db.execute(text(
            "SELECT count(*) FROM workflow_instances WHERE subject_ref=:s"), {"s": str(aid)})).scalar()
        signed_kept = any(d.is_signed_version == "true" for d in docs2)

        print(f"\n  2nd create -> agreement={aid2}")
        print(f"     versions now = {[(d.version_number, d.is_signed_version) for d in docs2_sorted]}")
        print(f"     latest version = v{latest2.version_number} signed={latest2.is_signed_version}")
        print(f"     status = {ag2.status.value}   engine instances after = {inst_after}")

        print("\n================ VERDICT ================")
        print(f"  same agreement reused (not duplicated):     {aid2 == aid}  (EXPECT True)")
        print(f"  signed history KEPT:                        {signed_kept}  (EXPECT True)")
        print(f"  fresh LATEST version is unsigned:           {latest2.is_signed_version != 'true'}  (EXPECT True)")
        print(f"  latest version advanced past v1:            {(latest2.version_number or 0) > 1}  (EXPECT True)")
        print(f"  status reset to DRAFT:                      {ag2.status == AgreementStatus.DRAFT}  (EXPECT True)")
        print(f"  prior engine run cleared:                   {inst_after == 0}  (EXPECT True)")

    # ---- cleanup: remove ALL SUPSED-marked rows (covers any aborted prior run) ----
    async with AsyncSessionLocal() as c:
        await c.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT wi.id FROM workflow_instances wi WHERE wi.subject_ref IN (SELECT a.id::text FROM agreements a JOIN studies s ON a.study_id=s.id WHERE s.name LIKE 'SUPSED%'))"))
        await c.execute(text("DELETE FROM workflow_instances WHERE subject_ref IN (SELECT a.id::text FROM agreements a JOIN studies s ON a.study_id=s.id WHERE s.name LIKE 'SUPSED%')"))
        await c.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id IN (SELECT id FROM workflow_definitions WHERE key LIKE 'tpl:%' AND key IN (SELECT 'tpl:'||id::text FROM study_templates WHERE template_name LIKE 'SUPSED%'))"))
        await c.execute(text("DELETE FROM workflow_definitions WHERE key IN (SELECT 'tpl:'||id::text FROM study_templates WHERE template_name LIKE 'SUPSED%')"))
        await c.execute(text("DELETE FROM agreement_comments WHERE agreement_id IN (SELECT a.id FROM agreements a JOIN studies s ON a.study_id=s.id WHERE s.name LIKE 'SUPSED%')"))
        await c.execute(text("DELETE FROM agreement_documents WHERE agreement_id IN (SELECT a.id FROM agreements a JOIN studies s ON a.study_id=s.id WHERE s.name LIKE 'SUPSED%')"))
        await c.execute(text("DELETE FROM agreements WHERE study_id IN (SELECT id FROM studies WHERE name LIKE 'SUPSED%')"))
        await c.execute(text("DELETE FROM site_profiles WHERE site_id IN (SELECT id FROM sites WHERE name LIKE 'SUPSED%')"))
        await c.execute(text("DELETE FROM study_sites WHERE study_id IN (SELECT id FROM studies WHERE name LIKE 'SUPSED%')"))
        await c.execute(text("DELETE FROM study_templates WHERE template_name LIKE 'SUPSED%'"))
        await c.execute(text("DELETE FROM studies WHERE name LIKE 'SUPSED%'"))
        await c.execute(text("DELETE FROM sites WHERE name LIKE 'SUPSED%'"))
        await c.commit()
    print("\n  (cleanup done)")


if __name__ == "__main__":
    asyncio.run(main())

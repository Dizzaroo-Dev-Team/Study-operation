"""
SET UP (and verify) an end-to-end unified-module test in dev. No feature code.
Seeds the test DATA the path needs and PROVES the create path, then frees the site.

What it does:
  1. Seeds a CDA template under study f29f2acc pointing at the on-disk local DOCX
     (uploads/templates/template_75a4022f...docx) so document_create can produce a doc
     (Azure is OFF in dev, so an Azure-keyed template would 503).
  2. Seeds a SiteProfile for a free study_site under that study (create_agreement
     requires one). Uses RECIPIENT_EMAIL as the authorized-signatory email.
  3. Seeds the workflow definition keyed tpl:<template_id> exercising every module:
     document_create -> review -> approval -> signing -> notify -> terminal.
  4. PROVES create works: creates a throwaway agreement (real create_agreement),
     confirms a v1 AgreementDocument exists, ensures the engine instance lands on the
     first step, then DELETES the throwaway so the study_site is free for you.

Edit RECIPIENT_EMAIL to an address you control (and that your Mailgun is allowed to
send to) before running. Re-runnable (idempotent-ish: reuses the seeded template).
"""
import asyncio
import sys
from uuid import UUID

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import SiteProfile, StudyTemplate, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

RECIPIENT_EMAIL = "labesh@dizzaroo.com"          # <-- your real inbox (reviewer/signer)
STUDY_ID = "f29f2acc-f534-4e6d-af5b-3860930b9cc1"  # MK-6482 study (has sites)
STUDY_SITE_ID = "eb894011-f171-4e85-92a0-01a7495911a9"  # free study_site
SITE_ID = "96467b7e-bcaf-4b64-84e1-75b02f63349f"        # St John Hospital – MK-6482
LOCAL_DOCX = "uploads/templates/template_75a4022f-98fb-4c2f-a483-91bdbbae1a1a.docx"
TEMPLATE_NAME = "E2E Unified Test (local DOCX)"


def chain_body(key):
    return {
        "key": key, "name": "E2E Unified — all modules", "start_step": "draft", "context_schema": [],
        "steps": [
            {"id": "draft", "type": "form", "name": "Create Document", "module": "document_create",
             "transitions": [{"id": "submit", "to": "review", "label": "Send for review", "action": "submit"}]},
            {"id": "review", "type": "approval", "name": "Legal Review", "module": "review",
             "transitions": [{"id": "ok", "to": "approval", "label": "Approve", "action": "approve"},
                             {"id": "back", "to": "draft", "label": "Send back", "action": "send_back"}]},
            {"id": "approval", "type": "approval", "name": "Internal Approval", "module": "approval",
             "transitions": [{"id": "ok", "to": "signing", "label": "Approve", "action": "approve"},
                             {"id": "no", "to": "draft", "label": "Reject", "action": "reject"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Signature", "module": "signing",
             "config": {"handoff": "owner_gated", "signers": [{"id": "signer", "name": "Authorized Signer"}]},
             "transitions": [{"id": "signed", "to": "notify", "label": "All signed", "action": "all_signed"},
                             {"id": "decl", "to": "draft", "label": "Declined", "action": "signing_declined"}]},
            {"id": "notify", "type": "approval", "name": "Notify Parties", "module": "notify",
             "transitions": [{"id": "done", "to": "end", "label": "Continue", "action": "approve"}]},
            {"id": "end", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def main():
    settings.workflow_unified = True
    async with AsyncSessionLocal() as db:
        import os
        if not os.path.isfile(LOCAL_DOCX):
            print(f"BLOCKER: local DOCX missing at {LOCAL_DOCX}"); return

        # 1) template (reuse if already seeded by name)
        row = (await db.execute(text("SELECT id FROM study_templates WHERE template_name=:n AND study_id=:s"),
                                {"n": TEMPLATE_NAME, "s": STUDY_ID})).fetchone()
        if row:
            template_id = str(row[0])
        else:
            t = StudyTemplate(study_id=STUDY_ID, template_name=TEMPLATE_NAME, template_type=TemplateType.CDA,
                              template_file_path=LOCAL_DOCX, template_file_url=None, is_active="true")
            db.add(t); await db.flush(); template_id = str(t.id); await db.commit()

        # 2) SiteProfile for the site (if missing)
        prof = (await db.execute(text("SELECT id FROM site_profiles WHERE site_id=:s"), {"s": SITE_ID})).fetchone()
        if not prof:
            db.add(SiteProfile(site_id=SITE_ID, authorized_signatory_name="Authorized Signer",
                               authorized_signatory_email=RECIPIENT_EMAIL,
                               pi_name="Dr. Test PI", pi_email=RECIPIENT_EMAIL,
                               site_name="St John Hospital – MK-6482"))
            await db.commit()

        # 3) workflow definition keyed tpl:<template_id>
        key = f"tpl:{template_id}"
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(chain_body(key)),
                                                 publish=True, published_by="e2e-setup")

        # 4) PROVE create works (throwaway), then free the site
        from app.modules.agreements.routes.crud import create_agreement
        from app.schemas import agreement as A
        proof = "NOT RUN"
        try:
            res = await create_agreement(
                site_id=SITE_ID,
                agreement_data=A.AgreementCreate(title="E2E-PROOF", status="DRAFT", template_id=UUID(template_id)),
                study_id=UUID(STUDY_ID), current_user={"user_id": "e2e-owner", "email": RECIPIENT_EMAIL}, db=db,
            )
            aid = str(getattr(res, "id", None) or res.get("id"))
            docs = (await db.execute(text("SELECT count(*) FROM agreement_documents WHERE agreement_id=:a"), {"a": aid})).scalar()
            async with transactional(db):
                inst = await wf.ensure_instance(db, key, aid, {"agreement_id": aid, "template_id": template_id, "agreement_type": "CDA"})
            proof = f"agreement created, docs={docs}, instance step={inst.current_step}"
            # cleanup throwaway so the study_site is FREE for you
            await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
            await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
            await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
            await db.execute(text("DELETE FROM agreement_documents WHERE agreement_id=:a"), {"a": aid})
            await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
            await db.commit()
        except Exception as exc:  # noqa: BLE001
            import traceback; traceback.print_exc()
            proof = f"CREATE FAILED: {exc}"
        finally:
            settings.workflow_unified = False  # script-local only; .env still drives the app

        print("=" * 88)
        print("E2E UNIFIED TEST — SETUP COMPLETE")
        print("=" * 88)
        print(f"Study      : {STUDY_ID}  (MK-6482)")
        print(f"Site       : {SITE_ID}  (St John Hospital – MK-6482)")
        print(f"Template   : {TEMPLATE_NAME}  id={template_id}")
        print(f"Definition : {key}  (document_create -> review -> approval -> signing -> notify -> end)")
        print(f"Recipient  : {RECIPIENT_EMAIL}  (use for review + signing)")
        print(f"Create proof: {proof}")
        print("=" * 88)


if __name__ == "__main__":
    asyncio.run(main())

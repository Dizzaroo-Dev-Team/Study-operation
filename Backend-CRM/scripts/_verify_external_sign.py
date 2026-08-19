"""PHASE A — verify EXTERNAL signing runs on the ENGINE end-to-end.

An external signer holding an ENGINE-issued signing token (unified_signing.dispatch,
the same path the owner side + auto-dispatch use — NOT the legacy /cta/sign-external)
requests an OTP, submits it, the PDF is stamped at {{SIGNATURE_<ROLE>}}, the signature is
recorded, and the workflow ADVANCES. The OTP is normally emailed (hash-only in DB); here
we inject an OTP row with a known hash to simulate the emailed code, then drive the real
unified_signing.submit (verify + record_signature + advance).
"""
import asyncio
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models import (
    Study, Site, StudySite, Agreement, AgreementDocument, AgreementStatus, TemplateType,
    AgreementSigningToken, AgreementSigningOtp,
)
from app.models.agreement import AgreementSignatureSource
from app.modules.workflows import service
from app.modules.workflows.schemas import WorkflowDefinitionBody, CurrentUser
from app.modules.agreements.services import unified_signing

MARK = "EXTSIGN"
SIGNER_EMAIL = "external.signer@site.test"
OTP_PLAINTEXT = "123456"


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def _make_signable_pdf(path: str):
    """A 1-page PDF containing the literal {{SIGNATURE_PI}} placeholder so the engine's
    embed_signature_into_pdf can locate + stamp it (and not fail-loud)."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import letter
    c = canvas.Canvas(path, pagesize=letter)
    c.setFont("Helvetica", 12)
    c.drawString(72, 720, "CLINICAL TRIAL AGREEMENT — external-sign engine test")
    c.drawString(72, 680, "For Site Signature:")
    c.drawString(72, 660, "{{SIGNATURE_PI}}")
    c.save()


def signing_def(key):
    return {
        "key": key, "name": "External sign verify", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "admin"},
             "transitions": [{"id": "submit", "to": "signing", "label": "Submit draft", "action": "submit"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Signatures",
             "config": {"signers": [{"id": "pi", "name": "PI", "assignee": {"type": "role", "value": "pi"}}]},
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
        ag = Agreement(id=uuid.uuid4(), site_id=site.id, study_id=study.id, study_site_id=ss.id,
                       title=f"{MARK} agreement", status=AgreementStatus.SENT_FOR_SIGNATURE,
                       is_legacy="false", signature_source=AgreementSignatureSource.INTERNAL,
                       agreement_type=TemplateType.CTA, created_by="ext-tester")
        db.add(ag); await db.flush()

        pdf_path = await asyncio.to_thread(_tmpfile, ".pdf", "extsign_")
        _make_signable_pdf(pdf_path)
        db.add(AgreementDocument(id=uuid.uuid4(), agreement_id=ag.id, version_number=1,
                                 is_signed_version="false", document_file_path=pdf_path, document_file_url=None))
        await db.flush()

        key = f"{MARK}_{uuid.uuid4().hex[:6]}"
        body = WorkflowDefinitionBody.model_validate(signing_def(key))
        await service.create_or_update_definition(db, body, publish=True, published_by=MARK)
        inst = await service.start_instance(db, key, {}, subject_ref=str(ag.id))
        await db.flush()
        await service.perform_action(db, inst.id, CurrentUser(id="ext-tester", roles=["admin"]), "submit", {}, None)
        await db.flush()

        # ENGINE dispatch -> engine-issued token for the external signer (the migrated path).
        await unified_signing.dispatch(db, ag, {"pi": SIGNER_EMAIL}, created_by="ext-tester")
        await db.flush()
        token_row = await db.scalar(
            select(AgreementSigningToken).where(AgreementSigningToken.agreement_id == ag.id)
            .where(AgreementSigningToken.role == "pi").where(AgreementSigningToken.is_active == "true"))
        doc = (await db.execute(select(AgreementDocument).where(AgreementDocument.agreement_id == ag.id))).scalars().first()

        # Simulate the emailed OTP: insert a row with the known hash (request_otp emails it,
        # stores only the hash — so we inject the hash to drive the real submit() verify).
        db.add(AgreementSigningOtp(
            id=uuid.uuid4(), agreement_id=ag.id, document_id=doc.id, role="pi", email=SIGNER_EMAIL,
            otp_hash=unified_signing._hash_otp_value(OTP_PLAINTEXT),
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
            attempts=0, last_sent_at=datetime.now(timezone.utc), is_active="true"))
        await db.flush()

        before = inst.current_step
        # The REAL engine submit: verify OTP -> stamp PDF at {{SIGNATURE_PI}} -> record -> advance.
        result = await unified_signing.submit(
            db, str(ag.id), token_row.token, OTP_PLAINTEXT,
            signer_name="External Signer", signer_title="PI", meaning="Approved & Signed", request_ip="127.0.0.1")
        await db.flush()

        inst2 = await service.find_instance_by_subject(db, str(ag.id))
        signed_versions = (await db.execute(
            select(AgreementDocument).where(AgreementDocument.agreement_id == ag.id)
            .where(AgreementDocument.is_signed_version == "true"))).scalars().all()
        await db.commit()

        print("\n================ PHASE A — external sign on the ENGINE ================")
        print(f"  engine token issued to: {token_row.recipient_email}")
        print(f"  submit() result: {result}")
        print(f"  instance step: {before} -> {inst2.current_step} (status={inst2.status})")
        print(f"  signed document versions: {[d.version_number for d in signed_versions]}")
        print("\n================ VERDICT ================")
        print(f"  signature recorded:            {result.get('status') == 'signed'}  (EXPECT True)")
        print(f"  workflow advanced past signing: {inst2.current_step != 'signing'}  (EXPECT True)")
        print(f"  signed version produced:        {len(signed_versions) > 0}  (EXPECT True)")


if __name__ == "__main__":
    asyncio.run(main())

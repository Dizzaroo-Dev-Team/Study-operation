"""
Regression check for the SIGNING STEP-GATE bug (run in the backend container).

Bug: on a review->sign workflow, a signature could be driven through the unified
sign endpoints while the engine was still at the REVIEW step (the gate was on the UI
button, not the action). This proves the SERVER now refuses out-of-step signing and
records NOTHING, and that signing works normally once the engine reaches the signing
step. Throwaway data; cleaned up. Does not touch live CDA/CTA paths.
"""
import asyncio
import sys
import secrets
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import (  # noqa: E402
    Agreement, AgreementStatus, AgreementDocument, AgreementSigningOtp,
    AgreementSigningToken, TemplateType,
)
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.agreements.services import unified_signing as us  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def make_pdf(path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(72, 720, "Step-gate Test Agreement")
    c.showPage(); c.save()


def review_then_sign_body(key):
    """review (approval) -> sign (ordered_signing) -> end. send_back loops via draft."""
    return {"key": key, "name": "Review then Sign", "start_step": "review", "context_schema": [],
            "steps": [
                {"id": "review", "type": "approval", "name": "Legal Review", "module": "review",
                 "transitions": [{"id": "ok", "to": "sign", "label": "Approve", "action": "approve"},
                                 {"id": "back", "to": "draft", "label": "Send back", "action": "send_back"}]},
                {"id": "draft", "type": "form", "name": "Edit",
                 "transitions": [{"id": "s", "to": "review", "label": "Resubmit", "action": "submit"}]},
                {"id": "sign", "type": "ordered_signing", "name": "Signature", "module": "signing",
                 "config": {"handoff": "owner_gated", "signers": [{"id": "signer", "name": "Authorized Signer"}]},
                 "transitions": [{"id": "done", "to": "end", "label": "All signed", "action": "all_signed"}]},
                {"id": "end", "type": "terminal", "name": "Done", "transitions": []}]}


async def _agreement_with_pdf(db):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                   title="STEP-GATE", status=AgreementStatus.DRAFT, is_legacy="false", created_by="owner-1")
    db.add(ag); await db.flush()
    pdf = await asyncio.to_thread(_tmpfile, ".pdf")
    make_pdf(pdf)
    db.add(AgreementDocument(agreement_id=ag.id, version_number=1, document_file_path=pdf,
                             created_by="owner-1", is_signed_version="false"))
    await db.flush()
    aid = str(ag.id); await db.commit()
    return aid


async def _seed_token(db, aid, slot, email):
    tok = secrets.token_urlsafe(16)
    db.add(AgreementSigningToken(agreement_id=aid, token=tok, role=slot, recipient_email=email,
                                 expires_at=datetime.now(timezone.utc) + timedelta(days=1), is_active="true"))
    await db.commit()
    return tok


async def _seed_otp(db, aid, slot, email, otp_plain):
    doc = await us._latest_doc(db, aid)
    db.add(AgreementSigningOtp(agreement_id=aid, document_id=doc.id, role=slot, email=email,
                               otp_hash=us._hash_otp_value(otp_plain),
                               expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                               attempts=0, last_sent_at=datetime.now(timezone.utc), is_active="true"))
    await db.commit()


async def _counts(db, aid):
    sigs = (await db.execute(text("SELECT count(*) FROM agreement_internal_signatures WHERE agreement_id=:a"), {"a": aid})).scalar()
    signed = (await db.execute(text("SELECT count(*) FROM agreement_signed_documents WHERE agreement_id=:a"), {"a": aid})).scalar()
    docs = (await db.execute(text("SELECT count(*) FROM agreement_documents WHERE agreement_id=:a"), {"a": aid})).scalar()
    return sigs, signed, docs


async def _cleanup(db, aid, key):
    for t in ("agreement_internal_signatures", "agreement_signed_documents", "agreement_signing_otps",
              "agreement_signing_tokens", "agreement_documents", "agreement_comments"):
        await db.execute(text(f"DELETE FROM {t} WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM audit_logs WHERE target_id=:a"), {"a": aid})
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
    settings.workflow_unified = True
    async with AsyncSessionLocal() as db:
        aid = await _agreement_with_pdf(db)
        key = f"tpl:{aid}"
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(review_then_sign_body(key)),
                                                 publish=True, published_by="verify")
        async with transactional(db):
            await wf.ensure_instance(db, key, aid, {"agreement_id": aid})
        try:
            agreement = await db.get(Agreement, aid)
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "review", inst.current_step

            # A signing token + OTP EXIST (e.g. lingering / mis-issued) while at review.
            tok = await _seed_token(db, aid, "signer", "labesh@dizzaroo.com")
            await _seed_otp(db, aid, "signer", "labesh@dizzaroo.com", "111111")

            # (1) request-otp at REVIEW -> refused server-side
            try:
                await us.request_otp(db, aid, tok)
                raise AssertionError("request_otp must be refused at the review step")
            except HTTPException as e:
                assert e.status_code == 409, e.status_code
                await db.rollback()
            results.append(("request-otp at REVIEW is refused (409) — engine is the gate", "no code issued"))

            # (2) submit at REVIEW -> refused, and NOTHING recorded
            before = await _counts(db, aid)
            try:
                await us.submit(db, aid, tok, "111111", "Sneaky Signer", None, "I approve", "1.2.3.4")
                raise AssertionError("submit must be refused at the review step")
            except HTTPException as e:
                assert e.status_code == 409, e.status_code
                await db.rollback()
            after = await _counts(db, aid)
            assert after == before == (0, 0, 1), (before, after)
            results.append(("submit at REVIEW is refused (409) — nothing recorded",
                            f"sigs/signed/docs unchanged at {after}"))

            # (3) approve the review -> engine reaches the signing step
            inst = await wf.find_instance_by_subject(db, aid)
            async with transactional(db):
                await wf.perform_action(db, inst.id, CurrentUser(id="labesh@dizzaroo.com", roles=[]), "ok", {})
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "sign", inst.current_step

            # (4) now signing works (same token), and the signature IS recorded
            await db.execute(text("UPDATE agreement_signing_otps SET is_active='false' WHERE agreement_id=:a"), {"a": aid}); await db.commit()
            await _seed_otp(db, aid, "signer", "labesh@dizzaroo.com", "222222")
            rec = await us.submit(db, aid, tok, "222222", "Authorized Signer", "PI", "I approve and sign", "9.9.9.9")
            assert rec["status"] == "signed" and len(rec["document_hash"]) == 64, rec
            sigs, signed, docs = await _counts(db, aid)
            assert (sigs, signed) == (1, 1) and docs == 2, (sigs, signed, docs)
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "end" or inst.status == "completed", (inst.current_step, inst.status)
            results.append(("After review approved, signing at the SIGN step works",
                            f"recorded sigs={sigs}, signed_docs={signed}, engine={inst.current_step}/{inst.status}"))
        finally:
            await _cleanup(db, aid, key)
            settings.workflow_unified = False

    print("=" * 92)
    print("SIGNING STEP-GATE — REGRESSION VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

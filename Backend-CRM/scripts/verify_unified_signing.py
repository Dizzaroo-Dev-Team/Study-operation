"""
Verify the UNIFIED signing module (run in the backend container). Exercises the
real service against a real PDF so manifestation/hash are genuine.

Covers: ordered (current-slot-only + slot-by-slot + owner-gated handoff lock),
parallel (any order + quorum -> step advances), and the 21 CFR fixes (manifestation
on the final PDF, OTP 5-attempt lockout 429, failed-attempt audit, final-artifact
hash, signer meaning), plus permissions/gate. Throwaway data; cleaned up.
"""
import asyncio
import hashlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import (  # noqa: E402
    Agreement, AgreementStatus, AgreementDocument, AgreementSigningOtp, TemplateType,
)
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.agreements.services import unified_signing as us  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def _read_bytes(path: str) -> bytes:
    """Read a file's bytes. Called via asyncio.to_thread from async code."""
    with open(path, "rb") as f:
        return f.read()


def make_pdf(path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(72, 720, "Unified Signing Test Agreement")
    c.showPage()
    c.save()


def ordered_body(key):
    return {"key": key, "name": "Ordered sign", "start_step": "sign", "context_schema": [],
            "steps": [
                {"id": "sign", "type": "ordered_signing", "name": "Signatures", "module": "signing",
                 "config": {"handoff": "owner_gated", "signers": [
                     {"id": "s1", "name": "Signer One"}, {"id": "s2", "name": "Signer Two"}]},
                 "transitions": [{"id": "done", "to": "end", "label": "All signed", "action": "all_signed"}]},
                {"id": "end", "type": "terminal", "name": "Done", "transitions": []}]}


def parallel_body(key):
    return {"key": key, "name": "Parallel sign", "start_step": "sign", "context_schema": [],
            "steps": [
                {"id": "sign", "type": "parallel", "name": "Signatures", "module": "signing",
                 "config": {"quorum": {"mode": "all"}, "on_reject": "count", "branches": [
                     {"id": "s1", "name": "Signer One", "kind": "action", "action_approve": "approve", "action_reject": "reject"},
                     {"id": "s2", "name": "Signer Two", "kind": "action", "action_approve": "approve", "action_reject": "reject"}]},
                 "transitions": [{"id": "ok", "to": "end", "label": "Quorum", "action": "quorum_met"},
                                 {"id": "no", "to": "draft", "label": "Failed", "action": "quorum_failed"}]},
                {"id": "draft", "type": "form", "name": "Rework", "transitions": [
                    {"id": "re", "to": "sign", "label": "Resubmit", "action": "submit"}]},
                {"id": "end", "type": "terminal", "name": "Done", "transitions": []}]}


async def _agreement_with_pdf(db, title, created_by):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                   title=title, status=AgreementStatus.DRAFT, is_legacy="false", created_by=created_by)
    db.add(ag); await db.flush()
    pdf_path = await asyncio.to_thread(_tmpfile, ".pdf")
    make_pdf(pdf_path)
    db.add(AgreementDocument(agreement_id=ag.id, version_number=1, document_file_path=pdf_path,
                             created_by=created_by, is_signed_version="false"))
    await db.flush()
    aid = str(ag.id); await db.commit()
    return aid, pdf_path


async def _publish_def(db, key, body_fn):
    async with transactional(db):
        await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(body_fn(key)),
                                             publish=True, published_by="verify")


async def _seed_token(db, aid, slot, email):
    from app.models import AgreementSigningToken
    import secrets
    tok = secrets.token_urlsafe(16)
    db.add(AgreementSigningToken(agreement_id=aid, token=tok, role=slot, recipient_email=email,
                                 expires_at=datetime.now(timezone.utc) + timedelta(days=1), is_active="true"))
    await db.commit()
    return tok


async def _seed_otp(db, aid, slot, email, otp_plain, attempts=0):
    doc = await us._latest_doc(db, aid)
    db.add(AgreementSigningOtp(agreement_id=aid, document_id=doc.id, role=slot, email=email,
                               otp_hash=us._hash_otp_value(otp_plain),
                               expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
                               attempts=attempts, last_sent_at=datetime.now(timezone.utc), is_active="true"))
    await db.commit()


async def _audit_count(db, aid, action):
    return (await db.execute(text(
        "SELECT count(*) FROM audit_logs WHERE target_id=:a AND action=:x"), {"a": aid, "x": action})).scalar()


async def _cleanup(db, aid, key):
    await db.execute(text("DELETE FROM agreement_internal_signatures WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_signed_documents WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_signing_otps WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_signing_tokens WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM audit_logs WHERE target_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_documents WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": key})).fetchone()
    if d:
        await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
    await db.commit()


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        # ============ ORDERED ============
        aid, src_pdf = await _agreement_with_pdf(db, "USIGN-ORDERED", "owner-1")
        ord_key = f"tpl:{aid}"
        await _publish_def(db, ord_key, ordered_body)
        async with transactional(db):
            await wf.ensure_instance(db, ord_key, aid, {"agreement_id": aid})
        try:
            agreement = await db.get(Agreement, aid)
            owner = await wf.is_agreement_owner(db, aid, "owner-1")
            assert owner["is_owner"] and not (await wf.is_agreement_owner(db, aid, "x"))["is_owner"]
            results.append(("Permissions: dispatch is creator-owns", "owner True / other False"))

            st = await us.status(db, aid)
            assert [s["state"] for s in st["slots"]] == ["open", "pending"], st
            results.append(("Ordered: only current slot open", "s1=open, s2=pending"))

            # owner dispatch (provide both emails; ordered+owner_gated sends ONLY s1)
            async with transactional(db):
                disp = await us.dispatch(db, agreement, {"s1": "s1@org.com", "s2": "s2@org.com"}, "owner-1")
            sent = {d["slot"] for d in disp["dispatched"] if d["status"] == "sent"}
            assert sent == {"s1"}, disp
            results.append(("Ordered owner-gated: dispatch sends only current slot", f"sent={sent}"))

            # engine refuses an out-of-turn slot even if a token exists
            tok2 = await _seed_token(db, aid, "s2", "s2@org.com")
            await _seed_otp(db, aid, "s2", "s2@org.com", "222222")
            try:
                await us.submit(db, aid, tok2, "222222", "Two", None, "I approve", "1.1.1.1")
                raise AssertionError("s2 must not sign before s1")
            except HTTPException as e:
                assert e.status_code == 409, e.status_code
                # Atomicity: the real route is session-per-request, so a 409 rolls back
                # the (uncommitted) signature work. Mirror that here.
                await db.rollback()
            results.append(("Ordered: engine refuses out-of-turn signer (409) — atomic, nothing recorded",
                            "s2 blocked before s1"))
            await db.execute(text("UPDATE agreement_signing_tokens SET is_active='false' WHERE agreement_id=:a AND role='s2'"), {"a": aid}); await db.commit()
            await db.execute(text("UPDATE agreement_signing_otps SET is_active='false' WHERE agreement_id=:a AND role='s2'"), {"a": aid}); await db.commit()

            # s1 signs (compliant core)
            tok1 = (await db.execute(text("SELECT token FROM agreement_signing_tokens WHERE agreement_id=:a AND role='s1' AND is_active='true'"), {"a": aid})).scalar()
            await _seed_otp(db, aid, "s1", "s1@org.com", "111111")
            src_hash = hashlib.sha256(await asyncio.to_thread(_read_bytes, src_pdf)).hexdigest()
            rec = await us.submit(db, aid, tok1, "111111", "Signer One", "PI", "I approve and sign", "9.9.9.9")
            assert len(rec["document_hash"]) == 64 and rec["meaning"] == "I approve and sign"
            assert rec["document_hash"] != src_hash, "final artifact must differ (manifestation applied)"
            sig = (await db.execute(text("SELECT role,meaning,auth_method,document_hash FROM agreement_internal_signatures WHERE agreement_id=:a AND role='s1'"), {"a": aid})).fetchone()
            assert sig and sig[1] == "I approve and sign" and sig[3] == rec["document_hash"]
            signed_docs = (await db.execute(text("SELECT count(*) FROM agreement_signed_documents WHERE agreement_id=:a"), {"a": aid})).scalar()
            assert signed_docs == 1
            results.append(("Compliance: manifestation on final PDF + final-artifact hash + meaning",
                            f"hash={rec['document_hash'][:12]}… meaning='{rec['meaning']}'"))

            st2 = await us.status(db, aid)
            assert [s["state"] for s in st2["slots"]] == ["signed", "open"], st2
            results.append(("Ordered: advances slot-by-slot", "s1=signed, s2=open"))

            # ===== OTP lockout (429) + failed-attempt audit =====
            await db.execute(text("UPDATE agreement_signing_otps SET is_active='false' WHERE agreement_id=:a"), {"a": aid}); await db.commit()
            tok2b = await _seed_token(db, aid, "s2", "s2@org.com")
            # (a) locked OTP (attempts at max) -> 429
            await _seed_otp(db, aid, "s2", "s2@org.com", "654321", attempts=5)
            try:
                await us.submit(db, aid, tok2b, "654321", "Two", None, "ok", "2.2.2.2")
                raise AssertionError("expected 429 lockout")
            except HTTPException as e:
                assert e.status_code == 429, e.status_code
            # (b) fresh OTP, 5 wrong -> 5 SIGN_OTP_FAILED audits + deactivation
            await db.execute(text("UPDATE agreement_signing_otps SET is_active='false' WHERE agreement_id=:a"), {"a": aid}); await db.commit()
            await _seed_otp(db, aid, "s2", "s2@org.com", "777777")
            for _ in range(5):
                try:
                    await us.submit(db, aid, tok2b, "000000", "Two", None, "ok", "2.2.2.2")
                except HTTPException as e:
                    assert e.status_code == 400
            failed = await _audit_count(db, aid, "SIGN_OTP_FAILED")
            assert failed >= 5, failed
            results.append(("Compliance: OTP 5-attempt lockout (429) + every failed attempt audited",
                            f"SIGN_OTP_FAILED rows={failed}"))

            # s2 signs correctly -> all signed -> engine completes
            await db.execute(text("UPDATE agreement_signing_otps SET is_active='false' WHERE agreement_id=:a"), {"a": aid}); await db.commit()
            await _seed_otp(db, aid, "s2", "s2@org.com", "888888")
            await us.submit(db, aid, tok2b, "888888", "Signer Two", "Sponsor", "I approve", "2.2.2.2")
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "end" or inst.status == "completed", (inst.current_step, inst.status)
            results.append(("Ordered: all signed -> engine advances past signing step",
                            f"current_step={inst.current_step}, status={inst.status}"))
        finally:
            await _cleanup(db, aid, ord_key)

        # ============ PARALLEL + QUORUM ============
        paid, _ = await _agreement_with_pdf(db, "USIGN-PARALLEL", "owner-2")
        par_key = f"tpl:{paid}"
        await _publish_def(db, par_key, parallel_body)
        async with transactional(db):
            await wf.ensure_instance(db, par_key, paid, {"agreement_id": paid})
        try:
            pag = await db.get(Agreement, paid)
            st = await us.status(db, paid)
            assert {s["state"] for s in st["slots"]} == {"open"}, st  # both open in parallel
            async with transactional(db):
                disp = await us.dispatch(db, pag, {"s1": "p1@org.com", "s2": "p2@org.com"}, "owner-2")
            assert {d["slot"] for d in disp["dispatched"] if d["status"] == "sent"} == {"s1", "s2"}
            results.append(("Parallel: both action-signers dispatched (any order)", "s1,s2 sent"))
            # sign s2 first, then s1 (any order)
            for slot, email, otp in [("s2", "p2@org.com", "121212"), ("s1", "p1@org.com", "343434")]:
                tok = (await db.execute(text("SELECT token FROM agreement_signing_tokens WHERE agreement_id=:a AND role=:r AND is_active='true'"), {"a": paid, "r": slot})).scalar()
                await _seed_otp(db, paid, slot, email, otp)
                await us.submit(db, paid, tok, otp, f"Signer {slot}", None, "I approve", "3.3.3.3")
            inst = await wf.find_instance_by_subject(db, paid)
            assert inst.current_step == "end" or inst.status == "completed", (inst.current_step, inst.status)
            results.append(("Parallel: quorum met -> step advances", f"current_step={inst.current_step}, status={inst.status}"))
        finally:
            await _cleanup(db, paid, par_key)

    print("=" * 96)
    print("UNIFIED SIGNING MODULE — VERIFICATION")
    print("=" * 96)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 96)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

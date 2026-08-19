"""
Verification for the SENT_FOR_SIGNATURE lock widening (Option 1) — run in the
backend container. Covers the previously-broken CTA path and proves CDA/illegal
transitions are unaffected. Workflow flags forced OFF so this isolates the lock
(no engine bridge involvement). Throwaway agreements on free study_sites; cleaned up.

Checks:
  a) CTA at SENT_FOR_SIGNATURE + both external signers (pi + designated) recorded
     -> SENT_FOR_SIGNATURE -> AWAITING_SPONSOR_SIGNATURE WITHOUT raising, and both
     signatures persist (not rolled back).
  b) sponsor finalize: AWAITING_SPONSOR_SIGNATURE -> EXECUTED still works.
  c) CDA: SENT_FOR_SIGNATURE -> EXECUTED still works exactly as before.
  d) a genuinely illegal transition (SENT_FOR_SIGNATURE -> READY_FOR_SIGNATURE,
     not in ALLOWED_TRANSITIONS) is still blocked.

Note: agreement/document ids are captured as plain strings up front — never access
expired ORM attributes after change_agreement_status's internal commits in a script.
"""
import asyncio
import sys
import tempfile

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementDocument, AgreementStatus, TemplateType  # noqa: E402
from app.modules.agreements.services.agreement_service import change_agreement_status  # noqa: E402


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


async def _make(db, atype, title):
    """Create a throwaway agreement + document. Returns (agreement_id, document_id)
    as plain strings, captured before any commit expires the ORM objects."""
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type=:t AND study_site_id IS NOT NULL) LIMIT 1"
    ), {"t": atype})).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                   agreement_type=TemplateType(atype), title=title,
                   status=AgreementStatus.DRAFT, is_legacy="false")
    db.add(ag); await db.flush()
    doc = AgreementDocument(agreement_id=ag.id, version_number=1,
                            document_file_path=await asyncio.to_thread(_tmpfile, ".docx"),
                            document_file_url=None, document_html="", is_signed_version="false")
    db.add(doc); await db.flush()
    aid, did = str(ag.id), str(doc.id)
    await db.commit()
    return aid, did


async def _drive(db, aid, statuses):
    for st in statuses:
        await change_agreement_status(db, aid, st, "verify")


async def _status(db, aid):
    return (await db.execute(text("SELECT status FROM agreements WHERE id=:a"), {"a": aid})).scalar()


async def _sig_count(db, aid):
    return (await db.execute(text("SELECT count(*) FROM agreement_internal_signatures WHERE agreement_id=:a"),
                             {"a": aid})).scalar()


async def _cleanup(db, aid):
    for t in ("agreement_internal_signatures", "agreement_documents", "agreement_comments"):
        await db.execute(text(f"DELETE FROM {t} WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


async def main():
    settings.workflow_drives_cta = False   # isolate the lock; no engine bridge
    settings.workflow_drives_cda = False
    results = []
    async with AsyncSessionLocal() as db:
        # ---- a) + b) CTA broken path now works ----
        aid, did = await _make(db, "CTA", "VERIFY-LOCK-CTA")
        try:
            await _drive(db, aid, [AgreementStatus.AWAITING_INTERNAL_REVIEW,
                                   AgreementStatus.INTERNAL_REVIEW_APPROVED,
                                   AgreementStatus.SENT_FOR_SIGNATURE])
            # both external signers complete (as cta_sign_submit records them). Raw INSERT.
            for role in ("pi", "designated"):
                await db.execute(text(
                    "INSERT INTO agreement_internal_signatures "
                    "(id, agreement_id, document_id, role, email, meaning, auth_method, version, ip_address, document_hash) "
                    "VALUES (gen_random_uuid(), :aid, :did, :role, :email, 'Signed & Approved', 'otp', 1, NULL, :h)"),
                    {"aid": aid, "did": did, "role": role, "email": f"{role}@x.com", "h": "hash-" + role})
            await db.commit()
            # the previously-forbidden transition — must NOT raise now
            await change_agreement_status(db, aid, AgreementStatus.AWAITING_SPONSOR_SIGNATURE, "system")
            st = await _status(db, aid)
            sigs = await _sig_count(db, aid)
            assert st == "AWAITING_SPONSOR_SIGNATURE", st
            assert sigs == 2, f"signatures rolled back? count={sigs}"
            results.append(("a) CTA both-signed -> AWAITING_SPONSOR (no raise; sigs persisted)",
                            f"status={st}, signatures={sigs}"))

            # b) sponsor finalize
            await change_agreement_status(db, aid, AgreementStatus.EXECUTED, "system")
            assert (await _status(db, aid)) == "EXECUTED"
            results.append(("b) sponsor finalize AWAITING_SPONSOR -> EXECUTED", "status=EXECUTED"))
        finally:
            await _cleanup(db, aid)

        # ---- c) CDA unchanged: SENT -> EXECUTED ----
        aid2, _ = await _make(db, "CDA", "VERIFY-LOCK-CDA")
        try:
            await _drive(db, aid2, [AgreementStatus.UNDER_REVIEW, AgreementStatus.READY_FOR_SIGNATURE,
                                    AgreementStatus.SENT_FOR_SIGNATURE, AgreementStatus.EXECUTED])
            assert (await _status(db, aid2)) == "EXECUTED"
            results.append(("c) CDA SENT_FOR_SIGNATURE -> EXECUTED (unchanged)", "status=EXECUTED"))
        finally:
            await _cleanup(db, aid2)

        # ---- d) illegal transition still blocked ----
        aid3, _ = await _make(db, "CDA", "VERIFY-LOCK-ILLEGAL")
        try:
            await _drive(db, aid3, [AgreementStatus.UNDER_REVIEW, AgreementStatus.READY_FOR_SIGNATURE,
                                    AgreementStatus.SENT_FOR_SIGNATURE])
            raised = False
            try:
                await change_agreement_status(db, aid3, AgreementStatus.READY_FOR_SIGNATURE, "verify")
            except ValueError as e:
                raised, msg = True, str(e)
            assert raised, "illegal SENT_FOR_SIGNATURE -> READY_FOR_SIGNATURE was NOT blocked"
            results.append(("d) illegal SENT -> READY_FOR_SIGNATURE still blocked", f"ValueError: {msg[:55]}..."))
        finally:
            await _cleanup(db, aid3)

    print("=" * 78)
    print("LOCK-WIDENING VERIFICATION (Option 1)")
    print("=" * 78)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 78)
    print(f"{len(results)}/4 checks passed")


if __name__ == "__main__":
    asyncio.run(main())

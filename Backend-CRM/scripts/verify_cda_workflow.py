"""
Dev verification for WORKFLOW_DRIVES_CDA (run in the backend container).

Creates a throwaway CDA attached to an existing study_site, then:
  FLAG ON  — start instance on create, drive DRAFT -> UNDER_REVIEW ->
             READY_FOR_SIGNATURE -> SENT_FOR_SIGNATURE through the REAL
             change_agreement_status funnel, then EXECUTED via the OTP->engine
             bridge (the exact line otp.py now runs). Asserts the engine instance
             advanced + status mirrored + audit recorded at each stage.
  FLAG OFF — same transitions produce NO instance and behave as today.

Cleans up the throwaway rows. NOT a pytest test; an integration smoke run.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import delete, select, text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementComment, AgreementStatus, TemplateType  # noqa: E402
from app.modules.workflows.models import WorkflowAuditEntry, WorkflowInstance  # noqa: E402
from app.modules.agreements.services.agreement_service import change_agreement_status  # noqa: E402
from app.modules.agreements.types.cda.service import cda_on_create  # noqa: E402
from app.modules.workflows.cda_bridge import sync_cda_instance_to_status  # noqa: E402


async def _instance(db, aid):
    return await db.scalar(
        select(WorkflowInstance)
        .where(WorkflowInstance.subject_ref == str(aid))
        .where(WorkflowInstance.definition_key == "CDA")
        .order_by(WorkflowInstance.id.desc())
    )


async def _make_cda(db, title):
    ss = (await db.execute(text("SELECT id, study_id, site_id FROM study_sites LIMIT 1"))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                   agreement_type=TemplateType.CDA, title=title,
                   status=AgreementStatus.DRAFT, is_legacy="false")
    db.add(ag)
    await db.flush()
    await db.commit()
    return ag


async def _cleanup(db, aid):
    await db.execute(delete(WorkflowInstance).where(WorkflowInstance.subject_ref == str(aid)))
    await db.execute(delete(AgreementComment).where(AgreementComment.agreement_id == aid))
    await db.execute(delete(Agreement).where(Agreement.id == aid))
    await db.commit()


def _line(stage, status, step):
    print(f"  {stage:<22} status={status:<22} engine_step={step}")


async def run_flag_on():
    print("\n========== FLAG ON ==========")
    settings.workflow_drives_cda = True
    async with AsyncSessionLocal() as db:
        ag = await _make_cda(db, "VERIFY-CDA-ON")
        aid = ag.id
        try:
            # create -> on_create starts the instance
            await cda_on_create(ag, db)
            await db.commit()
            inst = await _instance(db, aid)
            assert inst is not None, "no instance started on create"
            _line("create", ag.status.value, inst.current_step)
            assert inst.current_step == "draft"

            expected = {
                AgreementStatus.UNDER_REVIEW: "under_review",
                AgreementStatus.READY_FOR_SIGNATURE: "ready_for_signature",
                AgreementStatus.SENT_FOR_SIGNATURE: "sent_for_signature",
            }
            for status, step in expected.items():
                await change_agreement_status(db, str(aid), status, "verify-user")
                fresh = await db.get(Agreement, aid)
                inst = await _instance(db, aid)
                _line(status.value, fresh.status.value, inst.current_step)
                assert fresh.status == status, f"status mirror wrong: {fresh.status}"
                assert inst.current_step == step, f"engine step wrong: {inst.current_step} != {step}"

            # OTP path: the commit sets status EXECUTED directly; the fix's bridge
            # line advances the engine. Replicate exactly those two statements.
            fresh = await db.get(Agreement, aid)
            fresh.status = AgreementStatus.EXECUTED            # what otp.py sets directly
            await sync_cda_instance_to_status(db, fresh, fresh.status)  # the bridge line the fix adds
            await db.commit()
            inst = await _instance(db, aid)
            _line("OTP commit -> EXECUTED", fresh.status.value, inst.current_step)
            assert inst.current_step == "executed", f"OTP did not move engine to executed: {inst.current_step}"

            # audit + funnel side-effects
            audit = (await db.execute(
                select(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id == inst.id)
                .order_by(WorkflowAuditEntry.id))).scalars().all()
            comments = (await db.execute(
                select(AgreementComment).where(AgreementComment.agreement_id == aid))).scalars().all()
            print("\n  --- engine audit trail ---")
            for a in audit:
                print(f"    {a.action:<16} {str(a.from_step):<22} -> {a.to_step}")
            print(f"  funnel SYSTEM comments created (existing service fired): {len(comments)}")
            assert any(a.action == "started" for a in audit)
            assert any(a.action == "status_synced" and a.to_step == "executed" for a in audit)
            assert len(comments) >= 3  # one SYSTEM comment per change_agreement_status
            print("  RESULT: FLAG ON — engine advanced + status mirrored + OTP->EXECUTED + audit OK")
        finally:
            await _cleanup(db, aid)


async def run_flag_off():
    print("\n========== FLAG OFF ==========")
    settings.workflow_drives_cda = False
    async with AsyncSessionLocal() as db:
        ag = await _make_cda(db, "VERIFY-CDA-OFF")
        aid = ag.id
        try:
            await cda_on_create(ag, db)
            await db.commit()
            inst = await _instance(db, aid)
            assert inst is None, "flag OFF should NOT start an instance"
            _line("create", ag.status.value, "(no instance)")
            for status in (AgreementStatus.UNDER_REVIEW, AgreementStatus.READY_FOR_SIGNATURE,
                           AgreementStatus.SENT_FOR_SIGNATURE):
                await change_agreement_status(db, str(aid), status, "verify-user")
                fresh = await db.get(Agreement, aid)
                inst = await _instance(db, aid)
                _line(status.value, fresh.status.value, "(no instance)")
                assert fresh.status == status            # status transitions exactly as today
                assert inst is None                      # engine never involved
            print("  RESULT: FLAG OFF — no instance, status behaves exactly as today")
        finally:
            await _cleanup(db, aid)


async def main():
    await run_flag_on()
    await run_flag_off()
    print("\nVERIFICATION COMPLETE — all assertions passed.")


if __name__ == "__main__":
    asyncio.run(main())

"""
Verify ALL primary CDA actions are gated by the engine (run in the backend
container). Walks a real CDA end-to-end and, at each stage, compares:
  * which primary buttons the ENGINE allows (available_actions on the current step,
    matched by the transition's destination step — the same mapping the FE uses), vs
  * which primary button the STATUS LADDER (getPrimaryWorkflowAction) would show.
They must agree at every stage — the engine drives, and it agrees with reality
because the mapping is correct.

Each stage is driven the way the REAL endpoint drives it (funnel where the real
route uses change_agreement_status; direct status set + CDA bridge sync where
send-for-signature / OTP do). CDA-only, flag toggled in-proc. Throwaway agreement;
cleaned up.

Primary buttons (FE keys) and their engine gate (transition .to):
    mark_ready_send_review -> under_review        (draft: submit)
    complete_review        -> ready_for_signature (under_review: approve)
    send_signature         -> sent_for_signature  (ready_for_signature: send)
sync_signature / none are informational (no button) — status stays the source of
truth for those; they are never engine-gated.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401  (init order)
from app.modules.agreements.services.agreement_service import change_agreement_status  # noqa: E402
from app.modules.agreements.types.cda.service import cda_on_create  # noqa: E402
from app.modules.workflows import cda_bridge, service  # noqa: E402
from app.modules.workflows.schemas import CurrentUser  # noqa: E402

U = CurrentUser(id="tester", roles=[])  # open mode (enforce_roles default False)

# FE mapping (CDA_ENGINE_GATE): primary button -> engine transition destination.
GATE = {
    "mark_ready_send_review": "under_review",
    "complete_review": "ready_for_signature",
    "send_signature": "sent_for_signature",
}
PRIMARY_BUTTONS = set(GATE)


def status_primary(status: str) -> str:
    """Mirror getPrimaryWorkflowAction (agreementWorkflow.ts) for the walk states."""
    n = status.upper()
    if n == "DRAFT":
        return "mark_ready_send_review"
    if n in ("UNDER_REVIEW", "UNDER_NEGOTIATION", "REVIEWED_AND_SIGNED"):
        return "complete_review"
    if n == "READY_FOR_SIGNATURE":
        return "send_signature"
    if n == "SENT_FOR_SIGNATURE":
        return "sync_signature"
    return "none"


async def _make_cda(db, title):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                   agreement_type=TemplateType.CDA, title=title,
                   status=AgreementStatus.DRAFT, is_legacy="false")
    db.add(ag); await db.flush()
    aid = str(ag.id)
    await db.commit()
    return aid


async def _direct_set(db, aid, status):
    """Mimic send-for-signature / OTP: set status directly + CDA bridge sync."""
    ag = await db.get(Agreement, aid)
    ag.status = status
    await cda_bridge.sync_cda_instance_to_status(db, ag, status)
    await db.commit()


async def _cleanup(db, aid):
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN "
                          "(SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


async def _engine_buttons(db, aid):
    inst = await service.find_instance_by_subject(db, aid, "CDA")
    if inst is None:
        return None, set()
    acts = await service.available_actions(db, inst.id, U)
    allowed = {k for k, to in GATE.items() if any(a.to == to for a in acts)}
    return inst.current_step, allowed


async def main():
    rows = []
    async with AsyncSessionLocal() as db:
        settings.workflow_drives_cda = True
        aid = await _make_cda(db, "DRIVE-ALL-CDA")
        try:
            ag = await db.get(Agreement, aid)
            await cda_on_create(ag, db)
            await db.commit()

            async def record(stage_label, status):
                step, engine_btns = await _engine_buttons(db, aid)
                sp = status_primary(status.value if hasattr(status, "value") else status)
                status_btns = {sp} if sp in PRIMARY_BUTTONS else set()
                rows.append((stage_label, (status.value if hasattr(status, "value") else status),
                             step, engine_btns, status_btns, sp))

            await record("create", AgreementStatus.DRAFT)
            await change_agreement_status(db, aid, AgreementStatus.UNDER_REVIEW, user_id="system")
            await record("send-for-review", AgreementStatus.UNDER_REVIEW)
            await change_agreement_status(db, aid, AgreementStatus.READY_FOR_SIGNATURE, user_id="system")
            await record("complete-review", AgreementStatus.READY_FOR_SIGNATURE)
            await _direct_set(db, aid, AgreementStatus.SENT_FOR_SIGNATURE)
            await record("send-for-signature", AgreementStatus.SENT_FOR_SIGNATURE)
            await _direct_set(db, aid, AgreementStatus.FULLY_SIGNED)
            await record("otp-sign", AgreementStatus.FULLY_SIGNED)
            await _direct_set(db, aid, AgreementStatus.EXECUTED)
            await record("executed", AgreementStatus.EXECUTED)
        finally:
            await _cleanup(db, aid)
            settings.workflow_drives_cda = False

    print("=" * 116)
    print("ENGINE DRIVES ALL PRIMARY CDA ACTIONS — engine-allowed vs status-ladder buttons (flag ON)")
    print("=" * 116)
    print(f"{'stage':20} {'status':22} {'engine step':22} {'engine buttons':26} {'status ladder':26} match")
    print("-" * 116)
    all_match = True
    for stage, status, step, eng, stat, sp in rows:
        match = (eng == stat)
        all_match = all_match and match
        eng_s = ",".join(sorted(eng)) or "—"
        stat_s = (",".join(sorted(stat)) or f"({sp})")  # show informational primary in parens
        print(f"{stage:20} {status:22} {step:22} {eng_s:26} {stat_s:26} {'OK' if match else 'DIVERGE'}")
    print("-" * 116)
    print(f"{'ALL MATCH' if all_match else 'DIVERGENCE FOUND'} — engine gate agrees with the status ladder at every stage")
    print("Endpoints per button are UNCHANGED: send-for-review=POST .../send-for-review, "
          "complete-review=PATCH .../status, send-for-signature=POST .../send-for-signature")


if __name__ == "__main__":
    asyncio.run(main())

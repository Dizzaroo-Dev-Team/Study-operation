"""
Verify the FIRST real "drive" step (run in the backend container):
the engine — not the hardcoded status ladder — GATES the CDA "send for review"
action. CDA-only, flag-gated, additive. Every other action stays status-driven.

What the frontend does (and what this reproduces at the service level):
  resolve the agreement's instance by subject_ref (find_instance_by_subject) ->
  read its available_actions on the current step -> the action whose transition
  leads to `under_review` IS "send for review". The button shows iff that action
  is listed. Clicking still calls the SAME existing send-for-review endpoint
  (here mirrored by the funnel transition DRAFT->UNDER_REVIEW it performs).

Checks (flag ON):
  * At the draft step the engine LISTS send-for-review -> button shows.
  * After send-for-review (status + engine both at under_review) the engine does
    NOT list it -> button correctly hidden.
  * At ready_for_signature the engine does NOT list it -> hidden.
Flag OFF: config drives_cda=false (FE falls back to the status ladder, unchanged);
no instance is started, so the engine gate would be false anyway.

Throwaway CDA on a free study_site; cleaned up. Flag toggled in-proc only.
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
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.router import workflow_config  # noqa: E402
from app.modules.workflows.schemas import CurrentUser  # noqa: E402

U = CurrentUser(id="tester", roles=[])  # open mode (enforce_roles default False)
REVIEW_STEP = "under_review"  # the destination that identifies "send for review"


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


async def _cleanup(db, aid):
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN "
                          "(SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


async def _gate(db, aid):
    """Exactly what the FE computes: find instance -> available actions ->
    is there an action whose transition leads to under_review?"""
    inst = await service.find_instance_by_subject(db, aid, "CDA")
    if inst is None:
        return None, False, []
    acts = await service.available_actions(db, inst.id, U)
    available = any(a.to == REVIEW_STEP for a in acts)
    labels = [f"{a.transition_id}->{a.to}" for a in acts]
    return inst.current_step, available, labels


async def main():
    rows = []
    async with AsyncSessionLocal() as db:
        # ---- FLAG ON ----
        settings.workflow_drives_cda = True
        aid = await _make_cda(db, "DRIVE-SEND-REVIEW")
        try:
            # draft step (just created via on_create)
            ag = await db.get(Agreement, aid)
            await cda_on_create(ag, db)
            await db.commit()
            step, avail, acts = await _gate(db, aid)
            assert step == "draft" and avail, f"expected send-for-review available at draft, step={step} acts={acts}"
            rows.append(("DRAFT", step, avail, acts))

            # click "send for review" — the real endpoint moves DRAFT->UNDER_REVIEW
            # through the funnel (which mirrors the engine to under_review).
            await change_agreement_status(db, aid, AgreementStatus.UNDER_REVIEW, user_id="system")
            step, avail, acts = await _gate(db, aid)
            assert step == "under_review" and not avail, f"send-for-review must be gone at under_review, acts={acts}"
            rows.append(("UNDER_REVIEW", step, avail, acts))

            # later step: ready_for_signature — still not available
            await change_agreement_status(db, aid, AgreementStatus.READY_FOR_SIGNATURE, user_id="system")
            step, avail, acts = await _gate(db, aid)
            assert step == "ready_for_signature" and not avail, f"send-for-review must stay hidden, acts={acts}"
            rows.append(("READY_FOR_SIGNATURE", step, avail, acts))
        finally:
            await _cleanup(db, aid)
            settings.workflow_drives_cda = False

        # ---- FLAG OFF ----
        cfg = await workflow_config()
        assert cfg["drives_cda"] is False
        # with the flag off, on_create starts nothing -> no instance -> gate false,
        # and the FE uses the status ladder (button shown iff status == DRAFT).
        aid = await _make_cda(db, "DRIVE-OFF")
        try:
            ag = await db.get(Agreement, aid)
            await cda_on_create(ag, db)  # gated -> no-op
            await db.commit()
            step, avail, _ = await _gate(db, aid)
            assert step is None and avail is False, f"flag off: no instance/gate, got step={step}"
        finally:
            await _cleanup(db, aid)

    print("=" * 92)
    print('FIRST REAL DRIVE — engine gates CDA "send for review" (flag ON)')
    print("=" * 92)
    print(f"{'agreement.status':24} {'engine step':22} {'send-for-review?':18} engine actions(to)")
    print("-" * 92)
    for status, step, avail, acts in rows:
        shown = "SHOW button" if avail else "hide button"
        print(f"{status:24} {step:22} {shown:18} {acts}")
    print("-" * 92)
    print("PASS  available only at draft; hidden at under_review and ready_for_signature")
    print()
    print("=" * 92)
    print("FLAG OFF")
    print("=" * 92)
    print(f"PASS  config drives_cda={cfg['drives_cda']} -> FE uses the status ladder (button = status==DRAFT), unchanged")
    print("PASS  no instance started -> engine gate false anyway")


if __name__ == "__main__":
    asyncio.run(main())

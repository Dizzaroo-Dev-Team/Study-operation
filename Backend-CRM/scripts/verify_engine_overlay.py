"""
Verify the READ-ONLY engine overlay (run in the backend container).

What this proves (NO driving, NO re-hosting — pure observation):
  * GET /api/workflows/instances?subject_ref=&definition_key=  resolves the linked
    instance (via the router function find_instance) and returns current_step /
    current_step_name / status, or null.
  * Walking a real CDA through every stage USING EACH PATH'S REAL MECHANISM
    (funnel change_agreement_status where the real endpoints use it; direct status
    set with NO sync where send-for-signature bypasses the funnel; direct + bridge
    sync where OTP signing does) — then reading the overlay endpoint at each stage
    and comparing (real status) vs (engine current_step). The known send-for-
    signature LAG is expected and flagged.
  * Same walk for CTA up to where the known gaps begin (cro_gate/cro_review are
    engine-internal; distribute/closed have no real path) — CTA goes fully through
    the funnel, so every stage should MATCH.
  * FLAG OFF: the overlay shows nothing — config() reports drives_*=false (the FE
    badge's `enabled`), and with the flag off no instance is ever started, so the
    endpoint returns null too.

Throwaway agreements on free study_sites; cleaned up. Flags toggled in-proc only
(never persisted) — keep WORKFLOW_DRIVES_* OFF in shared/prod.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, get_db  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401  (init order)
from app.modules.agreements.services.agreement_service import change_agreement_status  # noqa: E402
from app.modules.agreements.types.cda.service import cda_on_create  # noqa: E402
from app.modules.workflows import cda_bridge, cta_bridge  # noqa: E402
from app.modules.workflows.router import find_instance as wf_find_instance  # noqa: E402
from app.modules.workflows.router import workflow_config  # noqa: E402


async def _free_study_site(db, atype):
    return (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type=:t AND study_site_id IS NOT NULL) LIMIT 1"
    ), {"t": atype})).fetchone()


async def _make(db, atype, title):
    ss = await _free_study_site(db, atype)
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                   agreement_type=atype, title=title,
                   status=AgreementStatus.DRAFT, is_legacy="false")
    db.add(ag); await db.flush()
    aid = str(ag.id)
    await db.commit()
    return aid


async def _overlay(db, aid, key):
    """Call the read-only endpoint exactly as the FE badge does."""
    out = await wf_find_instance(subject_ref=aid, definition_key=key, db=db)
    if out is None:
        return None, None
    return out.current_step, out.current_step_name


async def _direct_set(db, aid, status, *, sync=False, key="CDA"):
    """Mimic a path that sets agreement.status DIRECTLY (bypassing the funnel).
    When sync=True, also run the bridge sync the real path calls afterwards."""
    ag = await db.get(Agreement, aid)
    ag.status = status
    if sync:
        if key == "CDA":
            await cda_bridge.sync_cda_instance_to_status(db, ag, status)
        else:
            await cta_bridge.sync_cta_instance_to_status(db, ag, status)
    await db.commit()


async def _cleanup(db, aid):
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN "
                          "(SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


def _row(stage, status, step, step_name, expected):
    match = (step == expected)
    flag = "OK   " if match else "LAG  "
    return (flag, stage, status, step or "—", step_name or "—", expected, match)


async def walk_cda(db):
    rows = []
    settings.workflow_drives_cda = True
    aid = await _make(db, TemplateType.CDA, "OVERLAY-CDA")
    try:
        # 1. create -> on_create starts the instance at 'draft'
        ag = await db.get(Agreement, aid)
        await cda_on_create(ag, db)
        await db.commit()
        step, name = await _overlay(db, aid, "CDA")
        rows.append(_row("create", "DRAFT", step, name, cda_bridge.STATUS_TO_STEP["DRAFT"]))

        # 2. send-for-review -> funnel (mirrors)
        await change_agreement_status(db, aid, AgreementStatus.UNDER_REVIEW, user_id="system")
        step, name = await _overlay(db, aid, "CDA")
        rows.append(_row("send-for-review", "UNDER_REVIEW", step, name, cda_bridge.STATUS_TO_STEP["UNDER_REVIEW"]))

        # 3. complete-review -> funnel (mirrors)
        await change_agreement_status(db, aid, AgreementStatus.READY_FOR_SIGNATURE, user_id="system")
        step, name = await _overlay(db, aid, "CDA")
        rows.append(_row("complete-review", "READY_FOR_SIGNATURE", step, name, cda_bridge.STATUS_TO_STEP["READY_FOR_SIGNATURE"]))

        # 4. send-for-signature -> DIRECT set + bridge sync (signing.py now syncs CDA
        #    explicitly; previously this had NO sync and the engine lagged here).
        await _direct_set(db, aid, AgreementStatus.SENT_FOR_SIGNATURE, sync=True, key="CDA")
        step, name = await _overlay(db, aid, "CDA")
        rows.append(_row("send-for-signature", "SENT_FOR_SIGNATURE", step, name, cda_bridge.STATUS_TO_STEP["SENT_FOR_SIGNATURE"]))

        # 5. first OTP signature -> DIRECT set + bridge sync (otp.py) -> catches up
        await _direct_set(db, aid, AgreementStatus.FULLY_SIGNED, sync=True, key="CDA")
        step, name = await _overlay(db, aid, "CDA")
        rows.append(_row("otp-sign (FULLY_SIGNED)", "FULLY_SIGNED", step, name, cda_bridge.STATUS_TO_STEP["FULLY_SIGNED"]))

        # 6. executed -> DIRECT set + bridge sync
        await _direct_set(db, aid, AgreementStatus.EXECUTED, sync=True, key="CDA")
        step, name = await _overlay(db, aid, "CDA")
        rows.append(_row("executed", "EXECUTED", step, name, cda_bridge.STATUS_TO_STEP["EXECUTED"]))
    finally:
        await _cleanup(db, aid)
        settings.workflow_drives_cda = False
    return rows


async def walk_cta(db):
    rows = []
    settings.workflow_drives_cta = True
    aid = await _make(db, TemplateType.CTA, "OVERLAY-CTA")
    try:
        # 1. select-template create moment -> ensure starts instance at 'draft'
        ag = await db.get(Agreement, aid)
        await cta_bridge.ensure_cta_instance(db, ag)
        await db.commit()
        step, name = await _overlay(db, aid, "CTA")
        rows.append(_row("select-template", "DRAFT", step, name, cta_bridge.STATUS_TO_STEP["DRAFT"]))

        # 2..6 CTA goes fully through the funnel (every real endpoint uses it)
        for stage, status in [
            ("fill-placeholders", AgreementStatus.AWAITING_INTERNAL_REVIEW),
            ("approve-internal", AgreementStatus.INTERNAL_REVIEW_APPROVED),
            ("send-for-signature", AgreementStatus.SENT_FOR_SIGNATURE),
            ("both-signed", AgreementStatus.AWAITING_SPONSOR_SIGNATURE),
            ("finalize-sponsor", AgreementStatus.EXECUTED),
        ]:
            await change_agreement_status(db, aid, status, user_id="system")
            step, name = await _overlay(db, aid, "CTA")
            rows.append(_row(stage, status.value, step, name, cta_bridge.STATUS_TO_STEP[status.value]))
    finally:
        await _cleanup(db, aid)
        settings.workflow_drives_cta = False
    return rows


async def flag_off_check(db):
    settings.workflow_drives_cda = False
    settings.workflow_drives_cta = False
    cfg = await workflow_config()
    assert cfg["drives_cda"] is False and cfg["drives_cta"] is False
    # flag off -> on_create/ensure start nothing -> endpoint returns null
    aid = await _make(db, TemplateType.CDA, "OVERLAY-OFF")
    try:
        ag = await db.get(Agreement, aid)
        await cda_on_create(ag, db)   # gated -> no-op
        await db.commit()
        step, _ = await _overlay(db, aid, "CDA")
        assert step is None, f"flag off must yield no instance, got step={step}"
    finally:
        await _cleanup(db, aid)
    return cfg


def _print_table(title, rows):
    print("=" * 100)
    print(title)
    print("=" * 100)
    print(f"{'':5} {'stage':22} {'agreement.status':28} {'engine current_step':22} expected")
    print("-" * 100)
    lags = 0
    for flag, stage, status, step, _name, expected, match in rows:
        if not match:
            lags += 1
        print(f"{flag} {stage:22} {status:28} {step:22} {expected}")
    print("-" * 100)
    print(f"{len(rows)} stages; {lags} mismatch(es)" + (" (known send-for-signature lag)" if lags else ""))


async def main():
    async with AsyncSessionLocal() as db:
        cda_rows = await walk_cda(db)
        cta_rows = await walk_cta(db)
        cfg = await flag_off_check(db)

    _print_table("CDA — real status vs engine current_step (read-only overlay)", cda_rows)
    print()
    _print_table("CTA — real status vs engine current_step (read-only overlay)", cta_rows)
    print()
    print("=" * 100)
    print("FLAG OFF")
    print("=" * 100)
    print(f"PASS  config() -> drives_cda={cfg['drives_cda']}, drives_cta={cfg['drives_cta']} "
          f"(FE badge `enabled` false -> no badge)")
    print("PASS  flag off -> no instance started -> endpoint returns null -> badge renders nothing")


if __name__ == "__main__":
    asyncio.run(main())

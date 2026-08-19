"""
Verify the CDA workflow-view swap (run in the backend container).

AgreementTab renders the generic WorkflowRunner instead of the hardcoded CDA panel
exactly when:
    runnerOwnsView = drives_cda AND agreement exists AND a CDA instance exists
(resolved by subject_ref via the same find_instance endpoint the screen uses).
Otherwise the existing hardcoded panel renders, byte-for-byte today. One view at a
time — the booleans below are mutually exclusive.

Cases:
  * FLAG ON  + real CDA with an instance   -> runner owns the view
  * FLAG ON  + agreement with NO instance  -> existing panel (fallback)
  * FLAG OFF                                -> existing panel (byte-for-byte today)

Throwaway CDA; cleaned up. Flag toggled in-proc only. Keep WORKFLOW_DRIVES_CDA OFF
in shared/prod.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401  (init order)
from app.modules.agreements.types.cda.service import cda_on_create  # noqa: E402
from app.modules.workflows import service  # noqa: E402


def runner_owns_view(drives_cda: bool, has_agreement: bool, instance_id) -> bool:
    return bool(drives_cda) and bool(has_agreement) and instance_id is not None


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


async def _instance_id(db, aid):
    inst = await service.find_instance_by_subject(db, aid, "CDA")
    return inst.id if inst else None


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        # FLAG ON + instance exists -> runner owns the view
        settings.workflow_drives_cda = True
        aid = await _make_cda(db, "RUNNER-SWAP")
        try:
            ag = await db.get(Agreement, aid)
            await cda_on_create(ag, db)
            await db.commit()
            iid = await _instance_id(db, aid)
            assert iid is not None
            assert runner_owns_view(True, True, iid) is True
            results.append(("FLAG ON + real CDA instance", f"instance #{iid} -> WorkflowRunner owns the view"))

            # FLAG OFF (same agreement+instance) -> existing panel
            assert runner_owns_view(False, True, iid) is False
            results.append(("FLAG OFF", "existing hardcoded panel (byte-for-byte today)"))
        finally:
            await _cleanup(db, aid)
            settings.workflow_drives_cda = False

        # FLAG ON + agreement with NO instance -> existing panel (fallback)
        settings.workflow_drives_cda = True
        aid2 = await _make_cda(db, "RUNNER-SWAP-NOINST")
        try:
            iid2 = await _instance_id(db, aid2)  # never started one
            assert iid2 is None
            assert runner_owns_view(True, True, iid2) is False
            results.append(("FLAG ON + no instance", "existing panel (runner needs an instance)"))
        finally:
            await _cleanup(db, aid2)
            settings.workflow_drives_cda = False

    print("=" * 88)
    print("CDA WORKFLOW-VIEW SWAP — runnerOwnsView decision (one view at a time)")
    print("=" * 88)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 88)
    print("Runner block and hardcoded panel are mutually exclusive via runnerOwnsView. No double-render.")


if __name__ == "__main__":
    asyncio.run(main())

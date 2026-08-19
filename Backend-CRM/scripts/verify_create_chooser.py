"""
Verify the CDA create-chooser integration (run in the backend container).

Frontend behavior being verified at the backend level:
  - GET /api/workflows/config exposes the flags (chooser shows only when on).
  - FLAG OFF: agreement create starts NO instance (chooser never renders).
  - FLAG ON, three choices — each creates the agreement and EXACTLY ONE linked
    instance on the correct published version (no double-start):
      * Use existing  -> instance on the CURRENT published CDA version.
      * Edit existing / Create new -> the chooser publishes a NEW version FIRST
        (becomes default); the existing create's on_create then starts the single
        instance on that NEW version.

The chooser itself never starts an instance — only the on_create bridge does, so
there is exactly one per agreement. Throwaway CDAs on free study_sites; cleaned up.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401  (init order)
from app.modules.agreements.types.cda.service import cda_on_create  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.cda_bridge import CDA_V2_BODY  # noqa: E402
from app.modules.workflows.router import workflow_config  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402


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


async def _instances(db, aid):
    rows = (await db.execute(text(
        "SELECT definition_version FROM workflow_instances WHERE subject_ref=:a AND definition_key='CDA'"),
        {"a": aid})).fetchall()
    return [r[0] for r in rows]


async def _published_cda_version(db):
    v = await service.get_definition_version(db, "CDA")
    return v.version


async def _publish_new_cda(db):
    """What 'Edit'/'Create new' do in the builder: publish a new CDA version."""
    body = WorkflowDefinitionBody.model_validate(CDA_V2_BODY)
    async with transactional(db):
        v = await service.create_or_update_definition(db, body, publish=True, published_by="builder-user")
    return v.version


async def _cleanup(db, aid):
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


async def _create_and_oncreate(db, aid):
    """Mirror the real create: load the agreement and run the on_create dispatch
    exactly once (as crud.py does). Returns instance versions linked to it."""
    ag = await db.get(Agreement, aid)
    await cda_on_create(ag, db)
    await db.commit()
    return await _instances(db, aid)


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        # --- /config endpoint shape ---
        settings.workflow_drives_cda = False
        cfg_off = await workflow_config()
        settings.workflow_drives_cda = True
        cfg_on = await workflow_config()
        assert cfg_off["drives_cda"] is False and cfg_on["drives_cda"] is True
        results.append(("GET /workflows/config reflects the flag",
                        f"off={cfg_off['drives_cda']}, on={cfg_on['drives_cda']}"))

        # --- FLAG OFF: no instance, chooser never shows ---
        settings.workflow_drives_cda = False
        aid = await _make_cda(db, "CHOOSER-OFF")
        try:
            insts = await _create_and_oncreate(db, aid)
            assert insts == [], f"flag off must start NO instance, got {insts}"
            results.append(("FLAG OFF: create starts no instance (screen unchanged)", "instances=0"))
        finally:
            await _cleanup(db, aid)

        # --- FLAG ON: Use existing -> 1 instance on CURRENT published version ---
        settings.workflow_drives_cda = True
        cur = await _published_cda_version(db)
        aid = await _make_cda(db, "CHOOSER-USE-EXISTING")
        try:
            insts = await _create_and_oncreate(db, aid)
            assert insts == [cur], f"expected exactly one instance on v{cur}, got {insts}"
            results.append(("FLAG ON · Use existing -> 1 instance on current published",
                            f"instances={insts} (published v{cur})"))
        finally:
            await _cleanup(db, aid)

        # --- FLAG ON: Edit existing -> publish new version FIRST, then create ---
        newv = await _publish_new_cda(db)            # the builder's Save & publish
        assert newv == cur + 1
        aid = await _make_cda(db, "CHOOSER-EDIT")
        try:
            insts = await _create_and_oncreate(db, aid)
            assert insts == [newv], f"expected exactly one instance on new v{newv}, got {insts}"
            results.append(("FLAG ON · Edit existing -> 1 instance on NEW published version",
                            f"instances={insts} (new default v{newv})"))
        finally:
            await _cleanup(db, aid)

        # --- FLAG ON: Create new -> same mechanism (publish new, then create) ---
        newv2 = await _publish_new_cda(db)
        aid = await _make_cda(db, "CHOOSER-CREATE-NEW")
        try:
            insts = await _create_and_oncreate(db, aid)
            assert insts == [newv2], f"expected exactly one instance on v{newv2}, got {insts}"
            results.append(("FLAG ON · Create new -> 1 instance on NEW published version",
                            f"instances={insts} (new default v{newv2})"))
        finally:
            await _cleanup(db, aid)

    print("=" * 80)
    print("CREATE-CHOOSER (CDA) — VERIFICATION")
    print("=" * 80)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 80)
    print(f"{len(results)} checks passed; exactly-one-instance held in every flag-on case")


if __name__ == "__main__":
    asyncio.run(main())

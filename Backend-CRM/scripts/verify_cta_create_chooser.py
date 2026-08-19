"""
Verify the CTA create-chooser integration (run in the backend container).

The CTA "create moment" is select-template (it produces the initial
AgreementDocument v1). The chooser lives in CTAWorkflowPanel's DraftSetupStep and
never starts an instance itself — the select-template backend calls
cta_bridge.ensure_cta_instance, which is IDEMPOTENT: it starts exactly one engine
instance on the CURRENTLY published CTA version, or no-ops if one already exists.

Frontend behavior verified here at the backend level (ensure_cta_instance is the
exact call the select-template route makes):

  * GET /api/workflows/config exposes drives_cta (chooser shows only when on).
  * FLAG OFF: the create moment starts NO instance (chooser never renders).
  * FLAG ON, three choices — each yields EXACTLY ONE instance on the right version:
      - Use existing  -> instance on the CURRENT published CTA version.
      - Edit / Create new -> the builder publishes a NEW version FIRST (becomes
        default); the create moment then starts the single instance on that NEW
        version.
  * DOUBLE-START GUARD: even if on_create already started one at row-create, the
    select-template ensure_cta_instance no-ops -> still exactly one. Calling ensure
    twice is also a no-op.

Throwaway CTAs on free study_sites; cleaned up. WORKFLOW_DRIVES_CTA toggled in-proc
only (never persisted) — keep it OFF in shared/prod.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401  (init order)
from app.modules.agreements.types.cta.service import cta_on_create  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.cta_bridge import (  # noqa: E402
    CTA_V2_BODY,
    ensure_cta_instance,
    seed_cta_v2,
)
from app.modules.workflows.router import workflow_config  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402


async def _make_cta(db, title):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CTA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                   agreement_type=TemplateType.CTA, title=title,
                   status=AgreementStatus.DRAFT, is_legacy="false")
    db.add(ag); await db.flush()
    aid = str(ag.id)
    await db.commit()
    return aid


async def _instances(db, aid):
    rows = (await db.execute(text(
        "SELECT definition_version FROM workflow_instances WHERE subject_ref=:a AND definition_key='CTA'"),
        {"a": aid})).fetchall()
    return [r[0] for r in rows]


async def _ensure_seeded(db):
    """Make sure a published CTA version exists (Use-existing needs one)."""
    try:
        await service.get_definition_version(db, "CTA")
    except Exception:
        async with transactional(db):
            await seed_cta_v2(db)


async def _published_cta_version(db):
    v = await service.get_definition_version(db, "CTA")
    return v.version


async def _publish_new_cta(db):
    """What 'Edit'/'Create new' do in the builder: publish a new CTA version."""
    body = WorkflowDefinitionBody.model_validate(CTA_V2_BODY)
    async with transactional(db):
        v = await service.create_or_update_definition(db, body, publish=True, published_by="builder-user")
    return v.version


async def _cleanup(db, aid):
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN "
                          "(SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


async def _select_template_moment(db, aid):
    """Mirror the real select-template create moment: load the agreement fresh and
    run the SAME idempotent call the route makes (ensure_cta_instance). Commit and
    return the instance versions linked to it."""
    ag = await db.get(Agreement, aid)
    await ensure_cta_instance(db, ag)
    await db.commit()
    return await _instances(db, aid)


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        await _ensure_seeded(db)

        # --- /config endpoint shape ---
        settings.workflow_drives_cta = False
        cfg_off = await workflow_config()
        settings.workflow_drives_cta = True
        cfg_on = await workflow_config()
        assert cfg_off["drives_cta"] is False and cfg_on["drives_cta"] is True
        results.append(("GET /workflows/config reflects the flag",
                        f"off={cfg_off['drives_cta']}, on={cfg_on['drives_cta']}"))

        # --- FLAG OFF: create moment starts NO instance (chooser never shows) ---
        settings.workflow_drives_cta = False
        aid = await _make_cta(db, "CTA-CHOOSER-OFF")
        try:
            insts = await _select_template_moment(db, aid)
            assert insts == [], f"flag off must start NO instance, got {insts}"
            results.append(("FLAG OFF: select-template starts no instance (screen unchanged)", "instances=0"))
        finally:
            await _cleanup(db, aid)

        # --- FLAG ON: Use existing -> 1 instance on CURRENT published version ---
        settings.workflow_drives_cta = True
        cur = await _published_cta_version(db)
        aid = await _make_cta(db, "CTA-CHOOSER-USE-EXISTING")
        try:
            insts = await _select_template_moment(db, aid)
            assert insts == [cur], f"expected exactly one instance on v{cur}, got {insts}"
            results.append(("FLAG ON · Use existing -> 1 instance on current published",
                            f"instances={insts} (published v{cur})"))
        finally:
            await _cleanup(db, aid)

        # --- FLAG ON: Edit existing -> publish new version FIRST, then create ---
        newv = await _publish_new_cta(db)            # the builder's Save & publish
        assert newv == cur + 1
        aid = await _make_cta(db, "CTA-CHOOSER-EDIT")
        try:
            insts = await _select_template_moment(db, aid)
            assert insts == [newv], f"expected exactly one instance on new v{newv}, got {insts}"
            results.append(("FLAG ON · Edit existing -> 1 instance on NEW published version",
                            f"instances={insts} (new default v{newv})"))
        finally:
            await _cleanup(db, aid)

        # --- FLAG ON: Create new -> same mechanism (publish new, then create) ---
        newv2 = await _publish_new_cta(db)
        aid = await _make_cta(db, "CTA-CHOOSER-CREATE-NEW")
        try:
            insts = await _select_template_moment(db, aid)
            assert insts == [newv2], f"expected exactly one instance on v{newv2}, got {insts}"
            results.append(("FLAG ON · Create new -> 1 instance on NEW published version",
                            f"instances={insts} (new default v{newv2})"))
        finally:
            await _cleanup(db, aid)

        # --- DOUBLE-START GUARD: on_create starts one, select-template no-ops ---
        cur2 = await _published_cta_version(db)
        aid = await _make_cta(db, "CTA-CHOOSER-NO-DOUBLE")
        try:
            # row-create path fires first
            ag = await db.get(Agreement, aid)
            await cta_on_create(ag, db)
            await db.commit()
            after_oncreate = await _instances(db, aid)
            assert after_oncreate == [cur2], f"on_create should start exactly one, got {after_oncreate}"
            # then the select-template moment runs ensure again -> must NOT add another
            insts = await _select_template_moment(db, aid)
            assert insts == [cur2], f"ensure after on_create must NOT double-start, got {insts}"
            # and a redundant ensure call is also a no-op
            insts2 = await _select_template_moment(db, aid)
            assert insts2 == [cur2], f"second ensure must stay idempotent, got {insts2}"
            results.append(("DOUBLE-START GUARD: on_create + select-template + repeat -> still ONE",
                            f"instances={insts2} (idempotent on v{cur2})"))
        finally:
            await _cleanup(db, aid)

        # restore flag OFF (in-proc only; never persisted)
        settings.workflow_drives_cta = False

    print("=" * 80)
    print("CREATE-CHOOSER (CTA) — VERIFICATION")
    print("=" * 80)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 80)
    print(f"{len(results)} checks passed; exactly-one-instance held in every flag-on case")


if __name__ == "__main__":
    asyncio.run(main())

"""
Verify the UNIFIED template-driven workflow plumbing (run in the backend container).

Proves (with WORKFLOW_UNIFIED on):
  1. GET /api/workflows/config reports unified=true.
  2. Type bridges STAND DOWN under unified: cda_on_create starts NO type-keyed
     instance even with WORKFLOW_DRIVES_CDA on (so the only instance is the unified
     tpl:<template_id> one — exactly one per agreement).
  3. ensure_instance is idempotent: calling it twice for (agreement, tpl:<id>)
     returns the SAME instance (exactly one).
  4. Two DIFFERENT templates (even same type) get DIFFERENT workflows: distinct
     definition keys -> distinct instances.
  5. Backward-compat: the legacy "CDA"/"CTA" definitions still resolve.

Throwaway agreements + throwaway tpl:* definitions; all cleaned up. Flags toggled
in-proc only. Keep WORKFLOW_* OFF in shared/prod.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.agreements.types.cda.service import cda_on_create  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.router import workflow_config  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

T1 = "tpl:VERIFY-T1"
T2 = "tpl:VERIFY-T2"


def _tpl_body(key, name):
    return {
        "key": key, "name": name, "start_step": "draft", "context_schema": [],
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "transitions": [{"id": "s", "to": "review", "label": "Submit", "action": "submit"}]},
            {"id": "review", "type": "approval", "name": "Review",
             "transitions": [{"id": "a", "to": "done", "label": "Approve", "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def _publish(db, key, name):
    body = WorkflowDefinitionBody.model_validate(_tpl_body(key, name))
    async with transactional(db):
        await service.create_or_update_definition(db, body, publish=True, published_by="verify")


async def _make_cda(db, title):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                   agreement_type=TemplateType.CDA, title=title,
                   status=AgreementStatus.DRAFT, is_legacy="false")
    db.add(ag); await db.flush()
    aid = str(ag.id); await db.commit()
    return aid


async def _cleanup_agreement(db, aid):
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN "
                          "(SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


async def _cleanup_def(db, key):
    d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": key})).fetchone()
    if d:
        await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
        await db.commit()


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        settings.workflow_unified = True
        settings.workflow_drives_cda = True  # prove stand-down even with this ON

        # 1. config
        cfg = await workflow_config()
        assert cfg["unified"] is True, cfg
        results.append(("GET /workflows/config reports unified", f"unified={cfg['unified']}"))

        await _publish(db, T1, "Template 1 workflow")
        await _publish(db, T2, "Template 2 workflow")

        aidA = await _make_cda(db, "UNIFIED-A")
        aidB = await _make_cda(db, "UNIFIED-B")
        try:
            # 2. stand-down: cda_on_create starts NO type-keyed instance under unified
            agA = await db.get(Agreement, aidA)
            await cda_on_create(agA, db); await db.commit()
            cda_inst = await service.find_instance_by_subject(db, aidA, "CDA")
            assert cda_inst is None, f"type bridge must stand down under unified, got {cda_inst}"
            results.append(("Type bridge stands down (WORKFLOW_DRIVES_CDA on + unified)",
                            "cda_on_create started 0 type-keyed instances"))

            # 3. idempotent ensure on the template key
            i1 = await service.ensure_instance(db, T1, aidA, {"agreement_id": aidA, "agreement_type": "CDA"})
            await db.commit()
            i2 = await service.ensure_instance(db, T1, aidA, {"agreement_id": aidA})
            await db.commit()
            assert i1.id == i2.id, f"ensure must be idempotent: {i1.id} vs {i2.id}"
            count = (await db.execute(text("SELECT count(*) FROM workflow_instances WHERE subject_ref=:a"), {"a": aidA})).scalar()
            assert count == 1, f"exactly one instance per agreement, got {count}"
            results.append(("ensure_instance idempotent -> exactly one",
                            f"instance #{i1.id} (1 row, key {i1.definition_key})"))

            # 4. two different templates -> different workflows/instances
            iB = await service.ensure_instance(db, T2, aidB, {"agreement_id": aidB})
            await db.commit()
            assert iB.definition_key == T2 and i1.definition_key == T1 and iB.id != i1.id
            results.append(("Different templates -> different workflows",
                            f"A->{i1.definition_key} (#{i1.id}) · B->{iB.definition_key} (#{iB.id})"))

            # 5. legacy CDA/CTA still resolve
            cda_v = await service.get_definition_version(db, "CDA")
            cta_v = await service.get_definition_version(db, "CTA")
            results.append(("Backward-compat: legacy defs resolve",
                            f"CDA v{cda_v.version}, CTA v{cta_v.version} still published"))
        finally:
            await _cleanup_agreement(db, aidA)
            await _cleanup_agreement(db, aidB)
            await _cleanup_def(db, T1)
            await _cleanup_def(db, T2)
            settings.workflow_unified = False
            settings.workflow_drives_cda = False

    print("=" * 90)
    print("UNIFIED TEMPLATE-DRIVEN WORKFLOW — VERIFICATION")
    print("=" * 90)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 90)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

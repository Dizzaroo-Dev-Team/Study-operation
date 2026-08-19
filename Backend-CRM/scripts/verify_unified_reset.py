"""
Verify Part A (key alignment) + Part B (reset endpoint) for the unified page.
Run in the backend container.

PART A: a workflow published under tpl:<template_id> appears in listDefinitions
        under the SAME key the page looks up — so detection works after publish.
PART B reset endpoint (POST /api/workflows/definitions/reset):
  * GATED: refuses (403) when WORKFLOW_UNIFIED is off (prod-safe / not callable).
  * When on: deletes the definition + versions + instances + audit for that key.
  * IDEMPOTENT: a second reset returns zero counts, no error.
  * SCOPE: never touches the agreement row, and a DIFFERENT template's workflow is
    unaffected.

Throwaway tpl:* defs + agreements; cleaned up. Flags toggled in-proc only.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.router import reset_definition as route_reset  # noqa: E402
from app.modules.workflows.schemas import ResetRequest, WorkflowDefinitionBody  # noqa: E402

T1 = "tpl:RESET-T1"
T2 = "tpl:RESET-T2"


def _body(key, name):
    return {
        "key": key, "name": name, "start_step": "draft", "context_schema": [],
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "transitions": [{"id": "s", "to": "done", "label": "Submit", "action": "submit"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def _publish(db, key, name):
    body = WorkflowDefinitionBody.model_validate(_body(key, name))
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


async def _count(db, sql, **p):
    return (await db.execute(text(sql), p)).scalar()


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        settings.workflow_unified = True
        await _publish(db, T1, "Reset T1")
        await _publish(db, T2, "Reset T2")
        aidA = await _make_cda(db, "RESET-A")
        aidB = await _make_cda(db, "RESET-B")
        try:
            # PART A — publish key == lookup key (both tpl:<id>; in the list)
            keys = [d.key for d in await service.list_definitions(db)]
            assert T1 in keys and T2 in keys, keys
            results.append(("PART A: publish key == lookup key",
                            f"list contains {T1} -> checkDefinition detects it (no divergence)"))

            # instances (with their 'started' audit rows)
            await service.ensure_instance(db, T1, aidA, {"agreement_id": aidA}); await db.commit()
            await service.ensure_instance(db, T2, aidB, {"agreement_id": aidB}); await db.commit()
            a_audit = await _count(db, "SELECT count(*) FROM workflow_audit_entries e "
                                       "JOIN workflow_instances i ON i.id=e.instance_id WHERE i.definition_key=:k", k=T1)

            # GATING — flag off -> 403
            settings.workflow_unified = False
            try:
                await route_reset(ResetRequest(key=T1), db)
                raise AssertionError("expected 403 when WORKFLOW_UNIFIED off")
            except HTTPException as e:
                assert e.status_code == 403, e.status_code
            results.append(("Reset GATED when flag off (prod-safe)", "POST reset -> 403, not callable"))
            settings.workflow_unified = True

            # RESET T1
            res = await route_reset(ResetRequest(key=T1), db)
            assert res["definition_deleted"] and res["instances_deleted"] >= 1 and res["audit_deleted"] == a_audit
            assert await service.find_instance_by_subject(db, aidA, T1) is None
            assert await _count(db, "SELECT count(*) FROM workflow_definitions WHERE key=:k", k=T1) == 0
            results.append(("Reset wipes def+versions+instances+audit",
                            f"def_deleted={res['definition_deleted']}, versions={res['versions_deleted']}, "
                            f"instances={res['instances_deleted']}, audit={res['audit_deleted']}"))

            # IDEMPOTENT
            res2 = await route_reset(ResetRequest(key=T1), db)
            assert res2["definition_deleted"] is False and res2["instances_deleted"] == 0
            results.append(("Reset idempotent", "second reset -> zero counts, no error"))

            # SCOPE — agreement A row kept; T2 def + instance untouched
            assert await db.get(Agreement, aidA) is not None
            assert await _count(db, "SELECT count(*) FROM workflow_definitions WHERE key=:k", k=T2) == 1
            assert await service.find_instance_by_subject(db, aidB, T2) is not None
            results.append(("Scope preserved",
                            "agreement A row kept; second template T2 def + instance unaffected"))
        finally:
            for k in (T1, T2):
                async with transactional(db):
                    await service.reset_definition(db, k)
            for aid in (aidA, aidB):
                await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
                await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
            await db.commit()
            settings.workflow_unified = False

    print("=" * 92)
    print("UNIFIED KEY-ALIGNMENT + RESET — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

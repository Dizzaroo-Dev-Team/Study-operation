"""
Verify the module-layer SKELETON backend pieces (run in the container):
  * ownership primitive (creator-owns): is_agreement_owner / GET permits/owner.
  * Step schema accepts the new optional `module` field, and the ENGINE IGNORES it
    (engine stays the pure state machine; only the runner reads `module`).

Throwaway agreement; cleaned up. No flags toggled.
"""
import asyncio
import sys
import uuid

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.engine import WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

BODY_WITH_MODULE = {
    "key": "MODTEST", "name": "Module field test", "start_step": "draft", "context_schema": [],
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft", "module": "document_create",
         "transitions": [{"id": "s", "to": "review", "label": "Submit", "action": "submit"}]},
        {"id": "review", "type": "approval", "name": "Review", "module": "review",
         "transitions": [{"id": "a", "to": "done", "label": "Approve", "action": "approve"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        ss = (await db.execute(text(
            "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
            "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
        ))).fetchone()
        ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0],
                       agreement_type=TemplateType.CDA, title="MODULE-LAYER",
                       status=AgreementStatus.DRAFT, is_legacy="false", created_by="user-A")
        db.add(ag); await db.flush()
        aid = str(ag.id); await db.commit()
        try:
            # Ownership primitive
            owner = await service.is_agreement_owner(db, aid, "user-A")
            assert owner["is_owner"] is True and owner["found"] is True, owner
            results.append(("permits/owner: creator -> is_owner", f"{owner}"))

            non_owner = await service.is_agreement_owner(db, aid, "user-B")
            assert non_owner["is_owner"] is False and non_owner["found"] is True
            results.append(("permits/owner: non-creator -> not owner", f"is_owner={non_owner['is_owner']}"))

            missing = await service.is_agreement_owner(db, str(uuid.uuid4()), "user-A")
            assert missing["is_owner"] is False and missing["found"] is False
            results.append(("permits/owner: unknown subject -> default-deny", f"found={missing['found']}"))

            # Step.module parses + engine ignores it
            body = WorkflowDefinitionBody.model_validate(BODY_WITH_MODULE)
            mods = {s.id: s.module for s in body.steps}
            assert mods["draft"] == "document_create" and mods["review"] == "review" and mods["done"] is None
            results.append(("Step.module round-trips", f"{mods}"))

            eng = WorkflowEngine(body, enforce_roles=False)
            start = eng.start({})
            assert start.step_id == "draft", start.step_id  # engine runs, module ignored
            results.append(("Engine ignores `module` (pure state machine)", f"start step={start.step_id}"))
        finally:
            await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
            await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
            await db.commit()

    print("=" * 84)
    print("MODULE LAYER SKELETON — BACKEND VERIFICATION")
    print("=" * 84)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 84)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

"""
Verify the ordered-signing editor end to end (run in the backend container).

Reproduces exactly what the sandbox does:
  1. The builder's ordered_signing editor writes config.signers = [director, pi, vp]
     (ordered). We construct that definition body verbatim.
  2. Save & publish -> create_or_update_definition(publish=True).
  3. Start an instance -> start_instance.
  4. Runner -> service.available_actions / perform_action: confirm ONLY the first
     signer can act, the next opens after the previous signs, in the order set.
  5. Round-trip -> get_definition_version (what fromDefinition would load) and
     confirm the signer order is preserved.

Throwaway key ZZSIGN; cleaned up. Engine unchanged; workflow flags irrelevant here.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select, text  # noqa: E402

from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.models import WorkflowDefinition  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

KEY = "ZZSIGN"
ORDER = ["director", "pi", "vp"]

# Exactly the body the builder's toDefinition() produces for an ordered_signing
# node whose editor lists Director -> PI -> VP.
BODY = {
    "key": KEY, "name": "Ordered signing editor test", "start_step": "draft",
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "signing", "label": "Submit", "action": "submit"}]},
        {"id": "signing", "type": "ordered_signing", "name": "Signatures",
         "config": {"signers": [
             {"id": "director", "name": "Site Director", "assignee": {"type": "role", "value": "sponsor"}},
             {"id": "pi", "name": "PI", "assignee": {"type": "role", "value": "coordinator"}},
             {"id": "vp", "name": "VP", "assignee": {"type": "role", "value": "sponsor"}}]},
         "transitions": [{"id": "done_t", "to": "done", "label": "All signed", "action": "all_signed"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}

U = CurrentUser(id="tester", roles=[])  # open mode (enforce_roles default False)


async def _offered(db, inst_id):
    acts = await service.available_actions(db, inst_id, U)
    return [a.transition_id for a in acts]


async def _cleanup(db):
    d = await db.scalar(select(WorkflowDefinition).where(WorkflowDefinition.key == KEY))
    if d:
        await db.execute(text("DELETE FROM workflow_instances WHERE definition_key=:k"), {"k": KEY})
        await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d.id})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d.id})
        await db.commit()


async def main():
    async with AsyncSessionLocal() as db:
        await _cleanup(db)
        results = []
        try:
            body = WorkflowDefinitionBody.model_validate(BODY)  # parses = builder output is valid

            # 2. Save & publish
            async with transactional(db):
                v = await service.create_or_update_definition(db, body, publish=True, published_by="builder-user")
            results.append(("Save & publish (ordered_signing node)", f"version {v.version} published"))

            # 3. Start an instance
            async with transactional(db):
                inst = await service.start_instance(db, KEY, {}, subject_ref="agly-sign")
            assert inst.current_step == "draft"

            # advance form -> signing
            async with transactional(db):
                await service.perform_action(db, inst.id, U, "submit", {})
            inst = await service.get_instance(db, inst.id)
            assert inst.current_step == "signing", inst.current_step

            # 4. Order enforcement: only the current slot is offered at each stage.
            seen_order = []
            for expected in ORDER:
                offered = await _offered(db, inst.id)
                assert offered == [f"{expected}:sign"], f"expected only {expected}:sign, got {offered}"
                seen_order.append(expected)
                async with transactional(db):
                    await service.perform_action(db, inst.id, U, f"{expected}:sign", {})
                inst = await service.get_instance(db, inst.id)
            assert inst.current_step == "done" and inst.status == "completed", (inst.current_step, inst.status)
            results.append(("Order enforced slot-by-slot", " -> ".join(seen_order) + " -> done (completed)"))
            # prove a LATER signer was never offered before its turn
            results.append(("Gating proven", "at each stage exactly one slot was open; no skipping"))

            # 5. Round-trip: what fromDefinition() loads back.
            pub = await service.get_definition_version(db, KEY)
            signing = next(s for s in pub.body["steps"] if s["id"] == "signing")
            loaded_order = [s["id"] for s in signing["config"]["signers"]]
            loaded_names = [s["name"] for s in signing["config"]["signers"]]
            assert loaded_order == ORDER, loaded_order
            results.append(("Round-trip order preserved", f"{loaded_order}  ({loaded_names})"))

            print("=" * 78)
            print("ORDERED-SIGNING EDITOR — END-TO-END VERIFICATION")
            print("=" * 78)
            for label, detail in results:
                print(f"PASS  {label}\n        -> {detail}")
            print("=" * 78)
            print(f"{len(results)}/{len(results)} checks passed")
        finally:
            await _cleanup(db)


if __name__ == "__main__":
    asyncio.run(main())

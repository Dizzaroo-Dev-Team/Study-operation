"""
Integration verification for "choose workflow when creating an agreement" (run in
the backend container). Exercises the REAL service against the real DB with a
throwaway definition key, proving:

  a) use existing  -> instance starts on the current PUBLISHED version
  b) edit existing -> new version published & becomes default; a NEW instance uses
     it; AND an instance started on the OLD version BEFORE the edit still runs on
     the old version, unchanged (VERSION PINNING)
  c) create new    -> new key published v1 + default; instance runs on it
  d) publish-as-default records WHO + WHEN and is retrievable

Throwaway keys (ZZCHOOSE*) — does not touch CDA/CTA. Cleans up afterwards.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import select, text  # noqa: E402

from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.modules.workflows import service  # noqa: E402
from app.modules.workflows.models import (  # noqa: E402
    WorkflowDefinition, WorkflowDefinitionVersion, WorkflowInstance,
)
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

KEY = "ZZCHOOSE"
KEY2 = "ZZCHOOSE2"


def _body(key, terminal_name, extra_step=False):
    """Two distinguishable shapes so 'old vs new version' is visible."""
    steps = [
        {"id": "draft", "type": "form", "name": "Draft",
         "transitions": [{"id": "submit", "to": "review" if extra_step else "done",
                          "label": "Submit", "action": "submit"}]},
    ]
    if extra_step:
        steps.append({"id": "review", "type": "approval", "name": "Review",
                      "transitions": [{"id": "ok", "to": "done", "label": "OK", "action": "approve"}]})
    steps.append({"id": "done", "type": "terminal", "name": terminal_name, "transitions": []})
    return WorkflowDefinitionBody.model_validate(
        {"key": key, "name": f"{key} flow", "start_step": "draft", "steps": steps})


async def _published(db, key):
    return await service.get_definition_version(db, key)


async def _cleanup(db):
    for k in (KEY, KEY2):
        d = await db.scalar(select(WorkflowDefinition).where(WorkflowDefinition.key == k))
        if not d:
            continue
        await db.execute(text("DELETE FROM workflow_instances WHERE definition_key = :k"), {"k": k})
        await db.execute(text(
            "DELETE FROM workflow_definition_versions WHERE definition_id = :i"), {"i": d.id})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id = :i"), {"i": d.id})
    await db.commit()


async def main():
    async with AsyncSessionLocal() as db:
        await _cleanup(db)  # fresh start
        results = []
        try:
            # ---- a) USE EXISTING ----------------------------------------------
            async with transactional(db):
                v1 = await service.create_or_update_definition(
                    db, _body(KEY, "Done v1"), publish=True, published_by="alice")
            v1_id, v1_ver = v1.id, v1.version
            async with transactional(db):
                inst_a = await service.start_instance(db, KEY, {}, subject_ref="agly-a")
            assert inst_a.definition_version == v1_ver == 1
            assert inst_a.version_id == v1_id
            results.append(("a) use existing -> starts on current published v1",
                            f"instance v{inst_a.definition_version}, version_id={inst_a.version_id}"))

            # An instance started on the OLD version BEFORE any edit (for pinning).
            async with transactional(db):
                inst_old = await service.start_instance(db, KEY, {}, subject_ref="agly-old")
            assert inst_old.version_id == v1_id

            # ---- b) EDIT EXISTING -> publish v2 (new default) -----------------
            async with transactional(db):
                v2 = await service.create_or_update_definition(
                    db, _body(KEY, "Done v2", extra_step=True), publish=True, published_by="bob")
            v2_id, v2_ver = v2.id, v2.version
            assert v2_ver == 2
            # New default is v2
            pub = await _published(db, KEY)
            assert pub.version == 2 and pub.id == v2_id
            # A NEW agreement uses the new default (v2)
            async with transactional(db):
                inst_b = await service.start_instance(db, KEY, {}, subject_ref="agly-b")
            assert inst_b.definition_version == 2 and inst_b.version_id == v2_id
            # VERSION PINNING: the pre-edit instance still runs on v1, untouched
            inst_old_reloaded = await service.get_instance(db, inst_old.id)
            assert inst_old_reloaded.version_id == v1_id, "old instance drifted off its version!"
            assert inst_old_reloaded.definition_version == 1
            # ...and its engine resolves the v1 body (1-step), not v2 (2-step)
            v1_row = await db.get(WorkflowDefinitionVersion, inst_old_reloaded.version_id)
            v1_body = WorkflowDefinitionBody.model_validate(v1_row.body)
            assert [s.id for s in v1_body.steps] == ["draft", "done"], "old instance not on v1 shape"
            results.append((
                "b) edit -> v2 published+default; new agreement on v2; OLD instance pinned to v1",
                f"new inst v{inst_b.definition_version}; old inst still v{inst_old_reloaded.definition_version} "
                f"(version_id={inst_old_reloaded.version_id})"))

            # ---- c) CREATE NEW (brand-new key) --------------------------------
            async with transactional(db):
                c1 = await service.create_or_update_definition(
                    db, _body(KEY2, "Done"), publish=True, published_by="carol")
            async with transactional(db):
                inst_c = await service.start_instance(db, KEY2, {}, subject_ref="agly-c")
            assert inst_c.definition_version == 1 and inst_c.version_id == c1.id
            results.append(("c) create new -> v1 published+default; instance runs on it",
                            f"instance v{inst_c.definition_version} on {KEY2}"))

            # ---- d) AUDIT: who + when recorded & retrievable ------------------
            pub_v2 = await service.get_definition_version(db, KEY, 2)
            by, at = service.publish_meta(pub_v2)
            by1, at1 = service.publish_meta(await service.get_definition_version(db, KEY, 1))
            assert by == "bob" and at, f"v2 publish audit missing: by={by} at={at}"
            assert by1 == "alice", f"v1 publish audit wrong: {by1}"
            results.append(("d) publish-as-default records who+when (retrievable)",
                            f"v1 by={by1}, v2 by={by} at={at}"))

            print("=" * 78)
            print("CHOOSE-WORKFLOW VERIFICATION")
            print("=" * 78)
            for label, detail in results:
                print(f"PASS  {label}\n        -> {detail}")
            print("=" * 78)
            print(f"{len(results)}/4 checks passed")
        finally:
            await _cleanup(db)


if __name__ == "__main__":
    asyncio.run(main())

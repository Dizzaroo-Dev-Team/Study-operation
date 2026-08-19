"""
Verify the THREE heavy-workflow authoring fixes (general, any document type):
  BUG 1 — standalone "Owner sends for/to X" approval steps (review & signing) are
          detected (incl. "Sends for"/"Sends to", any case) and FOLDED away.
  BUG 2 — every completion path distributes: a branch that ended at its own terminal
          (skipping the broadcast) is rerouted THROUGH the broadcast.
  BUG 3 — a decision variable is declared in context_schema AND collected (draft form
          field) so the branch is REACHABLE; both branches then actually execute.
Normalizer is exercised directly + the repaired def is published and RUN for both
decision values. "has_cro" is only the example variable. Throwaway; cleaned up.
"""
import asyncio
import copy
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.modules.workflows import generate as gen  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

KEY = "tpl:zz-authfix"


def heavy_broken():
    """A CRO/Site flow with all three bugs: 'Owner sends for/to X' steps, a CRO path
    that ends without distribution, and a has_cro decision that's neither declared
    nor collected."""
    return {
        "key": KEY, "name": "Heavy", "start_step": "draft", "context_schema": [],
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft Document", "module": "document_create",
             "transitions": [{"id": "s", "to": "owner_sends_internal", "label": "Submit", "action": "submit"}]},
            {"id": "owner_sends_internal", "type": "approval", "name": "Owner Sends for Internal Review", "module": "approval",
             "transitions": [{"id": "x", "to": "internal_review", "label": "Send", "action": "send"}]},
            {"id": "internal_review", "type": "parallel", "name": "Internal Review", "module": "review",
             "config": {"quorum": {"mode": "all"}, "on_reject": "fail_fast", "branches": [
                 {"id": "il", "name": "Legal", "kind": "action"}, {"id": "if_", "name": "Fin", "kind": "action"}]},
             "transitions": [{"id": "ok", "to": "cro_gate", "label": "ok", "action": "quorum_met"},
                             {"id": "no", "to": "draft", "label": "back", "action": "quorum_failed"}]},
            {"id": "cro_gate", "type": "decision", "name": "CRO involved?",
             "transitions": [{"id": "y", "to": "owner_sends_cro", "label": "Yes", "action": "auto",
                              "condition": {"all": [{"field": "has_cro", "op": "is_true"}]}},
                             {"id": "n", "to": "owner_sends_site", "label": "No", "action": "auto"}]},
            {"id": "owner_sends_cro", "type": "approval", "name": "Owner Sends for CRO Review", "module": "approval",
             "transitions": [{"id": "x", "to": "cro_review", "label": "Send", "action": "send"}]},
            {"id": "cro_review", "type": "parallel", "name": "CRO Review", "module": "review",
             "config": {"quorum": {"mode": "all"}, "on_reject": "fail_fast", "branches": [
                 {"id": "cl", "name": "CRO Legal", "kind": "action"}, {"id": "cf", "name": "CRO Fin", "kind": "action"}]},
             "transitions": [{"id": "ok", "to": "cro_sign", "label": "ok", "action": "quorum_met"},
                             {"id": "no", "to": "draft", "label": "back", "action": "quorum_failed"}]},
            {"id": "cro_sign", "type": "ordered_signing", "name": "CRO Signature", "module": "signing",
             "config": {"signers": [{"id": "cro_signatory", "name": "CRO"}]},
             "transitions": [{"id": "ok", "to": "owner_sends_vp_cro", "label": "signed", "action": "all_signed"}]},
            {"id": "owner_sends_vp_cro", "type": "approval", "name": "Owner Sends to VP (CRO Path)", "module": "approval",
             "transitions": [{"id": "x", "to": "vp_cro", "label": "Send", "action": "send"}]},
            {"id": "vp_cro", "type": "ordered_signing", "name": "VP Final (CRO)", "module": "signing",
             "config": {"signers": [{"id": "vp", "name": "VP"}]},
             "transitions": [{"id": "ok", "to": "cro_done", "label": "signed", "action": "all_signed"}]},
            {"id": "cro_done", "type": "terminal", "name": "Final Ready (CRO)", "transitions": []},   # SKIPS distribute
            {"id": "owner_sends_site", "type": "approval", "name": "Owner Sends for Site Review", "module": "approval",
             "transitions": [{"id": "x", "to": "site_review", "label": "Send", "action": "send"}]},
            {"id": "site_review", "type": "parallel", "name": "Site Review", "module": "review",
             "config": {"quorum": {"mode": "all"}, "on_reject": "fail_fast", "branches": [
                 {"id": "sl", "name": "Site Legal", "kind": "action"}, {"id": "sf", "name": "Site Fin", "kind": "action"}]},
             "transitions": [{"id": "ok", "to": "site_sign", "label": "ok", "action": "quorum_met"},
                             {"id": "no", "to": "draft", "label": "back", "action": "quorum_failed"}]},
            {"id": "site_sign", "type": "ordered_signing", "name": "Site Director & PI", "module": "signing",
             "config": {"signers": [{"id": "site_director", "name": "Director"}, {"id": "pi", "name": "PI"}]},
             "transitions": [{"id": "ok", "to": "owner_sends_vp_site", "label": "signed", "action": "all_signed"}]},
            {"id": "owner_sends_vp_site", "type": "approval", "name": "Owner Sends to VP (Site Path)", "module": "approval",
             "transitions": [{"id": "x", "to": "vp_site", "label": "Send", "action": "send"}]},
            {"id": "vp_site", "type": "ordered_signing", "name": "VP Final (Site)", "module": "signing",
             "config": {"signers": [{"id": "vp", "name": "VP"}]},
             "transitions": [{"id": "ok", "to": "owner_final", "label": "signed", "action": "all_signed"}]},
            {"id": "owner_final", "type": "approval", "name": "Owner Final Review & Distribute", "module": "approval",
             "transitions": [{"id": "d", "to": "distribute", "label": "Distribute", "action": "distribute"}]},
            {"id": "distribute", "type": "broadcast", "name": "Distribute Final Copy", "module": "broadcast",
             "config": {"recipients": [{"id": "pi", "name": "PI"}]},
             "transitions": [{"id": "b", "to": "complete", "label": "done", "action": "broadcast_done"}]},
            {"id": "complete", "type": "terminal", "name": "Complete", "transitions": []},
        ],
    }


async def main():
    results = []
    settings.workflow_unified = True

    fixed = gen.normalize_draft(copy.deepcopy(heavy_broken()))
    steps = {s["id"]: s for s in fixed["steps"]}

    # BUG 1: all five "Owner sends for/to X" review/signing steps folded; owner_final kept.
    sent = ["owner_sends_internal", "owner_sends_cro", "owner_sends_site", "owner_sends_vp_cro", "owner_sends_vp_site"]
    assert all(x not in steps for x in sent), [x for x in sent if x in steps]
    assert "owner_final" in steps, "the final owner gate before broadcast is KEPT"
    # predecessors rewired straight into the review/signing steps
    assert steps["draft"]["transitions"][0]["to"] == "internal_review"
    assert {t["to"] for t in steps["cro_gate"]["transitions"]} == {"cro_review", "site_review"}
    assert steps["cro_sign"]["transitions"][0]["to"] == "vp_cro"            # owner_sends_vp_cro folded
    assert steps["vp_cro"]["config"].get("handoff") == "owner_gated"        # signing target -> owner_gated
    results.append(("BUG1: 'Owner sends for/to X' (review & signing) folded; final owner gate kept",
                    "5 folded, owner_final kept, predecessors rewired"))

    # BUG 2: the CRO path no longer dead-ends — its terminal is gone and it routes through broadcast.
    assert "cro_done" not in steps, "CRO-path terminal that skipped distribution is removed"
    assert steps["vp_cro"]["transitions"][0]["to"] == "distribute", "CRO path now flows into the broadcast"
    terminals = [s for s in fixed["steps"] if s["type"] == "terminal"]
    assert len(terminals) == 1 and terminals[0]["id"] == "complete", terminals
    results.append(("BUG2: CRO branch routed through distribute; single shared terminal", "vp_cro -> distribute -> complete"))

    # BUG 3: has_cro declared in context_schema AND collected on the draft form.
    schema_keys = {c["key"] for c in fixed.get("context_schema", [])}
    assert "has_cro" in schema_keys, fixed.get("context_schema")
    draft_fields = {f["key"] for f in (steps["draft"].get("config") or {}).get("fields", [])}
    assert "has_cro" in draft_fields, steps["draft"].get("config")
    results.append(("BUG3: decision variable declared in context_schema + collected on draft form",
                    "has_cro in schema + draft.fields"))

    WorkflowDefinitionBody.model_validate(fixed)  # schema-valid

    # BUG 3 (runtime): BOTH branches are reachable — has_cro=true -> CRO path, false -> site path.
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(fixed),
                                                 publish=True, published_by="v")
        u = CurrentUser(id="u", roles=[])
        for has_cro, expect in ((True, "cro_review"), (False, "site_review")):
            subj = f"zz-authfix-{has_cro}"
            async with transactional(db):
                inst = await wf.start_instance(db, KEY, {"has_cro": has_cro}, subject_ref=subj)
            # draft -> submit -> internal_review (parallel) -> approve both -> decision settles
            async with transactional(db):
                await wf.perform_action(db, inst.id, u, "s", {})
            inst = await wf.get_instance(db, inst.id)
            assert inst.current_step == "internal_review", inst.current_step
            acts = await wf.available_actions(db, inst.id, u)
            for a in [a for a in acts if a.action == "approve"]:
                async with transactional(db):
                    await wf.perform_action(db, inst.id, u, a.transition_id, {})
            inst = await wf.get_instance(db, inst.id)
            assert inst.current_step == expect, (f"has_cro={has_cro}", inst.current_step, "expected", expect)
            async with transactional(db):
                await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id=:i"), {"i": inst.id})
                await db.execute(text("DELETE FROM workflow_instances WHERE id=:i"), {"i": inst.id})
        results.append(("BUG3 (runtime): both branches REACHABLE — has_cro=true->CRO, false->Site", "both routed"))

        d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": KEY})).fetchone()
        async with transactional(db):
            await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
            await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})

    settings.workflow_unified = False
    print("=" * 92)
    print("AUTHORING FIXES (Bugs 1-3) — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

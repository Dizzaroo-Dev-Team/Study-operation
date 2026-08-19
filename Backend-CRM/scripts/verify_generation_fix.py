"""
Verify PART B — the generation fix: the draft NORMALIZER repairs the exact broken
shape the diagnosis found (signature-type signing, "Send for X" approval steps,
module-less parallel review), and generate_workflow returns a runnable definition.
LLM seam monkeypatched to the broken output, so this tests OUR repair logic, then the
repaired body is PUBLISHED + RUN to prove it invokes the modules. Throwaway; cleaned.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.modules.workflows import generate as gen  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

KEY = "tpl:zz-genfix"


def broken_body():
    """The exact shape from the diagnosed bad definition (def 46)."""
    return {
        "key": KEY, "name": "Broken", "start_step": "draft",
        "context_schema": [{"key": "has_cro", "label": "CRO?", "type": "boolean"}],
        "steps": [
            {"id": "draft", "type": "form", "name": "Main User Creates Document", "module": "document_create",
             "transitions": [{"id": "submit", "to": "review", "label": "Submit", "action": "submit"}]},
            {"id": "review", "type": "parallel", "name": "Legal and Financial Review",  # NO module
             "config": {"quorum": {"mode": "all"}, "on_reject": "fail_fast", "branches": [
                 {"id": "legal", "name": "Legal", "kind": "action"}, {"id": "fin", "name": "Financial", "kind": "action"}]},
             "transitions": [{"id": "ok", "to": "cro", "label": "Both", "action": "quorum_met"},
                             {"id": "no", "to": "draft", "label": "Back", "action": "quorum_failed"}]},
            {"id": "cro", "type": "decision", "name": "Is a CRO involved?",
             "transitions": [{"id": "y", "to": "cro_review", "label": "Yes", "action": "auto",
                              "condition": {"all": [{"field": "has_cro", "op": "is_true"}]}},
                             {"id": "n", "to": "handoff_director", "label": "No", "action": "auto"}]},
            {"id": "cro_review", "type": "parallel", "name": "CRO Legal and Financial Review",  # NO module
             "config": {"quorum": {"mode": "all"}, "on_reject": "fail_fast", "branches": [
                 {"id": "cl", "name": "CRO Legal", "kind": "action"}, {"id": "cf", "name": "CRO Fin", "kind": "action"}]},
             "transitions": [{"id": "cok", "to": "handoff_director", "label": "ok", "action": "quorum_met"},
                             {"id": "cno", "to": "draft", "label": "back", "action": "quorum_failed"}]},
            {"id": "handoff_director", "type": "approval", "name": "Send for Director's Signature", "module": "approval",
             "transitions": [{"id": "sd", "to": "director_sign", "label": "Send", "action": "send"}]},
            {"id": "director_sign", "type": "signature", "name": "Director Signs", "module": "signing",  # WRONG type
             "assignee": {"type": "role", "value": "director_signer"},
             "transitions": [{"id": "ds", "to": "handoff_pi", "label": "Signed", "action": "sign"}]},
            {"id": "handoff_pi", "type": "approval", "name": "Send for PI's Signature", "module": "approval",
             "transitions": [{"id": "sp", "to": "pi_sign", "label": "Send", "action": "send"}]},
            {"id": "pi_sign", "type": "signature", "name": "PI Signs", "module": "signing",  # WRONG type
             "assignee": {"type": "role", "value": "pi_signer"},
             "transitions": [{"id": "ps", "to": "handoff_remaining", "label": "Signed", "action": "sign"}]},
            {"id": "handoff_remaining", "type": "approval", "name": "Send for Remaining Signers", "module": "approval",
             "transitions": [{"id": "sr", "to": "remaining", "label": "Send", "action": "send"}]},
            {"id": "remaining", "type": "parallel", "name": "Remaining Signers Sign in Parallel",  # NO module
             "config": {"quorum": {"mode": "all"}, "on_reject": "count", "branches": [
                 {"id": "a", "name": "Signer A", "kind": "action"}, {"id": "b", "name": "Signer B", "kind": "action"}]},
             "transitions": [{"id": "rok", "to": "distribute", "label": "all", "action": "quorum_met"},
                             {"id": "rno", "to": "draft", "label": "back", "action": "quorum_failed"}]},
            {"id": "distribute", "type": "broadcast", "name": "Distribute Final Copy", "module": "broadcast",
             "config": {"recipients": [{"id": "pi", "name": "PI"}, {"id": "sm", "name": "Site Mgr"}]},
             "transitions": [{"id": "d", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


def fake(payload):
    async def _f(prompt):
        return payload
    return _f


async def main():
    results = []
    settings.workflow_unified = True

    # ── 1. NORMALIZER repairs the broken shape ──
    import copy
    fixed = gen.normalize_draft(copy.deepcopy(broken_body()))
    steps = {s["id"]: s for s in fixed["steps"]}
    # signature -> ordered_signing + signers + module signing + all_signed exit
    for sid in ("director_sign", "pi_sign"):
        assert steps[sid]["type"] == "ordered_signing" and steps[sid]["module"] == "signing", steps[sid]
        assert steps[sid]["config"]["signers"], steps[sid]
        assert any(t["action"] == "all_signed" for t in steps[sid]["transitions"]), steps[sid]
    # parallel reviews tagged review; parallel remaining tagged signing
    assert steps["review"]["module"] == "review" and steps["cro_review"]["module"] == "review"
    assert steps["remaining"]["module"] == "signing"
    # "Send for X" steps folded away
    assert "handoff_director" not in steps and "handoff_pi" not in steps and "handoff_remaining" not in steps
    # owner-gating moved into the signing steps; predecessors rewired
    assert steps["director_sign"]["config"].get("handoff") == "owner_gated"
    assert any(t["to"] == "director_sign" for t in steps["cro"]["transitions"]), "cro now points at signing"
    assert any(t["to"] == "pi_sign" for t in steps["director_sign"]["transitions"]), "director -> pi rewired"
    WorkflowDefinitionBody.model_validate(fixed)  # schema-valid
    results.append(("Normalizer: signature->ordered_signing, modules fixed, send-steps folded, schema-valid",
                    "director/pi=ordered_signing+signing; reviews=review; remaining=signing"))

    # ── 2. generate_workflow runs the normalizer end-to-end ──
    gen._llm_generate_json = fake({"body": broken_body(), "assumptions": ["x"], "summary": "ok"})
    g = await gen.generate_workflow("from diagram", key=KEY)
    gs = {s["id"]: s for s in g["body"]["steps"]}
    assert not any(s["type"] == "signature" for s in g["body"]["steps"]), "no bare signature steps survive"
    assert gs["review"]["module"] == "review" and gs["director_sign"]["module"] == "signing"
    results.append(("generate_workflow: returns the repaired, runnable definition", "no signature steps; modules set"))

    # ── 3. unclassifiable module-less parallel -> asks instead of shipping broken ──
    amb = broken_body()
    amb["steps"][1].pop("module", None)
    amb["steps"][1]["name"] = "Committee Step"   # neither 'review' nor 'sign'
    gen._llm_generate_json = fake({"body": amb, "assumptions": [], "summary": "s"})
    g2 = await gen.generate_workflow("x", key=KEY)
    assert g2.get("needs_clarification"), g2
    results.append(("Unclassifiable module-less step -> clarifying question (not a broken workflow)",
                    g2["needs_clarification"][:40] + "…"))

    # ── 4. LOCK & RUN the repaired def: publish, start, advance into review ──
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(fixed),
                                                 publish=True, published_by="v")
        async with transactional(db):
            inst = await wf.start_instance(db, KEY, {"agreement_id": "zz-genfix", "has_cro": False}, subject_ref="zz-genfix")
        u = CurrentUser(id="u", roles=[])
        async with transactional(db):
            await wf.perform_action(db, inst.id, u, "submit", {})
        inst = await wf.get_instance(db, inst.id)
        assert inst.current_step == "review", inst.current_step
        verbs = {a.action for a in await wf.available_actions(db, inst.id, u)}
        assert verbs and "all_signed" not in verbs, verbs   # at review you review, not sign
        results.append(("Repaired def publishes, starts, and reaches the parallel review step", "draft->review"))
        await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref='zz-genfix')"))
        await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref='zz-genfix'"))
        d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": KEY})).fetchone()
        if d:
            await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
            await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
        await db.commit()

    settings.workflow_unified = False
    print("=" * 92)
    print("GENERATION FIX (Part B) — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

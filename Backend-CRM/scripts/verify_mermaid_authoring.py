"""
Verify the MERMAID-as-input authoring path (run in backend container; LLM seams
monkeypatched). Covers:
  * CLARIFY with a pasted Mermaid -> catalog questions PLUS diagram-specific
    free-form questions (node roles / signature order), sanitized + capped.
  * The Mermaid TEXT is folded into the generation prompt.
  * CONFIRM yields JSON with: a decision branch, a parallel review (quorum), an
    ordered_signing that preserves Director-before-PI, a parallel "remaining" signing,
    and a broadcast with recipients — and it VALIDATES + publishes + starts (runs on
    the engine; signing is gated behind review). No business logic is run by the LLM.
"""
import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.modules.workflows import generate as gen  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

captured: dict = {}
KEY = "tpl:zz-mermaid-test"

MERMAID = """flowchart TD
  Draft[Main User Creates Document] --> Review[[Legal + Finance Review]]
  Review -->|Both approve| CRO{Has CRO?}
  Review -.->|discussion| Draft
  CRO -->|Yes| CROReview[[CRO Legal + Finance]]
  CRO -->|No| DirSign[/Director Signs/]
  CROReview --> DirSign
  DirSign --> PISign[/PI Signs/]
  PISign --> Remaining[[Remaining signers]]
  Remaining --> Distribute[(Distribute Final Copy)]
  Distribute --> Done([Done])
"""


def fake(payload):
    async def _f(prompt):
        captured["prompt"] = prompt
        return payload
    return _f


def mermaid_body():
    return {
        "key": KEY, "name": "Mermaid Derived", "start_step": "draft",
        "context_schema": [{"key": "has_cro", "label": "CRO?", "type": "boolean"}],
        "steps": [
            {"id": "draft", "type": "form", "name": "Create Document", "module": "document_create",
             "transitions": [{"id": "submit", "to": "review", "label": "Submit", "action": "submit"}]},
            {"id": "review", "type": "parallel", "name": "Legal + Finance Review", "module": "review",
             "config": {"quorum": {"mode": "all"}, "on_reject": "count", "branches": [
                 {"id": "legal", "name": "Legal", "kind": "action"},
                 {"id": "finance", "name": "Finance", "kind": "action"}]},
             "transitions": [{"id": "rok", "to": "cro", "label": "Both approve", "action": "quorum_met"},
                             {"id": "rno", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
            {"id": "cro", "type": "decision", "name": "Has CRO?",
             "transitions": [{"id": "yes", "to": "cro_review", "label": "Yes", "action": "auto",
                              "condition": {"all": [{"field": "has_cro", "op": "is_true"}]}},
                             {"id": "no", "to": "sign_main", "label": "No", "action": "auto"}]},
            {"id": "cro_review", "type": "parallel", "name": "CRO Review", "module": "review",
             "config": {"quorum": {"mode": "all"}, "on_reject": "count", "branches": [
                 {"id": "cl", "name": "CRO Legal", "kind": "action"},
                 {"id": "cf", "name": "CRO Finance", "kind": "action"}]},
             "transitions": [{"id": "cok", "to": "sign_main", "label": "Approved", "action": "quorum_met"},
                             {"id": "cno", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
            {"id": "sign_main", "type": "ordered_signing", "name": "Director then PI", "module": "signing",
             "config": {"handoff": "owner_gated", "signers": [
                 {"id": "director", "name": "Director"}, {"id": "pi", "name": "PI"}]},
             "transitions": [{"id": "smdone", "to": "sign_rest", "label": "Signed", "action": "all_signed"}]},
            {"id": "sign_rest", "type": "parallel", "name": "Remaining signers", "module": "signing",
             "config": {"quorum": {"mode": "all"}, "on_reject": "count", "branches": [
                 {"id": "a", "name": "Signer A", "kind": "action"},
                 {"id": "b", "name": "Signer B", "kind": "action"}]},
             "transitions": [{"id": "srok", "to": "distribute", "label": "All signed", "action": "quorum_met"},
                             {"id": "srno", "to": "draft", "label": "Back", "action": "quorum_failed"}]},
            {"id": "distribute", "type": "broadcast", "name": "Distribute Final Copy", "module": "broadcast",
             "config": {"recipients": [{"id": "pi", "name": "PI"}, {"id": "site", "name": "Site Manager"},
                                       {"id": "legal", "name": "Legal"}]},
             "transitions": [{"id": "dist", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def main():
    results = []
    settings.workflow_unified = True

    # ── 1. CLARIFY with a Mermaid: catalog ids + diagram-specific free-form questions ──
    gen._llm_clarify_json = fake({
        "ambiguous_ids": ["who_sends"],
        "extra_questions": [
            {"id": "node_roles", "question": "Which nodes are SIGNING vs REVIEW vs APPROVAL?",
             "options": ["I'll map them", "Legal+Finance=review; Director/PI/Remaining=signing"]},
            {"id": "sig_order", "question": "Confirm signature order: Director, then PI, then the rest?",
             "options": ["Yes", "No — change it"]},
            {"id": "discussion_loop", "question": "The dotted 'discussion' edge — model it as a send-back to draft?",
             "options": ["Yes, send back to draft", "Ignore it"]},
        ],
    })
    c = await gen.clarify_workflow("Review then sign per this diagram.", mermaid=MERMAID)
    ids = [q["id"] for q in c["questions"]]
    assert "who_sends" in ids, ids                          # catalog question kept
    assert "node_roles" in ids and "sig_order" in ids and "discussion_loop" in ids, ids  # diagram questions
    assert all(q["question"] and isinstance(q["options"], list) for q in c["questions"])
    assert "Has CRO?" in captured["prompt"], "the Mermaid text must reach the clarify prompt"
    results.append(("CLARIFY(mermaid): catalog + diagram-specific questions (node roles, signature order, dotted edge)",
                    f"ids={ids}"))

    # ── 2. GENERATE with the Mermaid + answers -> mapped JSON shape ──
    gen._llm_generate_json = fake({"body": mermaid_body(), "assumptions": ["mapped from diagram"],
                                   "summary": "Parallel review, CRO branch, Director then PI sign, remaining sign, distribute."})
    answers = [{"id": "sig_order", "question": "Confirm order", "answer": "Yes — Director then PI then rest"}]
    g = await gen.generate_workflow("from the diagram", key=KEY, answers=answers, mermaid=MERMAID)
    assert "Director Signs" in captured["prompt"] and "Director then PI" in captured["prompt"], "mermaid + answers folded in"
    steps = {s["id"]: s for s in g["body"]["steps"]}
    assert steps["cro"]["type"] == "decision", "decision branch present"
    assert steps["review"]["type"] == "parallel" and any(t["action"] == "quorum_met" for t in steps["review"]["transitions"])
    order = [s["id"] for s in steps["sign_main"]["config"]["signers"]]
    assert order == ["director", "pi"], ("ordered_signing preserves Director-before-PI", order)
    assert steps["sign_rest"]["type"] == "parallel", "remaining signers are parallel/quorum"
    assert len(steps["distribute"]["config"]["recipients"]) >= 1 and steps["distribute"]["type"] == "broadcast"
    assert g.get("summary")
    results.append(("GENERATE(mermaid): decision + parallel review + ordered(director->pi) + parallel rest + broadcast",
                    f"signers={order}, recipients={len(steps['distribute']['config']['recipients'])}"))

    # ── 3. LOCK & RUN: it VALIDATES, publishes, starts, and signing is gated behind review ──
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(mermaid_body()),
                                                 publish=True, published_by="verify")
        async with transactional(db):
            inst = await wf.start_instance(db, KEY, {"agreement_id": "zz-mmd", "has_cro": False}, subject_ref="zz-mmd")
        from app.modules.workflows.schemas import CurrentUser
        u = CurrentUser(id="u", roles=[])
        assert inst.current_step == "draft"
        async with transactional(db):
            await wf.perform_action(db, inst.id, u, "submit", {})
        inst = await wf.get_instance(db, inst.id)
        assert inst.current_step == "review", inst.current_step      # at parallel review
        verbs = {a.action for a in await wf.available_actions(db, inst.id, u)}
        assert "all_signed" not in verbs, "cannot sign while at the review step"
        results.append(("LOCK&RUN: schema-valid, published, started; signing gated behind review", "draft->review (no sign)"))

        await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref='zz-mmd')"))
        await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref='zz-mmd'"))
        d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": KEY})).fetchone()
        if d:
            await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
            await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
        await db.commit()

    settings.workflow_unified = False
    print("=" * 92)
    print("MERMAID AUTHORING — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

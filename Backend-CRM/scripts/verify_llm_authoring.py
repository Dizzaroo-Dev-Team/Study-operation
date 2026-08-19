"""
Verify the LLM clarify -> confirm -> lock&run authoring flow (run in backend container).
The two model seams are monkeypatched (no real Gemini call), so this tests OUR logic:
  * CLARIFY returns structured questions for ambiguous prompts, none for clear ones,
    and filters unknown ids.
  * CONFIRM folds the user's ANSWERS into the prompt and returns body + summary; the
    resolved shape honors the answers (sequential -> ordered_signing, parallel ->
    parallel/quorum; review.approve -> signing; review.send_back -> draft).
  * LOCK&RUN: the generated review->sign body publishes, an instance starts, and the
    engine GATES signing behind review (you cannot sign at the review step).
Throwaway definition + instance; cleaned up. No business logic is executed by the LLM.
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

captured: dict = {}


def fake(payload):
    async def _f(prompt):
        captured["prompt"] = prompt
        return payload
    return _f


KEY = "tpl:zz-llm-authoring-test"


def review_sign_body(signers_block, signing_type="ordered_signing", signing_cfg=None):
    return {
        "key": KEY, "name": "Review then Sign", "start_step": "draft", "context_schema": [],
        "steps": [
            {"id": "draft", "type": "form", "name": "Create Document", "module": "document_create",
             "transitions": [{"id": "submit", "to": "review", "label": "Send for review", "action": "submit"}]},
            {"id": "review", "type": "approval", "name": "Legal Review", "module": "review",
             "transitions": [{"id": "ok", "to": "signing", "label": "Approve", "action": "approve"},
                             {"id": "back", "to": "draft", "label": "Send back", "action": "send_back"}]},
            {"id": "signing", "type": signing_type, "name": "Signature", "module": "signing",
             "config": signing_cfg or {"handoff": "owner_gated", "signers": signers_block},
             "transitions": ([{"id": "signed", "to": "end", "label": "All signed", "action": "all_signed"}]
                             if signing_type == "ordered_signing"
                             else [{"id": "ok", "to": "end", "label": "Quorum", "action": "quorum_met"},
                                   {"id": "no", "to": "draft", "label": "Failed", "action": "quorum_failed"}])},
            {"id": "end", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


async def main():
    results = []
    settings.workflow_unified = True

    # ── 1. CLARIFY: ambiguous prompt -> structured questions (unknown id filtered) ──
    gen._llm_clarify_json = fake({"ambiguous_ids": ["signers", "review_vs_signing", "reject_loop", "__bogus__"]})
    c = await gen.clarify_workflow("Set up an agreement workflow with review and signing.")
    ids = [q["id"] for q in c["questions"]]
    assert c["clear"] is False and ids == ["signers", "review_vs_signing", "reject_loop"], (c)
    assert all(q["question"] and q["options"] for q in c["questions"]), "each question has text + options"
    results.append(("CLARIFY: ambiguous prompt -> only valid catalog questions (unknown id dropped)", f"ids={ids}"))

    # ── 2. CLARIFY: clear prompt -> no questions ──
    gen._llm_clarify_json = fake({"ambiguous_ids": []})
    c2 = await gen.clarify_workflow("Review by one legal reviewer, then one signer signs; reviewer can send back.")
    assert c2["clear"] is True and c2["questions"] == [], c2
    results.append(("CLARIFY: clear prompt -> asks nothing", "clear=True"))

    # ── 3. CONFIRM: answers folded into prompt; body + summary; shape honored ──
    seq_body = review_sign_body([{"id": "pi", "name": "PI"}, {"id": "sponsor", "name": "Sponsor"}])
    gen._llm_generate_json = fake({"body": seq_body, "assumptions": ["seq"],
                                   "summary": "One reviewer approves or sends back; then PI signs, then Sponsor."})
    answers = [{"id": "signers", "question": "Who signs, how many, and in what order?",
                "answer": "Two signers in sequence: PI then Sponsor"},
               {"id": "reject_loop", "question": "Send back to draft on rejection?", "answer": "Yes"}]
    g = await gen.generate_workflow("review then sign", key=KEY, answers=answers)
    assert "PI then Sponsor" in captured["prompt"], "answers must be folded into the generation prompt"
    assert g.get("summary"), "summary present for the confirm screen"
    steps = {s["id"]: s for s in g["body"]["steps"]}
    review = steps["review"]
    approve_to = next(t["to"] for t in review["transitions"] if t["action"] == "approve")
    back_to = next(t["to"] for t in review["transitions"] if t["action"] == "send_back")
    assert approve_to == "signing" and back_to == "draft", (approve_to, back_to)
    assert steps["signing"]["module"] == "signing" and steps["draft"]["module"] == "document_create"
    results.append(("CONFIRM: answers honored + body + summary; review.approve->signing, send_back->draft, modules set",
                    f"summary='{g['summary'][:48]}…'"))

    # ── 4. SHAPE: parallel answer -> parallel/quorum body validates ──
    par_body = review_sign_body(None, signing_type="parallel",
                                signing_cfg={"quorum": {"mode": "all"}, "on_reject": "count",
                                             "branches": [{"id": "a", "name": "A", "kind": "action"},
                                                          {"id": "b", "name": "B", "kind": "action"}]})
    gen._llm_generate_json = fake({"body": par_body, "assumptions": ["parallel"], "summary": "Two signers in parallel."})
    gp = await gen.generate_workflow("review then two signers in parallel",
                                     answers=[{"id": "signers", "answer": "Multiple signers in parallel (any order)"}])
    sign = {s["id"]: s for s in gp["body"]["steps"]}["signing"]
    assert sign["type"] == "parallel" and any(t["action"] == "quorum_met" for t in sign["transitions"])
    results.append(("SHAPE: 'parallel' answer -> parallel signing (quorum) validates", "type=parallel"))

    # ── 5. LOCK & RUN: publish the review->sign body, start an instance, prove the
    #      engine GATES signing behind review (cannot sign at the review step). ──
    async with AsyncSessionLocal() as db:
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(seq_body),
                                                 publish=True, published_by="verify")
        async with transactional(db):
            inst = await wf.start_instance(db, KEY, {"agreement_id": "zz-llm"}, subject_ref="zz-llm")
        u = CurrentUser(id="u", roles=[])
        assert inst.current_step == "draft"
        async with transactional(db):
            await wf.perform_action(db, inst.id, u, "submit", {})
        inst = await wf.get_instance(db, inst.id)
        assert inst.current_step == "review", inst.current_step
        acts = await wf.available_actions(db, inst.id, u)
        verbs = {a.action for a in acts}
        assert verbs == {"approve", "send_back"}, verbs            # at review you review — you cannot sign
        assert "all_signed" not in verbs, "signing must NOT be available at the review step"
        async with transactional(db):
            ok = next(a for a in acts if a.action == "approve")
            await wf.perform_action(db, inst.id, u, ok.transition_id, {})
        inst = await wf.get_instance(db, inst.id)
        assert inst.current_step == "signing", inst.current_step    # signing reachable ONLY after approval
        results.append(("LOCK&RUN: published; engine gates signing behind review (sign only after approve)",
                        "draft->review->(approve)->signing"))

        # cleanup
        await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref='zz-llm')"))
        await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref='zz-llm'"))
        d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": KEY})).fetchone()
        if d:
            await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
            await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
        await db.commit()

    settings.workflow_unified = False
    print("=" * 92)
    print("LLM CLARIFY -> CONFIRM -> LOCK&RUN — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

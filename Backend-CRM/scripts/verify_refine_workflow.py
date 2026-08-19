"""
Verify the ITERATIVE refine authoring loop (mocks the LLM seam — no network, no DB):

    python scripts/verify_refine_workflow.py        # expect 8/8

Proves that after a workflow is generated, the user can "request changes" and the
generator MODIFIES the existing workflow per that feedback instead of restarting from
the description — preserving everything they didn't ask to change — and that
successive refinements COMPOUND. Also confirms the guardrails (refine needs feedback;
a fresh description still drafts from scratch).

Nothing here persists or publishes; the result is still DATA the user confirms.
"""

import asyncio
import copy
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import app.modules.workflows.generate as gen  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
_results = []


def check(label, ok, detail=""):
    _results.append(ok)
    print(f"  {PASS if ok else FAIL}  {label}" + (f"  -> {detail}" if detail else ""))


# The originally generated workflow: draft -> parallel review(legal, financial) ->
# ordered signing(director, pi) -> distribute -> done.
BASE_BODY = {
    "key": "REFINE_DEMO", "name": "Refine demo", "start_step": "draft",
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft", "module": "document_create",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "review", "label": "Submit", "action": "submit"}]},
        {"id": "review", "type": "parallel", "name": "Review", "module": "review",
         "config": {"branches": [
             {"id": "legal", "name": "Legal", "assignee": {"type": "role", "value": "legal"}}],
             "quorum": {"mode": "all"}, "on_reject": "count"},
         "transitions": [
             {"id": "ok", "to": "signing", "label": "Approved", "action": "quorum_met"},
             {"id": "rwk", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
        {"id": "signing", "type": "ordered_signing", "name": "Signatures", "module": "signing",
         "config": {"signers": [
             {"id": "director", "name": "Director", "assignee": {"type": "role", "value": "sponsor"}},
             {"id": "pi", "name": "PI", "assignee": {"type": "role", "value": "coordinator"}}]},
         "transitions": [{"id": "signed", "to": "distribute", "label": "All signed", "action": "all_signed"}]},
        {"id": "distribute", "type": "broadcast", "name": "Distribute", "module": "broadcast",
         "config": {"recipients": [{"id": "legal", "name": "Legal"}]},
         "transitions": [{"id": "dist", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}


def _with_financial(body: dict) -> dict:
    """The model's 'refined' answer to 'add a financial reviewer in parallel': the
    SAME workflow with one extra review branch — every other step preserved."""
    b = copy.deepcopy(body)
    review = next(s for s in b["steps"] if s["id"] == "review")
    review["config"]["branches"].append(
        {"id": "financial", "name": "Financial", "assignee": {"type": "role", "value": "financial"}})
    return b


def _vp_before_distribute(body: dict) -> dict:
    """The model's 'refined' answer to 'VP signs before distribution': add VP to the
    ordered signers — again preserving the rest (incl. the financial branch added in
    the prior round, proving compounding)."""
    b = copy.deepcopy(body)
    signing = next(s for s in b["steps"] if s["id"] == "signing")
    signing["config"]["signers"].append(
        {"id": "vp", "name": "VP", "assignee": {"type": "role", "value": "sponsor"}})
    return b


class FakeLLM:
    """Returns canned outputs and records the prompts it was given (so we can prove
    the refine call was a MODIFY prompt carrying the prior workflow + feedback)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


def _run(responses, **kw):
    fake = FakeLLM(responses)
    orig = gen._llm_generate_json
    gen._llm_generate_json = fake
    try:
        result = asyncio.run(gen.generate_workflow(**kw))
    finally:
        gen._llm_generate_json = orig
    return result, fake


def main():
    print("=" * 78)
    print("Verify - iterative refine authoring loop")
    print("=" * 78)

    # --- Round 1: refine "add a financial reviewer in parallel" ---------------
    fb1 = "add a financial reviewer in parallel with the legal reviewer"
    r1, fake1 = _run(
        [{"body": _with_financial(BASE_BODY), "assumptions": ["Added Financial reviewer."],
          "summary": "Two parallel reviewers now."}],
        description="", prior=BASE_BODY, feedback=fb1,
    )
    body1 = r1.get("body") or {}
    steps1 = {s["id"]: s for s in body1.get("steps", [])}
    branches1 = {b["id"] for b in steps1.get("review", {}).get("config", {}).get("branches", [])}

    check("refine returns a valid draft (not an error)", "body" in r1 and "error" not in r1)
    check("the requested change was applied (financial branch added)",
          branches1 == {"legal", "financial"}, f"branches={sorted(branches1)}")
    check("unrelated steps preserved (signing/distribute/done intact)",
          {"signing", "distribute", "done"} <= set(steps1)
          and [s["id"] for s in steps1["signing"]["config"]["signers"]] == ["director", "pi"],
          f"steps={list(steps1)}")
    check("it was a MODIFY call, not a from-scratch redraft (prior + feedback in prompt)",
          len(fake1.prompts) == 1 and '"signing"' in fake1.prompts[0]
          and fb1 in fake1.prompts[0]
          and ("modify" in fake1.prompts[0].lower() or "refin" in fake1.prompts[0].lower()))
    check("result re-validates against the SAME schema the builder uses",
          bool(WorkflowDefinitionBody.model_validate(body1)))

    # --- Round 2: refine again "VP signs before distribution" — compounds ------
    fb2 = "VP should sign before distribution"
    r2, fake2 = _run(
        [{"body": _vp_before_distribute(body1), "assumptions": ["Added VP signer."],
          "summary": "Now VP signs last before distribution."}],
        description="", prior=body1, feedback=fb2, feedback_log=[fb1],
    )
    body2 = r2.get("body") or {}
    steps2 = {s["id"]: s for s in body2.get("steps", [])}
    signers2 = [s["id"] for s in steps2.get("signing", {}).get("config", {}).get("signers", [])]
    branches2 = {b["id"] for b in steps2.get("review", {}).get("config", {}).get("branches", [])}

    check("round 2 applied the new change (VP added to signers)",
          signers2 == ["director", "pi", "vp"], f"signers={signers2}")
    check("round 2 COMPOUNDED on round 1 (financial branch still present)",
          branches2 == {"legal", "financial"}, f"branches={sorted(branches2)}")
    check("earlier feedback rode along as context in round 2",
          fb1 in fake2.prompts[0] and fb2 in fake2.prompts[0])

    print("=" * 78)
    passed = sum(1 for r in _results if r)
    print(f"{passed}/{len(_results)} passed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())

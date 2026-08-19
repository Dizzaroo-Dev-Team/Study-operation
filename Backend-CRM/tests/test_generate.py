"""
test_generate.py
================

LLM auto-create: tests for the workflow generation service. The LLM client is
MOCKED (no network) by monkeypatching the single seam
`app.modules.workflows.generate._llm_generate_json` with canned responses.

Covers:
  a) the parsed output passes WorkflowDefinitionBody validation
  b) it contains a parallel step, an ordered_signing step, and a broadcast step
  c) repair loop: a first invalid response (bad schema, then bad JSON) is fed back
     and the service succeeds on retry; all-invalid yields a clear error
  d) a vague description yields needs_clarification, not a guess
  + the validated body WALKS end to end through the pure engine
  + the service never persists/publishes (returns a draft only)

Run:
    pytest tests/test_generate.py -v
    python  tests/test_generate.py
"""

import asyncio
import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

import app.modules.workflows.generate as gen  # noqa: E402
from app.modules.workflows.engine import WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid: str) -> CurrentUser:
    return CurrentUser(id=uid, roles=[])


# --- canned LLM outputs ----------------------------------------------------
# For: "draft, then legal and finance review in parallel (both must approve),
# then site director signs, then PI signs, then VP signs, then notify everyone".
VALID_BODY = {
    "key": "GEN_TEST", "name": "Generated Flow", "start_step": "draft",
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "review", "label": "Submit", "action": "submit"}]},
        {"id": "review", "type": "parallel", "name": "Legal & Finance Review",
         "config": {"branches": [
             {"id": "legal", "name": "Legal", "assignee": {"type": "role", "value": "legal"}},
             {"id": "financial", "name": "Finance", "assignee": {"type": "role", "value": "financial"}}],
             "quorum": {"mode": "all"}, "on_reject": "count"},
         "transitions": [
             {"id": "ok", "to": "signing", "label": "Both approved", "action": "quorum_met"},
             {"id": "rwk", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
        {"id": "signing", "type": "ordered_signing", "name": "Signatures",
         "config": {"signers": [
             {"id": "director", "name": "Site Director", "assignee": {"type": "role", "value": "sponsor"}},
             {"id": "pi", "name": "PI", "assignee": {"type": "role", "value": "coordinator"}},
             {"id": "vp", "name": "VP", "assignee": {"type": "role", "value": "sponsor"}}]},
         "transitions": [{"id": "signed", "to": "distribute", "label": "All signed", "action": "all_signed"}]},
        {"id": "distribute", "type": "broadcast", "name": "Notify Everyone",
         "config": {"recipients": [
             {"id": "legal", "name": "Legal"}, {"id": "financial", "name": "Finance"},
             {"id": "director", "name": "Site Director"}, {"id": "pi", "name": "PI"},
             {"id": "vp", "name": "VP"}]},
         "transitions": [{"id": "done_t", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}
VALID_RESPONSE = {
    "body": VALID_BODY,
    "assumptions": [
        "Legal and Finance must BOTH approve (quorum: all).",
        "Signing order: Site Director, then PI, then VP.",
        "On completion, the final copy is broadcast to everyone involved.",
    ],
}

# Schema-invalid: no terminal step -> WorkflowDefinitionBody validation fails.
INVALID_SCHEMA_RESPONSE = {
    "body": {"key": "BAD", "name": "Bad", "start_step": "draft", "steps": [
        {"id": "draft", "type": "form", "name": "Draft",
         "transitions": [{"id": "s", "to": "review", "label": "s", "action": "submit"}]},
        {"id": "review", "type": "approval", "name": "Review",
         "transitions": [{"id": "a", "to": "draft", "label": "a", "action": "approve"}]},
    ]},
    "assumptions": [],
}

NEEDS_CLARIFICATION_RESPONSE = {
    "needs_clarification": "What kind of document is this, and who are the required approvers and signers?"
}


# --- harness: monkeypatch the single LLM seam with canned responses --------
class FakeLLM:
    def __init__(self, responses):
        self.responses = list(responses)
        self.prompts = []

    async def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.responses.pop(0)


def run_gen(responses, description="make a flow", **kw):
    fake = FakeLLM(responses)
    orig = gen._llm_generate_json
    gen._llm_generate_json = fake
    try:
        result = asyncio.run(gen.generate_workflow(description, **kw))
    finally:
        gen._llm_generate_json = orig
    return result, fake


def _walk(body: dict):
    """Walk the generated definition end to end through the pure engine."""
    eng = WorkflowEngine(WorkflowDefinitionBody.model_validate(body), enforce_roles=False)
    r = eng.start({})
    assert r.step_id == "draft"
    r = eng.perform("draft", "submit", r.context, U("a"))
    assert r.step_id == "review"
    r = eng.perform("review", "legal:approve", r.context, U("l"))
    r = eng.perform("review", "financial:approve", r.context, U("f"))   # quorum -> signing
    assert r.step_id == "signing", r.step_id
    r = eng.perform("signing", "director:sign", r.context, U("d"))
    r = eng.perform("signing", "pi:sign", r.context, U("p"))
    r = eng.perform("signing", "vp:sign", r.context, U("v"))            # -> broadcast -> done
    assert r.step_id == "done" and r.is_terminal, r.step_id
    assert set(r.notified) == {"legal", "financial", "director", "pi", "vp"}
    return r


# ---------------------------------------------------------------------------
# a) parsed output passes validation
# ---------------------------------------------------------------------------
def test_a_output_validates():
    result, fake = run_gen([VALID_RESPONSE], key="GEN_TEST", name="Generated Flow")
    assert "body" in result and "error" not in result
    # Re-validate independently (the SAME schema the builder enforces).
    WorkflowDefinitionBody.model_validate(result["body"])
    assert result["assumptions"] and isinstance(result["assumptions"], list)
    assert len(fake.responses) == 0  # consumed exactly one LLM call


# ---------------------------------------------------------------------------
# b) contains parallel + ordered_signing + broadcast
# ---------------------------------------------------------------------------
def test_b_contains_block_types():
    result, _ = run_gen([VALID_RESPONSE])
    steps = {s["id"]: s for s in result["body"]["steps"]}
    types = {s["type"] for s in steps.values()}
    assert {"parallel", "ordered_signing", "broadcast"} <= types, types
    # parallel review has legal + financial branches
    review = steps["review"]
    assert {b["id"] for b in review["config"]["branches"]} == {"legal", "financial"}
    # ordered signing is director -> pi -> vp
    assert [s["id"] for s in steps["signing"]["config"]["signers"]] == ["director", "pi", "vp"]
    # broadcast has recipients
    assert len(steps["distribute"]["config"]["recipients"]) == 5


# ---------------------------------------------------------------------------
# c) repair loop
# ---------------------------------------------------------------------------
def test_c1_repair_after_invalid_schema():
    result, fake = run_gen([INVALID_SCHEMA_RESPONSE, VALID_RESPONSE])
    assert "body" in result and "error" not in result
    assert len(fake.prompts) == 2                       # one repair retry
    # The validation error was fed back into the second prompt.
    assert "terminal" in fake.prompts[1].lower()
    WorkflowDefinitionBody.model_validate(result["body"])


def test_c2_repair_after_invalid_json():
    # `None` simulates the client failing to parse JSON.
    result, fake = run_gen([None, VALID_RESPONSE])
    assert "body" in result
    assert len(fake.prompts) == 2


def test_c3_all_invalid_returns_error():
    # 3 attempts (initial + 2 retries) all invalid -> clear error, never junk.
    result, fake = run_gen([INVALID_SCHEMA_RESPONSE] * 3)
    assert "body" not in result
    assert "error" in result and "valid workflow" in result["error"].lower()
    assert len(fake.prompts) == 3


# ---------------------------------------------------------------------------
# d) vague description -> needs_clarification (not a guess)
# ---------------------------------------------------------------------------
def test_d_vague_needs_clarification():
    result, fake = run_gen([NEEDS_CLARIFICATION_RESPONSE], description="make me a thing")
    assert "needs_clarification" in result
    assert "body" not in result and "error" not in result
    assert len(fake.prompts) == 1  # no wasted retries on a clarification request


# ---------------------------------------------------------------------------
# engine walk of the generated definition
# ---------------------------------------------------------------------------
def test_e_generated_body_walks():
    result, _ = run_gen([VALID_RESPONSE])
    _walk(result["body"])


# ---------------------------------------------------------------------------
# f) REFINE — modify the existing draft per feedback (NOT a from-scratch regen)
# ---------------------------------------------------------------------------
# The "refined" model output = VALID_BODY with a THIRD review branch added (as if the
# user said "add a compliance reviewer in parallel"). The prior workflow is otherwise
# preserved — that's what we assert (plus that the prompt was a MODIFY prompt).
def _refined_body() -> dict:
    import copy
    b = copy.deepcopy(VALID_BODY)
    review = next(s for s in b["steps"] if s["id"] == "review")
    review["config"]["branches"].append(
        {"id": "compliance", "name": "Compliance", "assignee": {"type": "role", "value": "compliance"}})
    return b


REFINE_RESPONSE = {
    "body": _refined_body(),
    "assumptions": ["Added a Compliance reviewer in parallel with Legal and Finance."],
    "summary": "Same flow, now with three parallel reviewers.",
}


def test_f1_refine_modifies_existing_not_restart():
    fb = "add a compliance reviewer in parallel with the legal reviewer"
    result, fake = run_gen([REFINE_RESPONSE], description="", prior=VALID_BODY, feedback=fb)
    assert "body" in result and "error" not in result
    # The change was applied AND the rest of the workflow is preserved.
    steps = {s["id"]: s for s in result["body"]["steps"]}
    assert {b["id"] for b in steps["review"]["config"]["branches"]} == {"legal", "financial", "compliance"}
    assert {"signing", "distribute", "done"} <= set(steps)          # untouched steps preserved
    # Exactly one LLM call, and it was a MODIFY prompt: it contained the PRIOR JSON
    # (an existing step id) + the user's feedback — i.e. NOT a from-scratch redraft.
    assert len(fake.prompts) == 1
    p = fake.prompts[0]
    assert "modify" in p.lower() or "refin" in p.lower()
    assert '"signing"' in p and "distribute" in p                   # the prior definition was sent
    assert fb in p                                                   # the feedback was sent


def test_f2_refine_compounds_over_rounds():
    # Round 1 result feeds round 2 as `prior`; round 2 adds an even later step.
    r1, _ = run_gen([REFINE_RESPONSE], description="", prior=VALID_BODY,
                    feedback="add a compliance reviewer")
    prior2 = r1["body"]

    import copy
    b2 = copy.deepcopy(prior2)
    b2["name"] = "Generated Flow v2"
    ROUND2 = {"body": b2, "assumptions": ["Renamed."], "summary": "Renamed."}
    r2, fake2 = run_gen([ROUND2], description="", prior=prior2,
                        feedback="rename it", feedback_log=["add a compliance reviewer"])
    # Round 2 built on round 1 (compliance branch still present) — it compounded.
    steps2 = {s["id"]: s for s in r2["body"]["steps"]}
    assert "compliance" in {b["id"] for b in steps2["review"]["config"]["branches"]}
    # The earlier feedback rode along as context.
    assert "add a compliance reviewer" in fake2.prompts[0]


def test_f3_refine_requires_feedback():
    # prior given but no feedback -> a clear error, not a silent regen.
    result, fake = run_gen([VALID_RESPONSE], description="", prior=VALID_BODY, feedback="")
    assert "error" in result and "change" in result["error"].lower()
    assert len(fake.prompts) == 0                                    # never hit the model


# ---------------------------------------------------------------------------
# g) V2 — a description with parallel tracks + an automatic step + a timer now
#    generates a VALID workflow using split/join + job + timer (no "steps.kind").
# ---------------------------------------------------------------------------
# Canned model output for: "two parallel tracks (legal + budget), each reviewed,
# then auto-generate the PDF, final sign-off that escalates after 2 minutes, then
# auto-notify everyone."
V2_GEN_BODY = {
    "key": "V2GEN", "name": "Parallel + Auto + Timer", "start_step": "intake",
    "steps": [
        {"id": "intake", "type": "form", "name": "Intake", "module": "document_create",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "s", "to": "fork", "label": "Submit", "action": "submit"}]},
        {"id": "fork", "type": "split", "name": "Open Tracks", "transitions": [
            {"id": "a", "to": "legal", "label": "Legal", "action": "auto"},
            {"id": "b", "to": "budget", "label": "Budget", "action": "auto"}]},
        {"id": "legal", "type": "approval", "name": "Legal Review", "module": "review",
         "assignee": {"type": "role", "value": "legal"},
         "transitions": [{"id": "la", "to": "merge", "label": "Approve", "action": "approve"}]},
        {"id": "budget", "type": "approval", "name": "Budget Review", "module": "review",
         "assignee": {"type": "role", "value": "financial"},
         "transitions": [{"id": "ba", "to": "merge", "label": "Approve", "action": "approve"}]},
        {"id": "merge", "type": "join", "name": "Merge", "config": {"join": {"mode": "all"}},
         "transitions": [{"id": "m", "to": "render", "label": "Merged", "action": "join_met"}]},
        {"id": "render", "type": "job", "name": "Generate PDF",
         "config": {"job": {"kind": "generate_pdf", "max_attempts": 3, "output": {"document_url": "url"}}},
         "transitions": [
             {"id": "rd", "to": "signoff", "label": "Rendered", "action": "job_done"},
             {"id": "rf", "to": "intake", "label": "Failed", "action": "job_failed"}]},
        {"id": "signoff", "type": "approval", "name": "Final Sign-off", "module": "approval",
         "assignee": {"type": "role", "value": "study_manager"},
         "config": {"timer": {"seconds": 120, "action": "escalate"}},
         "transitions": [
             {"id": "ok", "to": "notify", "label": "Approve", "action": "approve"},
             {"id": "esc", "to": "escalated", "label": "Escalate", "action": "escalate"}]},
        {"id": "escalated", "type": "approval", "name": "Escalated", "module": "approval",
         "assignee": {"type": "role", "value": "medical_monitor"},
         "transitions": [{"id": "eok", "to": "notify", "label": "Approve", "action": "approve"}]},
        {"id": "notify", "type": "job", "name": "Notify Everyone",
         "config": {"job": {"kind": "notify"}},
         "transitions": [{"id": "nd", "to": "done", "label": "Done", "action": "job_done"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}
V2_GEN_RESPONSE = {"body": V2_GEN_BODY,
                   "assumptions": ["Legal and budget tracks run in parallel and merge when both finish.",
                                   "PDF generation and notification are automatic; sign-off escalates after 2 min."],
                   "summary": "Two parallel review tracks, then auto-PDF, a 2-minute-escalating sign-off, and auto-notify."}


def test_g_v2_parallel_job_timer_generates_valid():
    result, _ = run_gen([V2_GEN_RESPONSE],
                        description="two parallel tracks each reviewed, then auto-generate the PDF, "
                                    "final sign-off that escalates after 2 minutes, then notify everyone")
    assert "body" in result and "error" not in result, result
    # Re-validates against the SAME schema the builder enforces — no "steps.kind" error.
    WorkflowDefinitionBody.model_validate(result["body"])
    steps = {s["id"]: s for s in result["body"]["steps"]}
    types = {s["type"] for s in steps.values()}
    # REAL parallel sequences (split/join) + automatic (job) steps present.
    assert {"split", "join", "job"} <= types, types
    # The job steps carry config.job.kind, and the invented "generate_pdf" was
    # mapped to a REGISTERED, runnable handler ("generate_document") — not left as a
    # name with no handler (which is what caused the "no handler registered" failure).
    from app.modules.workflows.jobs import registered_kinds
    assert steps["render"]["config"]["job"]["kind"] == "generate_document"
    assert steps["render"]["config"]["job"]["kind"] in registered_kinds()
    assert steps["notify"]["config"]["job"]["kind"] in registered_kinds()
    assert any(t["action"] == "job_done" for t in steps["render"]["transitions"])
    # The 2-minute escalation timer survived, wired to a matching transition.
    assert steps["signoff"]["config"]["timer"]["seconds"] == 120
    assert steps["signoff"]["config"]["timer"]["action"] == "escalate"
    assert any(t["action"] == "escalate" for t in steps["signoff"]["transitions"])


# ---------------------------------------------------------------------------
# h) Legacy — a simple review->sign STILL generates valid AND simple: no spurious
#    V2 types (split/join/job/wait_message/call) and no timers.
# ---------------------------------------------------------------------------
LEGACY_SIMPLE_BODY = {
    "key": "SIMPLE", "name": "Review then Sign", "start_step": "draft",
    "steps": [
        {"id": "draft", "type": "form", "name": "Create Document", "module": "document_create",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "review", "label": "Send for review", "action": "submit"}]},
        {"id": "review", "type": "approval", "name": "Legal Review", "module": "review",
         "assignee": {"type": "role", "value": "legal"},
         "transitions": [
             {"id": "ok", "to": "signing", "label": "Approve", "action": "approve"},
             {"id": "back", "to": "draft", "label": "Send back", "action": "send_back", "requires_comment": True}]},
        {"id": "signing", "type": "ordered_signing", "name": "Signature", "module": "signing",
         "config": {"signers": [{"id": "signer", "name": "Authorized Signer",
                                 "assignee": {"type": "role", "value": "sponsor"}}]},
         "transitions": [{"id": "signed", "to": "end", "label": "All signed", "action": "all_signed"}]},
        {"id": "end", "type": "terminal", "name": "Done", "transitions": []},
    ],
}
LEGACY_SIMPLE_RESPONSE = {"body": LEGACY_SIMPLE_BODY,
                          "assumptions": ["One legal reviewer, then one signer."],
                          "summary": "A legal reviewer approves, then one authorized signer signs."}


def test_h_legacy_simple_stays_simple():
    result, _ = run_gen([LEGACY_SIMPLE_RESPONSE],
                        description="draft a document, one legal review, then one signature")
    assert "body" in result and "error" not in result, result
    WorkflowDefinitionBody.model_validate(result["body"])
    steps = result["body"]["steps"]
    types = {s["type"] for s in steps}
    # NO over-reach into V2 types for a plain flow.
    assert types.isdisjoint({"split", "join", "job", "wait_message", "call"}), types
    # And no timer was bolted onto any step.
    assert not any("timer" in (s.get("config") or {}) for s in steps)


# ---------------------------------------------------------------------------
# i) Normalizer safety net — the ORIGINAL bug: a job step missing config.job.kind
#    is repaired (kind backfilled + job_done wired) instead of failing "steps.kind".
# ---------------------------------------------------------------------------
def test_i_normalizer_backfills_missing_job_kind():
    body = {
        "key": "JOBFIX", "name": "Job fix", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "transitions": [{"id": "go", "to": "auto", "label": "Go", "action": "submit"}]},
            # job step with NO config.job and a non-job_done forward arrow — the exact
            # shape that previously raised "steps.kind: Field required".
            {"id": "auto", "type": "job", "name": "Send Notifications", "config": {},
             "transitions": [{"id": "nx", "to": "done", "label": "Next", "action": "next"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    fixed = gen.normalize_draft(body)
    WorkflowDefinitionBody.model_validate(fixed)            # would raise before the fix
    job = next(s for s in fixed["steps"] if s["id"] == "auto")
    assert job["config"]["job"]["kind"] == "notify"        # inferred from the name
    assert any(t["action"] == "job_done" for t in job["transitions"])


def test_i2_normalizer_attaches_timer_for_escalation_exit():
    body = {
        "key": "TMRFIX", "name": "Timer fix", "start_step": "rev",
        "steps": [
            {"id": "rev", "type": "approval", "name": "Review", "module": "review",
             "assignee": {"type": "role", "value": "legal"},
             "transitions": [
                 {"id": "ok", "to": "done", "label": "Approve", "action": "approve"},
                 {"id": "esc", "to": "esc2", "label": "Escalate", "action": "escalate"}]},
            {"id": "esc2", "type": "approval", "name": "Escalated", "module": "approval",
             "assignee": {"type": "role", "value": "medical_monitor"},
             "transitions": [{"id": "e", "to": "done", "label": "Approve", "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    fixed = gen.normalize_draft(body)
    WorkflowDefinitionBody.model_validate(fixed)
    rev = next(s for s in fixed["steps"] if s["id"] == "rev")
    assert rev["config"]["timer"]["action"] == "escalate" and rev["config"]["timer"]["seconds"] > 0


def test_j_v2_fewshot_example_is_valid():
    # The few-shot embedded in the system prompt must itself be schema-valid, or it
    # teaches the model a broken shape.
    WorkflowDefinitionBody.model_validate(gen.V2_EXAMPLE_BODY)


_TESTS = [
    ("a) output passes validation", test_a_output_validates,
     "service returns a body that re-validates against WorkflowDefinitionBody"),
    ("b) has parallel+ordered+broadcast", test_b_contains_block_types,
     "parallel(legal,financial) + ordered_signing(director,pi,vp) + broadcast present"),
    ("c1) repair after bad schema", test_c1_repair_after_invalid_schema,
     "invalid (no terminal) -> error fed back -> valid on retry (2 calls)"),
    ("c2) repair after bad JSON", test_c2_repair_after_invalid_json,
     "unparseable response -> retry -> valid (2 calls)"),
    ("c3) all-invalid -> error", test_c3_all_invalid_returns_error,
     "3 invalid attempts -> clear error, never junk"),
    ("d) vague -> needs_clarification", test_d_vague_needs_clarification,
     "vague description returns a clarifying question, not a guess"),
    ("e) generated body walks", test_e_generated_body_walks,
     "draft -> parallel -> ordered sign -> broadcast(5) -> done, end to end"),
    ("f1) refine modifies (no restart)", test_f1_refine_modifies_existing_not_restart,
     "prior + feedback -> modify prompt; change applied, other steps preserved"),
    ("f2) refine compounds", test_f2_refine_compounds_over_rounds,
     "round 2 builds on round 1; earlier feedback passed as context"),
    ("f3) refine needs feedback", test_f3_refine_requires_feedback,
     "prior without feedback -> clear error, model never called"),
    ("g) V2 parallel+job+timer valid", test_g_v2_parallel_job_timer_generates_valid,
     "split/join + job(kind) + 2-min timer generate VALID (no steps.kind error)"),
    ("h) legacy stays simple", test_h_legacy_simple_stays_simple,
     "simple review->sign: valid, no spurious V2 types, no timers"),
    ("i) normalizer backfills job.kind", test_i_normalizer_backfills_missing_job_kind,
     "job step missing config.job.kind -> repaired (kind + job_done), validates"),
    ("i2) normalizer attaches timer", test_i2_normalizer_attaches_timer_for_escalation_exit,
     "an 'escalate' exit with no timer -> timer attached, validates"),
    ("j) V2 few-shot is valid", test_j_v2_fewshot_example_is_valid,
     "the embedded V2 worked example is itself schema-valid"),
]


if __name__ == "__main__":
    print("=" * 78)
    print("Workflow engine — LLM auto-create (generate) tests")
    print("=" * 78)
    failures = 0
    for label, fn, summary in _TESTS:
        try:
            fn()
            print(f"PASS  {label}\n        -> {summary}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {label}\n        -> {type(exc).__name__}: {exc}")
    print("=" * 78)
    print(f"{len(_TESTS) - failures}/{len(_TESTS)} passed")
    sys.exit(1 if failures else 0)

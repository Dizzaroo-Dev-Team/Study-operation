"""
test_parallel.py
================

Test-first coverage for the workflow engine's NEW "parallel review" capability.

The engine is PURE (no DB, no FastAPI), so these tests drive WorkflowEngine
directly with definitions built in code — exactly how the engine runs in prod,
just without the persistence/route layer around it.

Runnable two ways:
    pytest tests/test_parallel.py -v
    python  tests/test_parallel.py          # prints a self-contained report

Covers:
  a) quorum n_of_m 2/3: legal + financial approve -> advances to signature
  b) on_reject="count": legal + financial reject -> quorum_failed path
  c) on_reject="fail_fast": one reject -> immediately quorum_failed
  d) double-vote on the same branch is rejected
  e) a plain sequential flow still runs start-to-finish unchanged
"""

import os
import sys

# Make `app` importable when this file is run directly (python tests/test_parallel.py).
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.workflows.engine import EngineError, WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


# ---------------------------------------------------------------------------
# Definition builders (data, not code — same JSON the builder/seed produce)
# ---------------------------------------------------------------------------
def parallel_def(on_reject: str = "count") -> WorkflowDefinitionBody:
    """draft -> parallel_review[legal, financial, quality; quorum 2-of-3] -> signature -> executed
       (quorum_failed -> rejected)"""
    raw = {
        "key": "PARTEST",
        "name": "Parallel Review Test",
        "start_step": "draft",
        "steps": [
            {
                "id": "draft", "type": "form", "name": "Draft",
                "assignee": {"type": "role", "value": "study_manager"},
                "transitions": [
                    {"id": "submit", "to": "parallel_review", "label": "Submit", "action": "submit"}
                ],
            },
            {
                "id": "parallel_review", "type": "parallel", "name": "Parallel Review",
                "config": {
                    "branches": [
                        {"id": "legal", "name": "Legal",
                         "assignee": {"type": "role", "value": "legal"}},
                        {"id": "financial", "name": "Financial",
                         "assignee": {"type": "role", "value": "financial"}},
                        {"id": "quality", "name": "Quality",
                         "assignee": {"type": "role", "value": "quality"}},
                    ],
                    "quorum": {"mode": "n_of_m", "value": 2},
                    "on_reject": on_reject,
                },
                "transitions": [
                    {"id": "qm", "to": "signature", "label": "Quorum met", "action": "quorum_met"},
                    {"id": "qf", "to": "rejected", "label": "Quorum failed", "action": "quorum_failed"},
                ],
            },
            {
                "id": "signature", "type": "signature", "name": "Signature",
                "assignee": {"type": "role", "value": "coordinator"},
                "transitions": [
                    {"id": "sign", "to": "executed", "label": "Sign", "action": "sign"}
                ],
            },
            {"id": "executed", "type": "terminal", "name": "Executed", "transitions": []},
            {"id": "rejected", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def sequential_def() -> WorkflowDefinitionBody:
    """draft -> approval -> signature -> executed (the unchanged classic path)."""
    raw = {
        "key": "SEQTEST",
        "name": "Sequential Test",
        "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "review", "label": "Submit", "action": "submit"}]},
            {"id": "review", "type": "approval", "name": "Review",
             "assignee": {"type": "role", "value": "legal"},
             "transitions": [{"id": "approve", "to": "signature", "label": "Approve", "action": "approve"}]},
            {"id": "signature", "type": "signature", "name": "Signature",
             "assignee": {"type": "role", "value": "coordinator"},
             "transitions": [{"id": "sign", "to": "executed", "label": "Sign", "action": "sign"}]},
            {"id": "executed", "type": "terminal", "name": "Executed", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


# Open mode (roles off): any authenticated user may act on any open branch.
def U(uid: str) -> CurrentUser:
    return CurrentUser(id=uid, roles=[])


def _engine(on_reject="count") -> WorkflowEngine:
    return WorkflowEngine(parallel_def(on_reject), enforce_roles=False)


def _drive_to_parallel(engine: WorkflowEngine) -> dict:
    """start -> draft (form) -> submit -> parks on the parallel step."""
    r = engine.start({})
    assert r.step_id == "draft", f"expected draft, got {r.step_id}"
    r = engine.perform("draft", "submit", r.context, U("author"))
    assert r.step_id == "parallel_review", f"expected parallel_review, got {r.step_id}"
    return r.context


# ---------------------------------------------------------------------------
# a) quorum 2-of-3 met -> advances to signature
# ---------------------------------------------------------------------------
def test_a_quorum_met_advances():
    eng = _engine("count")
    ctx = _drive_to_parallel(eng)

    # Builder/runner surface: 3 open branches x {approve, reject} = 6 actions.
    acts = eng.available_actions("parallel_review", ctx, U("alice"))
    assert len(acts) == 6, [a.transition_id for a in acts]

    # Legal approves -> still open (1/3).
    r = eng.perform("parallel_review", "legal:approve", ctx, U("alice"))
    assert r.step_id == "parallel_review"
    assert r.context["_branches"]["parallel_review"]["legal"]["decision"] == "approve"
    assert r.context["_branches"]["parallel_review"]["legal"]["actor"] == "alice"

    # Legal branch is now closed -> 2 open branches x 2 = 4 actions.
    acts = eng.available_actions("parallel_review", r.context, U("zara"))
    assert len(acts) == 4 and all("legal:" not in a.transition_id for a in acts)

    # Financial approves -> 2/3 quorum met -> settle past to signature.
    r = eng.perform("parallel_review", "financial:approve", r.context, U("bob"))
    assert r.step_id == "signature", f"expected signature, got {r.step_id}"
    branches = r.context["_branches"]["parallel_review"]
    assert {b: branches[b]["decision"] for b in branches} == {
        "legal": "approve", "financial": "approve"
    }


# ---------------------------------------------------------------------------
# b) on_reject="count": two rejects make quorum impossible -> quorum_failed
# ---------------------------------------------------------------------------
def test_b_count_rejects_to_failed():
    eng = _engine("count")
    ctx = _drive_to_parallel(eng)

    # 1st reject: A=0,R=1,open=2; A+open=2 >= threshold(2) -> still reachable -> open.
    r = eng.perform("parallel_review", "legal:reject", ctx, U("alice"))
    assert r.step_id == "parallel_review", f"expected still open, got {r.step_id}"

    # 2nd reject: A=0,R=2,open=1; A+open=1 < 2 -> impossible -> quorum_failed.
    r = eng.perform("parallel_review", "financial:reject", r.context, U("bob"))
    assert r.step_id == "rejected", f"expected rejected, got {r.step_id}"


# ---------------------------------------------------------------------------
# c) on_reject="fail_fast": one reject -> immediately quorum_failed
# ---------------------------------------------------------------------------
def test_c_fail_fast_one_reject():
    eng = _engine("fail_fast")
    ctx = _drive_to_parallel(eng)

    r = eng.perform("parallel_review", "legal:reject", ctx, U("alice"))
    assert r.step_id == "rejected", f"expected rejected, got {r.step_id}"


# ---------------------------------------------------------------------------
# d) double-vote on the same branch is rejected
# ---------------------------------------------------------------------------
def test_d_double_vote_rejected():
    eng = _engine("count")
    ctx = _drive_to_parallel(eng)

    r = eng.perform("parallel_review", "legal:approve", ctx, U("alice"))
    assert r.step_id == "parallel_review"

    raised = False
    try:
        eng.perform("parallel_review", "legal:reject", r.context, U("mallory"))
    except EngineError as exc:
        raised = True
        msg = str(exc)
    assert raised, "expected EngineError on double-vote of the same branch"
    assert "already been voted" in msg, msg


# ---------------------------------------------------------------------------
# e) plain sequential flow still runs start-to-finish unchanged
# ---------------------------------------------------------------------------
def test_e_sequential_unchanged():
    eng = WorkflowEngine(sequential_def(), enforce_roles=False)
    r = eng.start({})
    assert r.step_id == "draft"
    r = eng.perform("draft", "submit", r.context, U("u"))
    assert r.step_id == "review"
    r = eng.perform("review", "approve", r.context, U("u"))
    assert r.step_id == "signature"
    r = eng.perform("signature", "sign", r.context, U("u"))
    assert r.step_id == "executed" and r.is_terminal
    # No parallel state ever created for a sequential flow.
    assert "_branches" not in r.context


# (label, fn, human-readable summary) — tests assert-only; summary is for the
# script runner below (kept out of the functions so pytest sees clean None returns).
_TESTS = [
    ("a) quorum 2/3 met -> advances", test_a_quorum_met_advances,
     "2/3 approvals -> advanced to 'signature'; votes audited in _branches"),
    ("b) count: 2 rejects -> failed", test_b_count_rejects_to_failed,
     "count mode: 2 rejects make 2/3 unreachable -> 'rejected' (quorum_failed)"),
    ("c) fail_fast: 1 reject -> failed", test_c_fail_fast_one_reject,
     "fail_fast: first reject -> 'rejected' (quorum_failed) immediately"),
    ("d) double-vote rejected", test_d_double_vote_rejected,
     "double-vote on the same branch raises EngineError('already been voted')"),
    ("e) sequential flow unchanged", test_e_sequential_unchanged,
     "draft -> review -> signature -> executed (terminal); no _branches added"),
]


if __name__ == "__main__":
    print("=" * 72)
    print("Workflow engine — parallel review tests")
    print("=" * 72)
    failures = 0
    for label, fn, summary in _TESTS:
        try:
            fn()
            print(f"PASS  {label}\n        -> {summary}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {label}\n        -> {type(exc).__name__}: {exc}")
    print("=" * 72)
    print(f"{len(_TESTS) - failures}/{len(_TESTS)} passed")
    sys.exit(1 if failures else 0)

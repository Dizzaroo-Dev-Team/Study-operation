"""
test_decision.py
================

The general ASK-THE-OWNER decision step. Proves a decision whose branch variable
is UNSET on arrival PAUSES and asks (instead of auto-taking the default and leaving
the other branch unreachable), and that answering routes to the correct branch —
for ANY decision variable, any operator. Nothing here is CRO-specific.

The engine is PURE, so the walk is driven directly (same style as test_full_cta).

Covers:
  a) boolean decision, variable unset -> engine PARKS at the decision; available
     actions expose a single "decide" action to the owner.
  b) answering YES routes to the true branch; answering NO routes to the
     (default) branch — BOTH branches reachable purely by answering.
  c) a SECOND, different variable (numeric "budget > 50k") proves generality:
     60000 -> over branch, 40000 -> under branch.
  d) backward-compat: a variable PRE-SET at start auto-resolves (no pause).
  e) a pure pass-through decision (no condition) never pauses — auto-resolves.
  f) guards: an empty answer is rejected; strict-mode assignee gates who may decide.

Run:
    pytest tests/test_decision.py -v
    python  tests/test_decision.py
"""

import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

from app.modules.workflows.engine import DECIDE_TOKEN, EngineError, WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, StepType, WorkflowDefinitionBody  # noqa: E402


def U(uid: str, roles=None) -> CurrentUser:
    return CurrentUser(id=uid, roles=roles or [])


# ---------------------------------------------------------------------------
# Definitions (general; the decision is the COLLECTION point — nothing pre-sets
# the branch variable on the draft form).
# ---------------------------------------------------------------------------
def boolean_decision_def() -> WorkflowDefinitionBody:
    """draft -> gate(decision on has_cro) -> cro_path | site_path.
    has_cro is NOT collected anywhere up-front, so the gate must ask."""
    raw = {
        "key": "BOOL_DEC", "name": "CRO gate", "start_step": "draft",
        "context_schema": [{"key": "has_cro", "label": "Is a CRO involved?", "type": "boolean"}],
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "gate", "label": "Submit", "action": "submit"}]},
            {"id": "gate", "type": "decision", "name": "Does a CRO exist?",
             "transitions": [
                 {"id": "cro_yes", "to": "cro_path", "label": "CRO exists", "action": "auto",
                  "condition": {"all": [{"field": "has_cro", "op": "is_true"}]}},
                 {"id": "cro_no", "to": "site_path", "label": "No CRO", "action": "auto"}]},
            {"id": "cro_path", "type": "terminal", "name": "CRO path", "transitions": []},
            {"id": "site_path", "type": "terminal", "name": "Site path", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def numeric_decision_def() -> WorkflowDefinitionBody:
    """draft -> gate(decision on budget > 50000) -> over_path | under_path.
    A DIFFERENT variable + operator, to prove the feature is general."""
    raw = {
        "key": "NUM_DEC", "name": "Budget gate", "start_step": "draft",
        "context_schema": [{"key": "budget", "label": "Contract value", "type": "number"}],
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "gate", "label": "Submit", "action": "submit"}]},
            {"id": "gate", "type": "decision", "name": "Is the budget over 50k?",
             "transitions": [
                 {"id": "big", "to": "over_path", "label": "Over 50k", "action": "auto",
                  "condition": {"all": [{"field": "budget", "op": "gt", "value": 50000}]}},
                 {"id": "small", "to": "under_path", "label": "50k or under", "action": "auto"}]},
            {"id": "over_path", "type": "terminal", "name": "Over path", "transitions": []},
            {"id": "under_path", "type": "terminal", "name": "Under path", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def passthrough_decision_def() -> WorkflowDefinitionBody:
    """draft -> gate(decision, NO condition) -> done. Must NOT pause (nothing to ask)."""
    raw = {
        "key": "PASS_DEC", "name": "Pass-through", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "gate", "label": "Submit", "action": "submit"}]},
            {"id": "gate", "type": "decision", "name": "Returned to owner",
             "transitions": [{"id": "go", "to": "done", "label": "Proceed", "action": "auto"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def _to_gate(engine: WorkflowEngine, context=None):
    """start -> submit, returning the StepResult parked at (or past) `gate`. The
    submitter carries the draft's role so this works in strict mode too."""
    r = engine.start(dict(context or {}))
    assert r.step_id == "draft"
    return engine.perform("draft", "submit", r.context, U("owner", roles=["study_manager"]))


# ---------------------------------------------------------------------------
# a) unset variable -> PARK at the decision + a single "decide" action offered
# ---------------------------------------------------------------------------
def test_a_unset_variable_parks_and_asks():
    eng = WorkflowEngine(boolean_decision_def(), enforce_roles=False)
    r = _to_gate(eng)
    assert r.step_id == "gate" and not r.is_terminal, r.step_id
    assert r.step_type == StepType.DECISION
    acts = eng.available_actions("gate", r.context, U("owner"))
    assert len(acts) == 1 and acts[0].action == "decide"
    assert acts[0].transition_id == DECIDE_TOKEN


# ---------------------------------------------------------------------------
# b) answering routes to the matching branch — BOTH reachable
# ---------------------------------------------------------------------------
def test_b_both_branches_reachable_by_answering():
    # YES -> CRO branch
    eng = WorkflowEngine(boolean_decision_def(), enforce_roles=False)
    r = _to_gate(eng)
    r_yes = eng.perform("gate", DECIDE_TOKEN, r.context, U("owner"), payload={"has_cro": True})
    assert r_yes.step_id == "cro_path" and r_yes.is_terminal, r_yes.step_id
    assert r_yes.context["has_cro"] is True
    assert r_yes.vote and r_yes.vote["decision"] == "decided" and r_yes.vote["branch_id"] == "cro_yes"

    # NO -> Site branch (the default branch — now reachable from the UI)
    eng2 = WorkflowEngine(boolean_decision_def(), enforce_roles=False)
    r2 = _to_gate(eng2)
    r_no = eng2.perform("gate", DECIDE_TOKEN, r2.context, U("owner"), payload={"has_cro": False})
    assert r_no.step_id == "site_path" and r_no.is_terminal, r_no.step_id
    assert r_no.vote["branch_id"] == "cro_no"


# ---------------------------------------------------------------------------
# c) a DIFFERENT variable + operator (numeric) — proves generality
# ---------------------------------------------------------------------------
def test_c_second_variable_is_general():
    eng = WorkflowEngine(numeric_decision_def(), enforce_roles=False)
    r = _to_gate(eng)
    assert r.step_id == "gate" and not r.is_terminal     # budget unset -> asked

    over = eng.perform("gate", DECIDE_TOKEN, r.context, U("owner"), payload={"budget": 60000})
    assert over.step_id == "over_path", over.step_id

    eng2 = WorkflowEngine(numeric_decision_def(), enforce_roles=False)
    r2 = _to_gate(eng2)
    under = eng2.perform("gate", DECIDE_TOKEN, r2.context, U("owner"), payload={"budget": 40000})
    assert under.step_id == "under_path", under.step_id


# ---------------------------------------------------------------------------
# d) backward-compat: a variable PRE-SET at start auto-resolves (no pause)
# ---------------------------------------------------------------------------
def test_d_preset_variable_auto_resolves():
    eng = WorkflowEngine(boolean_decision_def(), enforce_roles=False)
    r = _to_gate(eng, context={"has_cro": True})
    # The gate was crossed automatically; no parking, no decide action needed.
    assert r.step_id == "cro_path" and r.is_terminal, r.step_id
    assert eng.available_actions("gate", {"has_cro": True}, U("owner")) == []

    eng2 = WorkflowEngine(boolean_decision_def(), enforce_roles=False)
    r2 = _to_gate(eng2, context={"has_cro": False})
    assert r2.step_id == "site_path" and r2.is_terminal, r2.step_id


# ---------------------------------------------------------------------------
# e) pass-through decision (no condition) never pauses
# ---------------------------------------------------------------------------
def test_e_passthrough_decision_does_not_pause():
    eng = WorkflowEngine(passthrough_decision_def(), enforce_roles=False)
    r = _to_gate(eng)
    assert r.step_id == "done" and r.is_terminal, r.step_id


# ---------------------------------------------------------------------------
# f) guards — empty answer rejected; strict-mode assignee gates the decider
# ---------------------------------------------------------------------------
def test_f1_empty_answer_rejected():
    eng = WorkflowEngine(boolean_decision_def(), enforce_roles=False)
    r = _to_gate(eng)
    try:
        eng.perform("gate", DECIDE_TOKEN, r.context, U("owner"), payload={})
    except EngineError as exc:
        assert "answer" in str(exc).lower()
    else:
        raise AssertionError("expected EngineError for an empty decision answer")


def test_f2_strict_mode_assignee_gates_decider():
    body = boolean_decision_def()
    # Give the gate an explicit role assignee and run in STRICT mode.
    for s in body.steps:
        if s.id == "gate":
            from app.modules.workflows.schemas import Assignee, AssigneeType
            s.assignee = Assignee(type=AssigneeType.ROLE, value="legal")
    eng = WorkflowEngine(body, enforce_roles=True)
    r = _to_gate(eng)
    assert r.step_id == "gate"
    # A non-legal user sees no action and cannot decide.
    assert eng.available_actions("gate", r.context, U("rando", roles=["coordinator"])) == []
    try:
        eng.perform("gate", DECIDE_TOKEN, r.context, U("rando", roles=["coordinator"]), payload={"has_cro": True})
    except EngineError as exc:
        assert "authorized" in str(exc).lower()
    else:
        raise AssertionError("expected EngineError for an unauthorized decider")
    # The legal reviewer can decide.
    legal = eng.available_actions("gate", r.context, U("lego", roles=["legal"]))
    assert len(legal) == 1 and legal[0].action == "decide"
    ok = eng.perform("gate", DECIDE_TOKEN, r.context, U("lego", roles=["legal"]), payload={"has_cro": True})
    assert ok.step_id == "cro_path"


_TESTS = [
    ("a) unset variable parks + asks", test_a_unset_variable_parks_and_asks,
     "decision with an unset variable pauses; one 'decide' action offered to the owner"),
    ("b) both branches reachable", test_b_both_branches_reachable_by_answering,
     "answering Yes -> true branch, No -> default branch (both reachable from the UI)"),
    ("c) second variable is general", test_c_second_variable_is_general,
     "numeric budget>50k: 60000 -> over branch, 40000 -> under branch (no code changes)"),
    ("d) pre-set variable auto-resolves", test_d_preset_variable_auto_resolves,
     "a variable collected up-front routes automatically — no pause (backward compat)"),
    ("e) pass-through never pauses", test_e_passthrough_decision_does_not_pause,
     "a decision with only an unconditional default auto-resolves"),
    ("f1) empty answer rejected", test_f1_empty_answer_rejected,
     "submitting no value is rejected rather than silently taking the default"),
    ("f2) strict-mode assignee gates", test_f2_strict_mode_assignee_gates_decider,
     "with an assignee + strict roles, only the assigned role may answer"),
]


if __name__ == "__main__":
    print("=" * 78)
    print("Workflow engine — general DECISION (ask-the-owner) tests")
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

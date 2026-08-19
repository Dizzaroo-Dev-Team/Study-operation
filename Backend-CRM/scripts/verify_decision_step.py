"""
Verify the general ASK-THE-OWNER decision step (pure engine - runnable anywhere,
no DB needed):

    python scripts/verify_decision_step.py        # expect 9/9

Proves, on a CTA-shaped flow ("Does a CRO exist?") and a SECOND, different variable
("budget over 50k?"), that a decision whose branch variable is UNSET on arrival
PAUSES and asks instead of auto-taking the default - so BOTH branches are reachable
purely by answering at the decision step. Also checks backward-compat (a pre-set
variable auto-resolves) and that a pass-through decision never pauses. Nothing here
is CRO-specific: the variable, the question, and the routing all come from the
definition.

The signing engine, audit, and every other step type are untouched.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.workflows.engine import DECIDE_TOKEN, EngineError, WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, StepType, WorkflowDefinitionBody  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
_results = []


def check(label, ok, detail=""):
    _results.append(ok)
    print(f"  {PASS if ok else FAIL}  {label}" + (f"  -> {detail}" if detail else ""))


def U(uid, roles=None):
    return CurrentUser(id=uid, roles=roles or [])


# CTA-shaped flow: internal review is collapsed to a single form for brevity; the
# decision is the real "Does a CRO exist?" gate, with has_cro NOT pre-collected.
CTA_FLOW = {
    "key": "VERIFY_CTA_DEC", "name": "CTA (CRO gate)", "start_step": "draft",
    "context_schema": [{"key": "has_cro", "label": "Is a CRO involved?", "type": "boolean"}],
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "cro_gate", "label": "Submit", "action": "submit"}]},
        {"id": "cro_gate", "type": "decision", "name": "Does a CRO exist?",
         "transitions": [
             {"id": "cro_yes", "to": "cro_review", "label": "CRO exists", "action": "auto",
              "condition": {"all": [{"field": "has_cro", "op": "is_true"}]}},
             {"id": "cro_no", "to": "site_team", "label": "No CRO", "action": "auto"}]},
        {"id": "cro_review", "type": "terminal", "name": "CRO review", "transitions": []},
        {"id": "site_team", "type": "terminal", "name": "Site team", "transitions": []},
    ],
}

# A DIFFERENT variable + operator, to prove generality with zero code changes.
BUDGET_FLOW = {
    "key": "VERIFY_BUDGET_DEC", "name": "Budget gate", "start_step": "draft",
    "context_schema": [{"key": "budget", "label": "Contract value", "type": "number"}],
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "gate", "label": "Submit", "action": "submit"}]},
        {"id": "gate", "type": "decision", "name": "Is the budget over 50k?",
         "transitions": [
             {"id": "big", "to": "exec_review", "label": "Over 50k", "action": "auto",
              "condition": {"all": [{"field": "budget", "op": "gt", "value": 50000}]}},
             {"id": "small", "to": "fast_track", "label": "50k or under", "action": "auto"}]},
        {"id": "exec_review", "type": "terminal", "name": "Exec review", "transitions": []},
        {"id": "fast_track", "type": "terminal", "name": "Fast track", "transitions": []},
    ],
}

# A pure pass-through decision (no condition) - must never pause.
PASS_FLOW = {
    "key": "VERIFY_PASS_DEC", "name": "Pass-through", "start_step": "draft",
    "steps": [
        {"id": "draft", "type": "form", "name": "Draft",
         "assignee": {"type": "role", "value": "study_manager"},
         "transitions": [{"id": "submit", "to": "gate", "label": "Submit", "action": "submit"}]},
        {"id": "gate", "type": "decision", "name": "Returned to owner",
         "transitions": [{"id": "go", "to": "done", "label": "Proceed", "action": "auto"}]},
        {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
    ],
}


def _to_gate(eng, gate_id, context=None):
    r = eng.start(dict(context or {}))
    return eng.perform("draft", "submit", r.context, U("owner", roles=["study_manager"]))


def main():
    print("=" * 78)
    print("Verify - general ASK-THE-OWNER decision step")
    print("=" * 78)

    # --- CTA flow: pause + ask, both branches reachable -----------------------
    eng = WorkflowEngine(WorkflowDefinitionBody.model_validate(CTA_FLOW), enforce_roles=False)
    parked = _to_gate(eng, "cro_gate")
    check("CTA: unset has_cro PARKS at the decision (does not auto-default)",
          parked.step_id == "cro_gate" and parked.step_type == StepType.DECISION and not parked.is_terminal,
          f"current={parked.step_id}")
    acts = eng.available_actions("cro_gate", parked.context, U("owner"))
    check("CTA: the owner is offered exactly one 'decide' action",
          len(acts) == 1 and acts[0].action == "decide" and acts[0].transition_id == DECIDE_TOKEN,
          f"actions={[a.action for a in acts]}")

    yes = eng.perform("cro_gate", DECIDE_TOKEN, parked.context, U("owner"), payload={"has_cro": True})
    check("CTA: answering YES routes to the CRO branch",
          yes.step_id == "cro_review", f"-> {yes.step_id}")

    eng2 = WorkflowEngine(WorkflowDefinitionBody.model_validate(CTA_FLOW), enforce_roles=False)
    parked2 = _to_gate(eng2, "cro_gate")
    no = eng2.perform("cro_gate", DECIDE_TOKEN, parked2.context, U("owner"), payload={"has_cro": False})
    check("CTA: answering NO routes to the Site branch (the once-unreachable default)",
          no.step_id == "site_team", f"-> {no.step_id}")
    check("CTA: the answer is recorded (vote=decided + chosen branch)",
          bool(no.vote) and no.vote["decision"] == "decided" and no.vote["branch_id"] == "cro_no",
          f"vote={no.vote and no.vote.get('branch_id')}")

    # --- Backward-compat: a pre-set variable auto-resolves --------------------
    eng3 = WorkflowEngine(WorkflowDefinitionBody.model_validate(CTA_FLOW), enforce_roles=False)
    pre = _to_gate(eng3, "cro_gate", context={"has_cro": True})
    check("CTA: has_cro pre-set at draft AUTO-resolves (no pause) - backward compatible",
          pre.step_id == "cro_review" and pre.is_terminal, f"-> {pre.step_id}")

    # --- Second variable proves generality ------------------------------------
    engb = WorkflowEngine(WorkflowDefinitionBody.model_validate(BUDGET_FLOW), enforce_roles=False)
    pb = _to_gate(engb, "gate")
    over = engb.perform("gate", DECIDE_TOKEN, pb.context, U("owner"), payload={"budget": 60000})
    engb2 = WorkflowEngine(WorkflowDefinitionBody.model_validate(BUDGET_FLOW), enforce_roles=False)
    pb2 = _to_gate(engb2, "gate")
    under = engb2.perform("gate", DECIDE_TOKEN, pb2.context, U("owner"), payload={"budget": 40000})
    check("GENERAL: a DIFFERENT variable (budget>50k) pauses + asks", pb.step_id == "gate", f"current={pb.step_id}")
    check("GENERAL: 60000 -> over branch, 40000 -> under branch (no code changes)",
          over.step_id == "exec_review" and under.step_id == "fast_track",
          f"over={over.step_id}, under={under.step_id}")

    # --- Pass-through decision never pauses -----------------------------------
    engp = WorkflowEngine(WorkflowDefinitionBody.model_validate(PASS_FLOW), enforce_roles=False)
    pp = _to_gate(engp, "gate")
    check("Pass-through decision (no condition) never pauses - auto-resolves",
          pp.step_id == "done" and pp.is_terminal, f"-> {pp.step_id}")

    print("=" * 78)
    passed = sum(1 for r in _results if r)
    print(f"{passed}/{len(_results)} passed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(main())

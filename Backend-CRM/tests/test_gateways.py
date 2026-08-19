"""
test_gateways.py
================

V2 Phase 2: tokens + split/join gateways.

Real parallel branches that are FULL SEQUENCES (form -> approval per branch),
joined under a completion policy — the same evaluate_join_policy that powers
the parallel macro's quorum. Covers: spawn, independent progress, all-join,
n_of_m early join with straggler cancellation, conditional branches, a
parallel MACRO nested inside a token branch, terminate-all semantics, and
definition validation.

Pure engine — no DB. Run: pytest tests/test_gateways.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.workflows.engine import (  # noqa: E402
    EngineError,
    WorkflowEngine,
    evaluate_join_policy,
)
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid, *roles):
    return CurrentUser(id=uid, roles=list(roles))


def E(raw):
    return WorkflowEngine(WorkflowDefinitionBody.model_validate(raw), enforce_roles=False)


def two_branch_def(join_cfg=None, b_cond=None):
    """draft -> split -> (A: form -> approval -> join) + (B: form -> join)
       join -> final approval -> done"""
    b_transition = {"id": "go_b", "to": "b_form", "label": "Branch B", "action": "auto"}
    if b_cond:
        b_transition["condition"] = b_cond
    return {
        "key": "GATE_T", "name": "Gateway test", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "transitions": [{"id": "submit", "to": "fork", "label": "Submit",
                              "action": "submit"}]},
            {"id": "fork", "type": "split", "name": "Fork",
             "transitions": [
                 {"id": "go_a", "to": "a_form", "label": "Branch A", "action": "auto"},
                 b_transition]},
            {"id": "a_form", "type": "form", "name": "A form",
             "transitions": [{"id": "a_submit", "to": "a_approve", "label": "Submit A",
                              "action": "submit"}]},
            {"id": "a_approve", "type": "approval", "name": "A approval",
             "transitions": [{"id": "a_ok", "to": "merge", "label": "Approve A",
                              "action": "approve"}]},
            {"id": "b_form", "type": "form", "name": "B form",
             "transitions": [{"id": "b_submit", "to": "merge", "label": "Submit B",
                              "action": "submit"}]},
            {"id": "merge", "type": "join", "name": "Merge",
             "config": ({"join": join_cfg} if join_cfg else {}),
             "transitions": [{"id": "merged", "to": "final", "label": "Merged",
                              "action": "join_met"}]},
            {"id": "final", "type": "approval", "name": "Final",
             "transitions": [{"id": "f_ok", "to": "done", "label": "Approve",
                              "action": "approve"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


def _steps_of(ctx):
    return sorted(t["step"] for t in ctx.get("_tokens", []))


def test_split_spawns_branch_tokens_with_full_sequences():
    eng = E(two_branch_def())
    r = eng.start({})
    r = eng.perform("draft", "submit", r.context, U("u"))
    assert _steps_of(r.context) == ["a_form", "b_form"]  # two real tokens

    # Both branches offer their actions at once (union over tokens).
    acts = {a.transition_id for a in eng.available_actions(r.step_id, r.context, U("u"))}
    assert {"a_submit", "b_submit"} <= acts

    # Branch A progresses through ITS OWN SEQUENCE without touching branch B.
    r = eng.perform(r.step_id, "a_submit", r.context, U("u"))
    assert _steps_of(r.context) == ["a_approve", "b_form"]
    r = eng.perform(r.step_id, "a_ok", r.context, U("u"))
    # A arrived at the join; B still parked — join(all) holds.
    assert _steps_of(r.context) == ["b_form"]
    assert not r.is_terminal

    # B arrives -> join fires -> single continuation token at the final step.
    r = eng.perform(r.step_id, "b_submit", r.context, U("u"))
    assert _steps_of(r.context) == ["final"]
    r = eng.perform(r.step_id, "f_ok", r.context, U("u"))
    assert r.is_terminal and r.step_id == "done"
    assert "_tokens" not in r.context  # cleared on completion


def test_n_of_m_join_fires_early_and_cancels_straggler():
    eng = E(two_branch_def(join_cfg={"mode": "n_of_m", "value": 1}))
    r = eng.start({})
    r = eng.perform("draft", "submit", r.context, U("u"))
    # B finishes first; 1-of-2 met -> A's token (mid-sequence) is CANCELLED.
    r = eng.perform(r.step_id, "b_submit", r.context, U("u"))
    assert _steps_of(r.context) == ["final"]
    acts = {a.transition_id for a in eng.available_actions(r.step_id, r.context, U("u"))}
    assert "a_submit" not in acts  # the straggler branch is gone


def test_conditional_split_branch_filtered():
    cond = {"all": [{"field": "need_b", "op": "is_true"}]}
    eng = E(two_branch_def(b_cond=cond))
    r = eng.start({"need_b": False})
    r = eng.perform("draft", "submit", r.context, U("u"))
    # Only branch A spawned; the join expects exactly the spawned count (1).
    assert _steps_of(r.context) == ["a_form"]
    r = eng.perform(r.step_id, "a_submit", r.context, U("u"))
    r = eng.perform(r.step_id, "a_ok", r.context, U("u"))
    assert _steps_of(r.context) == ["final"]  # join(all over 1) fired


def test_parallel_macro_inside_a_token_branch():
    """A legacy parallel (quorum) step nested INSIDE a split branch: the macro
    and the token world compose — both are the same join-policy machinery."""
    raw = two_branch_def()
    # Replace branch A's approval with a parallel quorum step.
    for s in raw["steps"]:
        if s["id"] == "a_approve":
            s.clear()
            s.update({
                "id": "a_approve", "type": "parallel", "name": "A panel",
                "config": {"branches": [
                    {"id": "r1", "name": "R1"}, {"id": "r2", "name": "R2"}],
                    "quorum": {"mode": "n_of_m", "value": 1}, "on_reject": "count"},
                "transitions": [
                    {"id": "a_qm", "to": "merge", "label": "Met", "action": "quorum_met"},
                    {"id": "a_qf", "to": "merge", "label": "Failed", "action": "quorum_failed"}],
            })
    eng = E(raw)
    r = eng.start({})
    r = eng.perform("draft", "submit", r.context, U("u"))
    r = eng.perform(r.step_id, "a_submit", r.context, U("u"))
    assert _steps_of(r.context) == ["a_approve", "b_form"]
    # Vote inside the macro while branch B is independently parked.
    r = eng.perform(r.step_id, "r1:approve", r.context, U("rev1"))
    assert r.vote["branch_id"] == "r1"
    assert _steps_of(r.context) == ["b_form"]  # A reached the join via quorum
    r = eng.perform(r.step_id, "b_submit", r.context, U("u"))
    assert _steps_of(r.context) == ["final"]


def test_terminal_terminates_all_tokens():
    raw = two_branch_def()
    # Branch B goes straight to a terminal instead of the join.
    for s in raw["steps"]:
        if s["id"] == "b_form":
            s["transitions"] = [{"id": "b_kill", "to": "done", "label": "Abort",
                                 "action": "submit"}]
    eng = E(raw)
    r = eng.start({})
    r = eng.perform("draft", "submit", r.context, U("u"))
    r = eng.perform(r.step_id, "b_kill", r.context, U("u"))
    assert r.is_terminal and r.step_id == "done"
    assert "_tokens" not in r.context and "_joins" not in r.context


def test_join_policy_evaluator_shared_semantics():
    # all
    assert evaluate_join_policy("all", None, "count", 3, 3, 0, 0) == "met"
    assert evaluate_join_policy("all", None, "count", 3, 2, 0, 1) == "open"
    # n_of_m + fail_fast
    assert evaluate_join_policy("n_of_m", 2, "fail_fast", 3, 1, 1, 1) == "failed"
    assert evaluate_join_policy("n_of_m", 2, "count", 3, 1, 1, 1) == "open"
    # count-mode unreachable threshold fails early
    assert evaluate_join_policy("n_of_m", 3, "count", 3, 1, 1, 1) == "failed"
    # percent
    assert evaluate_join_policy("percent", 50, "count", 4, 2, 0, 2) == "met"


def test_validation_rules_for_gateways():
    bad_split = two_branch_def()
    for s in bad_split["steps"]:
        if s["id"] == "fork":
            s["transitions"] = s["transitions"][:1]
    with pytest.raises(Exception, match="at least 2 outgoing"):
        WorkflowDefinitionBody.model_validate(bad_split)

    bad_join = two_branch_def()
    for s in bad_join["steps"]:
        if s["id"] == "merge":
            s["transitions"] = [{"id": "x", "to": "final", "label": "x", "action": "next"}]
    with pytest.raises(Exception, match="join_met"):
        WorkflowDefinitionBody.model_validate(bad_join)


def test_legacy_definitions_gain_no_token_keys():
    """A definition without gateways must keep its persisted context shape
    byte-for-byte: no _tokens/_joins/_tok_seq ever appear."""
    raw = {
        "key": "LEGACY", "name": "Legacy", "start_step": "a",
        "steps": [
            {"id": "a", "type": "form", "name": "A",
             "transitions": [{"id": "go", "to": "z", "label": "Go", "action": "submit"}]},
            {"id": "z", "type": "terminal", "name": "Z", "transitions": []},
        ],
    }
    eng = E(raw)
    r = eng.start({"x": 1})
    assert set(r.context) == {"x"}
    r = eng.perform("a", "go", r.context, U("u"))
    assert set(r.context) == {"x"}

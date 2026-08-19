"""
test_kernel.py
==============

Phase 1 of Workflow Platform V2: the event-sourced pure kernel.

    decide(definition, state, event) -> Decision(state', commands)

Proves: purity (same inputs -> same outputs, caller state never mutated), the
event/command contract for the three Phase-1 events (StartWorkflow,
ActionPerformed, CancelRequested), and audit-command equivalence with what the
service used to hand-write (started / action verbs / vote detail / notified
rows / decline-reason persistence).

Pure — no DB. Run: pytest tests/test_kernel.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.workflows import kernel  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid, *roles):
    return CurrentUser(id=uid, roles=list(roles))


def flow() -> WorkflowDefinitionBody:
    """draft -> parallel(legal+financial, all) -> signing(ordered, vp) -> executed"""
    raw = {
        "key": "KERNEL_T", "name": "Kernel test", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "par", "label": "Submit",
                              "action": "submit"}]},
            {"id": "par", "type": "parallel", "name": "Review",
             "config": {"branches": [
                 {"id": "legal", "name": "Legal",
                  "assignee": {"type": "role", "value": "legal"}},
                 {"id": "fin", "name": "Financial", "kind": "notify"}],
                 "quorum": {"mode": "all"}, "on_reject": "count"},
             "transitions": [
                 {"id": "qm", "to": "signing", "label": "Met", "action": "quorum_met"},
                 {"id": "qf", "to": "rejected", "label": "Failed", "action": "quorum_failed"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Sign",
             "config": {"signers": [{"id": "vp", "name": "VP",
                                     "assignee": {"type": "role", "value": "vp"}}]},
             "transitions": [
                 {"id": "ok", "to": "executed", "label": "All signed", "action": "all_signed"},
                 {"id": "dec", "to": "rejected", "label": "Declined",
                  "action": "signing_declined", "requires_comment": True}]},
            {"id": "executed", "type": "terminal", "name": "Executed", "transitions": []},
            {"id": "rejected", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


BLANK = kernel.InstanceState(status="active", current_step=None, context={})


def test_start_event_state_and_audit():
    d = kernel.decide(flow(), BLANK, kernel.StartWorkflow(context={"a": 1}),
                      enforce_roles=False)
    assert d.state.status == "active" and d.state.current_step == "draft"
    assert d.state.context["a"] == 1
    audits = [c for c in d.commands if isinstance(c, kernel.AppendAudit)]
    assert audits[0].action == "started" and audits[0].to_step == "draft"


def test_decide_is_pure_and_deterministic():
    state = kernel.InstanceState("active", "draft", {"x": 1})
    ev = kernel.ActionPerformed(user=U("sm", "study_manager"),
                                transition_id="submit", payload={})
    ctx_before = dict(state.context)
    d1 = kernel.decide(flow(), state, ev, enforce_roles=False)
    d2 = kernel.decide(flow(), state, ev, enforce_roles=False)

    def _no_ts(ctx):
        """Strip the engine's embedded 'at' timestamps (the one wall-clock value
        the engine records, kept for audit fidelity) before comparing."""
        import json
        s = json.loads(json.dumps(ctx))
        for step_votes in (s.get("_branches") or {}).values():
            for v in step_votes.values():
                v.pop("at", None)
        return s

    assert d1.state.status == d2.state.status
    assert d1.state.current_step == d2.state.current_step == "par"
    assert _no_ts(d1.state.context) == _no_ts(d2.state.context)
    assert state.context == ctx_before  # caller's state never mutated


def test_action_event_emits_vote_audit_and_notify_rows():
    # Submit onto the parallel step: entering it delivers the notify branch.
    d = kernel.decide(flow(), kernel.InstanceState("active", "draft", {}),
                      kernel.ActionPerformed(user=U("sm"), transition_id="submit",
                                             payload={}),
                      enforce_roles=False)
    audits = [c for c in d.commands if isinstance(c, kernel.AppendAudit)]
    assert audits[0].action == "submit"
    notified = [a for a in audits if a.action == "notified"]
    assert len(notified) == 1 and notified[0].payload["branch_id"] == "fin"

    # Vote the only action branch -> quorum met -> vote audit carries branch_id.
    d2 = kernel.decide(flow(), d.state,
                       kernel.ActionPerformed(user=U("l1", "legal"),
                                              transition_id="legal:approve", payload={}),
                       enforce_roles=False)
    assert d2.state.current_step == "signing"
    a0 = [c for c in d2.commands if isinstance(c, kernel.AppendAudit)][0]
    assert a0.action == "approve" and a0.payload["branch_id"] == "legal"


def test_decline_emits_persist_reason_command():
    state = kernel.InstanceState("active", "signing", {})
    d = kernel.decide(flow(), state,
                      kernel.ActionPerformed(user=U("vp1", "vp"),
                                             transition_id="vp:decline", payload={},
                                             comment="Clause 7 unacceptable"),
                      enforce_roles=False)
    assert d.state.current_step == "rejected" and d.state.status == "completed"
    persists = [c for c in d.commands if isinstance(c, kernel.PersistDeclineReason)]
    assert len(persists) == 1
    assert persists[0].branch_id == "vp"
    assert persists[0].reason == "Clause 7 unacceptable"


def test_cancel_event():
    d = kernel.decide(flow(), kernel.InstanceState("active", "draft", {}),
                      kernel.CancelRequested(user=U("sm"), comment="dup"),
                      enforce_roles=False)
    assert d.state.status == "cancelled" and d.state.current_step == "draft"
    a = d.commands[0]
    assert a.action == "cancelled" and a.actor == "sm" and a.comment == "dup"
    # Cancelling a non-active instance is rejected by the kernel.
    with pytest.raises(kernel.KernelError, match="already cancelled"):
        kernel.decide(flow(), d.state, kernel.CancelRequested(user=U("sm")),
                      enforce_roles=False)


def test_action_on_finished_instance_rejected():
    done = kernel.InstanceState("completed", "executed", {})
    with pytest.raises(kernel.KernelError, match="no actions allowed"):
        kernel.decide(flow(), done,
                      kernel.ActionPerformed(user=U("x"), transition_id="submit",
                                             payload={}),
                      enforce_roles=False)

"""
test_rework.py
==============

Proves the reset-on-entry fix: rework / send-back loops into round-based steps
(parallel, mixed fan-out, ordered_signing) now reopen their branches/slots on
re-entry, so a reworked step is walkable again — while the AUDIT trail keeps BOTH
rounds (the failed attempt and the successful one).

Engine is PURE; a small in-test `Runner` mirrors the real service's persistence +
audit (start_instance / perform_action / _log / _log_notifications), so the
asserted audit equals what WorkflowAuditEntry would receive.

Run:
    pytest tests/test_rework.py -v
    python  tests/test_rework.py

Covers:
  a) parallel: one branch rejects -> quorum_failed -> draft -> resubmit ->
     internal_review reopens both branches -> both approve -> advances
  b) ordered_signing: a decline -> rework -> re-entry reopens all slots ->
     signing completes
  c) audit shows BOTH rounds (failed + successful); nothing erased
  d) all existing 22 tests still pass
"""

import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

from app.modules.workflows.engine import WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

import test_parallel         # noqa: E402
import test_fanout           # noqa: E402
import test_ordered_signing  # noqa: E402
import test_broadcast        # noqa: E402
import test_full_cta         # noqa: E402


def U(uid: str) -> CurrentUser:
    return CurrentUser(id=uid, roles=[])


class Runner:
    """Faithful mirror of the real service's persistence + audit."""

    def __init__(self, engine: WorkflowEngine):
        self.e = engine
        self.context: dict = {}
        self.current = None
        self.status = "active"
        self.audit: list[dict] = []

    def start(self, context: dict):
        r = self.e.start(context)
        self.context, self.current = r.context, r.step_id
        self.audit.append({"action": "started", "to": r.step_id, "branch": None, "actor": None})
        self._notif(r)
        if r.is_terminal:
            self.status = "completed"
        return r

    def act(self, transition_id: str, user: CurrentUser):
        frm = self.current
        r = self.e.perform(frm, transition_id, self.context, user)
        self.context, self.current = r.context, r.step_id
        if r.vote:
            action, branch = r.vote["decision"], r.vote["branch_id"]
        else:
            action, branch = self._verb(frm, transition_id), None
        self.audit.append({"action": action, "to": r.step_id, "branch": branch, "actor": user.id})
        self._notif(r)
        if r.is_terminal:
            self.status = "completed"
        return r

    def options(self):
        """Distinct slot/branch ids currently offered on the parked step."""
        acts = self.e.available_actions(self.current, self.context, U("anyone"))
        return {a.transition_id.rsplit(":", 1)[0] for a in acts}

    def _notif(self, r):
        for bid in r.notified:
            self.audit.append({"action": "notified", "to": r.step_id, "branch": bid, "actor": None})

    def _verb(self, step_id, transition_id):
        for t in self.e.step(step_id).transitions:
            if t.id == transition_id:
                return t.action
        return "action"


# ---------------------------------------------------------------------------
# Definitions (NEW — nothing real touched)
# ---------------------------------------------------------------------------
def parallel_rework_def() -> WorkflowDefinitionBody:
    """draft -> internal_review[legal+financial, quorum all] -> done
       quorum_failed loops back to draft (rework)."""
    raw = {
        "key": "RWK_PAR", "name": "Parallel rework", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "internal_review", "label": "Submit", "action": "submit"}]},
            {"id": "internal_review", "type": "parallel", "name": "Internal Review",
             "config": {"branches": [
                 {"id": "internal_legal", "name": "Legal", "assignee": {"type": "role", "value": "legal"}},
                 {"id": "internal_financial", "name": "Financial", "assignee": {"type": "role", "value": "financial"}},
             ], "quorum": {"mode": "all"}, "on_reject": "count"},
             "transitions": [
                 {"id": "ok", "to": "done", "label": "Approved", "action": "quorum_met"},
                 {"id": "rwk", "to": "draft", "label": "Send back", "action": "quorum_failed"},
             ]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def ordered_rework_def() -> WorkflowDefinitionBody:
    """draft -> signing[director,pi,vp] -> done
       signing_declined -> rework(approval) -> redo loops back to signing."""
    raw = {
        "key": "RWK_ORD", "name": "Ordered rework", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "signing", "label": "Submit", "action": "submit"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Signatures",
             "config": {"signers": [
                 {"id": "director", "name": "Director"},
                 {"id": "pi", "name": "PI"},
                 {"id": "vp", "name": "VP"},
             ]},
             "transitions": [
                 {"id": "ok", "to": "done", "label": "All signed", "action": "all_signed"},
                 {"id": "dec", "to": "rework", "label": "Declined", "action": "signing_declined"},
             ]},
            {"id": "rework", "type": "approval", "name": "Rework",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "redo", "to": "signing", "label": "Re-send for signatures", "action": "rework"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


# ---------------------------------------------------------------------------
# a) parallel rework: reject -> back to draft -> resubmit -> reopened -> approve
# ---------------------------------------------------------------------------
def _walk_parallel_rework() -> Runner:
    run = Runner(WorkflowEngine(parallel_rework_def(), enforce_roles=False))
    run.start({})
    run.act("submit", U("main"))
    assert run.current == "internal_review"

    # Round 1: legal approves, financial REJECTS -> quorum_failed (count: unreachable)
    run.act("internal_legal:approve", U("l1"))
    run.act("internal_financial:reject", U("f1"))
    assert run.current == "draft", f"expected send-back to draft, got {run.current}"

    # Resubmit -> re-enter internal_review. THE FIX: both branches open again.
    run.act("submit", U("main"))
    assert run.current == "internal_review"
    assert run.options() == {"internal_legal", "internal_financial"}, run.options()

    # Round 2: both approve -> advances to done.
    run.act("internal_legal:approve", U("l2"))
    r = run.act("internal_financial:approve", U("f2"))
    assert run.current == "done" and r.is_terminal, run.current

    # Live working-state holds ONLY the fresh (round-2) votes.
    final = run.context["_branches"]["internal_review"]
    assert final["internal_financial"]["decision"] == "approve"
    assert final["internal_financial"]["actor"] == "f2"
    return run


def test_a_parallel_rework_reopens():
    _walk_parallel_rework()


# ---------------------------------------------------------------------------
# b) ordered rework: decline -> rework -> re-entry reopens all slots -> complete
# ---------------------------------------------------------------------------
def _walk_ordered_rework() -> Runner:
    run = Runner(WorkflowEngine(ordered_rework_def(), enforce_roles=False))
    run.start({})
    run.act("submit", U("main"))
    assert run.current == "signing"
    assert run.options() == {"director"}            # director first

    # Round 1: director signs, PI declines -> rework
    run.act("director:sign", U("d1"))
    assert run.options() == {"pi"}
    run.act("pi:decline", U("p1"))
    assert run.current == "rework", run.current

    # Re-send -> re-enter signing. THE FIX: slots reopen, director is first again.
    run.act("redo", U("main"))
    assert run.current == "signing"
    assert run.options() == {"director"}, run.options()

    # Round 2: full clean signing run.
    run.act("director:sign", U("d2"))
    run.act("pi:sign", U("p2"))
    r = run.act("vp:sign", U("v2"))
    assert run.current == "done" and r.is_terminal, run.current
    # Final live state = round-2 signers only, all signed.
    final = run.context["_branches"]["signing"]
    assert {s: final[s]["decision"] for s in ("director", "pi", "vp")} == \
        {"director": "signed", "pi": "signed", "vp": "signed"}
    return run


def test_b_ordered_rework_reopens():
    _walk_ordered_rework()


# ---------------------------------------------------------------------------
# c) audit shows BOTH rounds — nothing erased
# ---------------------------------------------------------------------------
def test_c_audit_keeps_both_rounds():
    run_par = _walk_parallel_rework()
    rows = [(a["action"], a["branch"]) for a in run_par.audit]
    # Round 1 failure AND round 2 success both present.
    assert ("reject", "internal_financial") in rows          # round 1
    assert rows.count(("approve", "internal_legal")) == 2     # round 1 + round 2
    assert ("approve", "internal_financial") in rows          # round 2
    assert [a["action"] for a in run_par.audit].count("submit") == 2  # resubmitted once
    assert run_par.audit[-1]["to"] == "done"

    run_ord = _walk_ordered_rework()
    orows = [(a["action"], a["branch"]) for a in run_ord.audit]
    assert ("declined", "pi") in orows                        # round 1 decline
    assert orows.count(("signed", "director")) == 2           # both rounds
    assert ("signed", "vp") in orows                          # round 2 completion


# ---------------------------------------------------------------------------
# d) all existing 22 tests still pass (no regression)
# ---------------------------------------------------------------------------
def test_d_no_regression():
    suites = (test_parallel, test_fanout, test_ordered_signing, test_broadcast, test_full_cta)
    total = 0
    for suite in suites:
        for _label, fn, _summary in suite._TESTS:
            fn()
            total += 1
    assert total == 22, f"expected 22 existing tests, ran {total}"


_TESTS = [
    ("a) parallel rework reopens", test_a_parallel_rework_reopens,
     "reject -> back to draft -> resubmit -> both branches open -> approve -> done"),
    ("b) ordered rework reopens", test_b_ordered_rework_reopens,
     "decline -> rework -> re-entry reopens all slots (director first) -> completes"),
    ("c) audit keeps both rounds", test_c_audit_keeps_both_rounds,
     "failed round AND successful round both in audit; nothing erased"),
    ("d) existing 22 tests pass", test_d_no_regression,
     "blocks 1-4 + full CTA all still pass"),
]


if __name__ == "__main__":
    print("=" * 78)
    print("Workflow engine — rework / send-back (reset-on-entry) tests")
    print("=" * 78)
    failures = 0
    for label, fn, summary in _TESTS:
        try:
            fn()
            print(f"PASS  {label}\n        -> {summary}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {label}\n        -> {type(exc).__name__}: {exc}")

    # Show the parallel rework audit trail (both rounds) for the report.
    run = _walk_parallel_rework()
    print("\n--- audit trail: parallel rework (both rounds) ---")
    for a in run.audit:
        b = f" [{a['branch']}]" if a["branch"] else ""
        print(f"  {a['action']:<10}{b:<22} -> {a['to']:<18} ({a['actor'] or 'system'})")
    print("=" * 78)
    print(f"{len(_TESTS) - failures}/{len(_TESTS)} passed")
    sys.exit(1 if failures else 0)

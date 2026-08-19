"""
test_fanout.py
==============

Test-first coverage for the workflow engine's "mixed fan-out" capability — the
real CTA "Send to Site Team" pattern: one step fans out to several people at
once, where some branches are NOTIFY-ONLY (PI, Site Manager, CRC) and some are
ACTION-REQUIRED reviewers (Site Legal, Site Financial). Quorum is computed over
ACTION branches only; notify branches are recorded as delivered and ignored for
quorum. Reuses the block-1 parallel branch/vote/join machinery.

The engine is PURE, so these drive WorkflowEngine directly.

Runnable two ways:
    pytest tests/test_fanout.py -v
    python  tests/test_fanout.py            # prints a self-contained report

Covers:
  a) both action branches approve -> advances (notify branches did NOT block)
  b) one action branch rejects (fail_fast) -> quorum_failed
  c) notify branches recorded as "notified"; never returned as available actions
  d) block-1 parallel tests still pass (no regression)
  e) sequential flow still runs unchanged
"""

import os
import sys

# Make `app` importable, and the tests dir importable (for the sibling block-1 import).
_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

from app.modules.workflows.engine import EngineError, WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

import test_parallel  # noqa: E402  (sibling block-1 suite, for the regression test)


NOTIFY = ["pi", "site_manager", "crc"]
ACTION = ["site_legal", "site_financial"]


def fanout_def(on_reject: str = "count") -> WorkflowDefinitionBody:
    """draft -> site_team[notify: pi/site_manager/crc; action: site_legal/site_financial;
       quorum all over action] -> signature -> executed   (quorum_failed -> rejected)"""
    raw = {
        "key": "FANTEST",
        "name": "Mixed Fan-out Test",
        "start_step": "draft",
        "steps": [
            {
                "id": "draft", "type": "form", "name": "Draft",
                "assignee": {"type": "role", "value": "study_manager"},
                "transitions": [
                    {"id": "submit", "to": "site_team", "label": "Send to Site Team", "action": "submit"}
                ],
            },
            {
                "id": "site_team", "type": "parallel", "name": "Send to Site Team",
                "config": {
                    "branches": [
                        {"id": "pi", "name": "PI", "kind": "notify"},
                        {"id": "site_manager", "name": "Site Manager", "kind": "notify"},
                        {"id": "crc", "name": "CRC", "kind": "notify"},
                        {"id": "site_legal", "name": "Site Legal", "kind": "action",
                         "assignee": {"type": "role", "value": "legal"}},
                        {"id": "site_financial", "name": "Site Financial", "kind": "action",
                         "assignee": {"type": "role", "value": "financial"}},
                    ],
                    "quorum": {"mode": "all"},      # all ACTION branches must approve
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
                "transitions": [{"id": "sign", "to": "executed", "label": "Sign", "action": "sign"}],
            },
            {"id": "executed", "type": "terminal", "name": "Executed", "transitions": []},
            {"id": "rejected", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def U(uid: str) -> CurrentUser:
    return CurrentUser(id=uid, roles=[])  # open mode


def _drive_to_site_team(engine: WorkflowEngine):
    """start -> draft -> submit -> parks on the fan-out step. Returns the
    StepResult of entering site_team (so .notified can be inspected)."""
    r = engine.start({})
    assert r.step_id == "draft", r.step_id
    r = engine.perform("draft", "submit", r.context, U("author"))
    assert r.step_id == "site_team", r.step_id
    return r


# ---------------------------------------------------------------------------
# a) both action branches approve -> advances; notify branches did NOT block
# ---------------------------------------------------------------------------
def test_a_action_quorum_advances():
    eng = WorkflowEngine(fanout_def("count"), enforce_roles=False)
    entry = _drive_to_site_team(eng)

    # Only the 2 ACTION branches are actionable (x approve/reject = 4); the 3
    # notify branches never appear.
    acts = eng.available_actions("site_team", entry.context, U("alice"))
    assert len(acts) == 4, [a.transition_id for a in acts]
    assert not any(any(n in a.transition_id for n in NOTIFY) for a in acts)

    # First action approves -> still open (quorum is ALL action branches = 2).
    r = eng.perform("site_team", "site_legal:approve", entry.context, U("alice"))
    assert r.step_id == "site_team", r.step_id

    # Second action approves -> quorum over action branches met -> advance.
    r = eng.perform("site_team", "site_financial:approve", r.context, U("bob"))
    assert r.step_id == "signature", r.step_id
    # Notify recipients are present-and-delivered but never counted for quorum.
    branches = r.context["_branches"]["site_team"]
    assert all(branches[n]["decision"] == "notified" for n in NOTIFY)


# ---------------------------------------------------------------------------
# b) one action branch rejects (fail_fast) -> quorum_failed
# ---------------------------------------------------------------------------
def test_b_action_reject_fail_fast():
    eng = WorkflowEngine(fanout_def("fail_fast"), enforce_roles=False)
    entry = _drive_to_site_team(eng)

    r = eng.perform("site_team", "site_legal:reject", entry.context, U("alice"))
    assert r.step_id == "rejected", r.step_id


# ---------------------------------------------------------------------------
# c) notify branches recorded as "notified"; never actionable
# ---------------------------------------------------------------------------
def test_c_notify_recorded_never_actionable():
    eng = WorkflowEngine(fanout_def("count"), enforce_roles=False)
    entry = _drive_to_site_team(eng)

    # Engine surfaced exactly the 3 notify deliveries on entry (for the service
    # to turn into "notified" audit rows).
    assert set(entry.notified) == set(NOTIFY), entry.notified

    # They are recorded as delivered in the shared _branches structure.
    recorded = entry.context["_branches"]["site_team"]
    assert all(recorded[n]["decision"] == "notified" and recorded[n]["actor"] is None
               for n in NOTIFY)

    # And they are NEVER returned as available actions...
    acts = eng.available_actions("site_team", entry.context, U("alice"))
    assert all(not any(n in a.transition_id for n in NOTIFY) for a in acts)

    # ...nor can they be voted directly.
    raised = False
    try:
        eng.perform("site_team", "pi:approve", entry.context, U("alice"))
    except EngineError as exc:
        raised = True
        assert "notify-only" in str(exc), str(exc)
    assert raised, "voting a notify branch should raise EngineError"


# ---------------------------------------------------------------------------
# d) block-1 parallel tests still pass (no regression)
# ---------------------------------------------------------------------------
def test_d_block1_no_regression():
    for _label, fn, _summary in test_parallel._TESTS:
        fn()  # raises AssertionError/EngineError if anything regressed


# ---------------------------------------------------------------------------
# e) sequential flow still runs unchanged
# ---------------------------------------------------------------------------
def test_e_sequential_unchanged():
    eng = WorkflowEngine(test_parallel.sequential_def(), enforce_roles=False)
    r = eng.start({})
    assert r.step_id == "draft"
    r = eng.perform("draft", "submit", r.context, U("u"))
    assert r.step_id == "review"
    r = eng.perform("review", "approve", r.context, U("u"))
    assert r.step_id == "signature"
    r = eng.perform("signature", "sign", r.context, U("u"))
    assert r.step_id == "executed" and r.is_terminal
    assert "_branches" not in r.context


# (label, fn, summary) — summary is for the script runner only; tests are assert-only.
_TESTS = [
    ("a) action quorum advances (notify ignored)", test_a_action_quorum_advances,
     "both action branches approve -> 'signature'; notify branches never gated"),
    ("b) fail_fast action reject -> failed", test_b_action_reject_fail_fast,
     "one action reject (fail_fast) -> 'rejected' (quorum_failed)"),
    ("c) notify recorded, never actionable", test_c_notify_recorded_never_actionable,
     "pi/site_manager/crc recorded 'notified'; absent from actions; vote rejected"),
    ("d) block-1 parallel: no regression", test_d_block1_no_regression,
     "all block-1 parallel tests still pass"),
    ("e) sequential flow unchanged", test_e_sequential_unchanged,
     "draft -> review -> signature -> executed (terminal); no _branches added"),
]


if __name__ == "__main__":
    print("=" * 72)
    print("Workflow engine — mixed fan-out tests")
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

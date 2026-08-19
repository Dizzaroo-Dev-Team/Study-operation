"""
test_broadcast.py
=================

Test-first coverage for the workflow engine's "notify-all broadcast" capability —
the real CTA "Distribute Final Copy": a step that notifies many recipients at
once, requires NO action, records the deliveries, and immediately auto-advances.
Reuses the block-2 notify-delivery recording + audit path.

The engine is PURE, so these drive WorkflowEngine directly.

Runnable two ways:
    pytest tests/test_broadcast.py -v
    python  tests/test_broadcast.py          # prints a self-contained report

Covers:
  a) on reaching distribute, all 6 recipients recorded "notified"
  b) available_actions on the broadcast step is empty (nobody acts)
  c) the broadcast auto-advances and the instance completes at 'done'
  d) blocks 1, 2 & 3 tests still pass; sequential flow unchanged
"""

import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

from app.modules.workflows.engine import EngineError, WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

import test_parallel         # noqa: E402  (block 1 — regression)
import test_fanout           # noqa: E402  (block 2 — regression)
import test_ordered_signing  # noqa: E402  (block 3 — regression)


RECIPIENTS = ["pi", "site_manager", "site_legal", "site_financial", "crc", "site_director"]
SIGNERS = ["director", "pi", "vp"]


def broadcast_def() -> WorkflowDefinitionBody:
    """draft -> signing[director,pi,vp] -> executed_doc (normal approval)
       -> distribute (broadcast: 6 recipients) -> done (terminal)."""
    raw = {
        "key": "BCASTTEST",
        "name": "Broadcast Test",
        "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "signing", "label": "Send", "action": "submit"}]},
            {"id": "signing", "type": "ordered_signing", "name": "Signatures",
             "config": {"signers": [
                 {"id": "director", "name": "Site Director"},
                 {"id": "pi", "name": "PI"},
                 {"id": "vp", "name": "VP"},
             ]},
             "transitions": [{"id": "done", "to": "executed_doc", "label": "All signed", "action": "all_signed"}]},
            {"id": "executed_doc", "type": "approval", "name": "Final Executed Document",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "approve", "to": "distribute", "label": "Distribute", "action": "approve"}]},
            {"id": "distribute", "type": "broadcast", "name": "Distribute Final Copy",
             "config": {"recipients": [
                 {"id": "pi", "name": "PI"},
                 {"id": "site_manager", "name": "Site Manager"},
                 {"id": "site_legal", "name": "Site Legal"},
                 {"id": "site_financial", "name": "Site Financial"},
                 {"id": "crc", "name": "CRC"},
                 {"id": "site_director", "name": "Site Director"},
             ]},
             "transitions": [{"id": "bdone", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def U(uid: str) -> CurrentUser:
    return CurrentUser(id=uid, roles=[])  # open mode


def _drive_to_done(engine: WorkflowEngine):
    """Walk the whole flow; the final perform crosses the broadcast and completes."""
    r = engine.start({})
    assert r.step_id == "draft", r.step_id
    r = engine.perform("draft", "submit", r.context, U("author"))
    assert r.step_id == "signing", r.step_id
    for s in SIGNERS:
        r = engine.perform("signing", f"{s}:sign", r.context, U(s))
    assert r.step_id == "executed_doc", r.step_id
    # Approving the executed doc enters the broadcast, which auto-advances to done.
    r = engine.perform("executed_doc", "approve", r.context, U("study_mgr"))
    return r


# ---------------------------------------------------------------------------
# a) all 6 recipients recorded "notified"
# ---------------------------------------------------------------------------
def test_a_all_recipients_notified():
    eng = WorkflowEngine(broadcast_def(), enforce_roles=False)
    r = _drive_to_done(eng)

    # The crossing perform surfaced exactly the 6 deliveries (the service turns
    # each into an action="notified" audit row).
    assert set(r.notified) == set(RECIPIENTS), r.notified
    recorded = r.context["_branches"]["distribute"]
    assert set(recorded.keys()) == set(RECIPIENTS)
    assert all(recorded[rid]["decision"] == "notified" and recorded[rid]["actor"] is None
               for rid in RECIPIENTS)


# ---------------------------------------------------------------------------
# b) available_actions on the broadcast step is empty
# ---------------------------------------------------------------------------
def test_b_broadcast_has_no_actions():
    eng = WorkflowEngine(broadcast_def(), enforce_roles=False)
    # Directly on the broadcast step (with or without context) -> nobody acts.
    assert eng.available_actions("distribute", {}, U("anyone")) == []
    # And it cannot be acted upon.
    raised = False
    try:
        eng.perform("distribute", "bdone", {}, U("anyone"))
    except EngineError as exc:
        raised = True
        assert "auto-advance" in str(exc), str(exc)
    assert raised, "performing on a broadcast step should raise"


# ---------------------------------------------------------------------------
# c) broadcast auto-advances; instance completes at 'done'
# ---------------------------------------------------------------------------
def test_c_auto_advances_to_done():
    eng = WorkflowEngine(broadcast_def(), enforce_roles=False)
    r = _drive_to_done(eng)
    assert r.step_id == "done", r.step_id
    assert r.is_terminal is True
    # 'distribute' was crossed, never parked on.
    assert "distribute" in r.visited and r.step_id != "distribute"


# ---------------------------------------------------------------------------
# d) blocks 1,2,3 still pass; sequential flow unchanged
# ---------------------------------------------------------------------------
def test_d_blocks_1_2_3_and_sequential():
    for suite in (test_parallel, test_fanout, test_ordered_signing):
        for _label, fn, _summary in suite._TESTS:
            fn()
    eng = WorkflowEngine(test_parallel.sequential_def(), enforce_roles=False)
    r = eng.start({})
    r = eng.perform("draft", "submit", r.context, U("u"))
    r = eng.perform("review", "approve", r.context, U("u"))
    r = eng.perform("signature", "sign", r.context, U("u"))
    assert r.step_id == "executed" and r.is_terminal
    assert "_branches" not in r.context


_TESTS = [
    ("a) all 6 recipients notified", test_a_all_recipients_notified,
     "entering distribute records all 6 recipients as 'notified' (audited)"),
    ("b) broadcast has no actions", test_b_broadcast_has_no_actions,
     "available_actions == []; perform on a broadcast step raises"),
    ("c) auto-advances to done", test_c_auto_advances_to_done,
     "broadcast crossed without parking; instance completes at terminal 'done'"),
    ("d) blocks 1/2/3 + sequential", test_d_blocks_1_2_3_and_sequential,
     "all block-1/2/3 tests pass; sequential flow unchanged"),
]


if __name__ == "__main__":
    print("=" * 72)
    print("Workflow engine — notify-all broadcast tests")
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

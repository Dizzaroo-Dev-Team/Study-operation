"""
test_ordered_signing.py
=======================

Test-first coverage for the workflow engine's "ordered signing" capability — the
real CTA signature phase: a single step holds an ORDERED signer list (Site
Director -> PI -> VP). Only the current signer's slot is open; the next unlocks
only after the current one signs. Strict order, no skipping. Reuses the block-1
_branches slot/audit machinery.

The engine is PURE, so these drive WorkflowEngine directly.

Runnable two ways:
    pytest tests/test_ordered_signing.py -v
    python  tests/test_ordered_signing.py     # prints a self-contained report

Covers:
  a) signing in order director->pi->vp advances to executed
  b) only the current signer's slot is offered at each stage
  c) signing out of order (vp before director) raises
  d) a decline takes the signing_declined path
  e) blocks 1 & 2 still pass; a plain sequential flow still runs unchanged
"""

import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

from app.modules.workflows.engine import EngineError, WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

import test_parallel  # noqa: E402  (block-1 suite — regression)
import test_fanout    # noqa: E402  (block-2 suite — regression)


ORDER = ["director", "pi", "vp"]


def ordered_def() -> WorkflowDefinitionBody:
    """draft -> ordered_signing[director -> pi -> vp] -> executed
       (signing_declined -> rejected)."""
    raw = {
        "key": "ORDTEST",
        "name": "Ordered Signing Test",
        "start_step": "draft",
        "steps": [
            {
                "id": "draft", "type": "form", "name": "Draft",
                "assignee": {"type": "role", "value": "study_manager"},
                "transitions": [
                    {"id": "submit", "to": "signing", "label": "Send for signatures", "action": "submit"}
                ],
            },
            {
                "id": "signing", "type": "ordered_signing", "name": "Signatures",
                "config": {
                    "signers": [
                        {"id": "director", "name": "Site Director",
                         "assignee": {"type": "role", "value": "site_director"}},
                        {"id": "pi", "name": "PI",
                         "assignee": {"type": "role", "value": "pi"}},
                        {"id": "vp", "name": "VP",
                         "assignee": {"type": "role", "value": "vp"}},
                    ],
                },
                "transitions": [
                    {"id": "done", "to": "executed", "label": "All signed", "action": "all_signed"},
                    {"id": "declined", "to": "rejected", "label": "Declined", "action": "signing_declined"},
                ],
            },
            {"id": "executed", "type": "terminal", "name": "Executed", "transitions": []},
            {"id": "rejected", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def U(uid: str) -> CurrentUser:
    return CurrentUser(id=uid, roles=[])  # open mode


def _drive_to_signing(engine: WorkflowEngine):
    r = engine.start({})
    assert r.step_id == "draft", r.step_id
    r = engine.perform("draft", "submit", r.context, U("author"))
    assert r.step_id == "signing", r.step_id
    return r


def _offered_signers(engine: WorkflowEngine, context) -> set:
    """Distinct signer ids currently offered by available_actions."""
    acts = engine.available_actions("signing", context, U("anyone"))
    return {a.transition_id.rsplit(":", 1)[0] for a in acts}


# ---------------------------------------------------------------------------
# a) signing in order advances to executed
# ---------------------------------------------------------------------------
def test_a_in_order_advances():
    eng = WorkflowEngine(ordered_def(), enforce_roles=False)
    r = _drive_to_signing(eng)

    r = eng.perform("signing", "director:sign", r.context, U("dee"))
    assert r.step_id == "signing", r.step_id
    r = eng.perform("signing", "pi:sign", r.context, U("paula"))
    assert r.step_id == "signing", r.step_id
    r = eng.perform("signing", "vp:sign", r.context, U("vic"))
    assert r.step_id == "executed" and r.is_terminal, r.step_id

    slots = r.context["_branches"]["signing"]
    assert [slots[s]["decision"] for s in ORDER] == ["signed", "signed", "signed"]
    assert slots["director"]["actor"] == "dee" and slots["vp"]["actor"] == "vic"


# ---------------------------------------------------------------------------
# b) only the current signer's slot is offered at each stage
# ---------------------------------------------------------------------------
def test_b_only_current_slot_offered():
    eng = WorkflowEngine(ordered_def(), enforce_roles=False)
    r = _drive_to_signing(eng)

    assert _offered_signers(eng, r.context) == {"director"}
    r = eng.perform("signing", "director:sign", r.context, U("dee"))
    assert _offered_signers(eng, r.context) == {"pi"}
    r = eng.perform("signing", "pi:sign", r.context, U("paula"))
    assert _offered_signers(eng, r.context) == {"vp"}


# ---------------------------------------------------------------------------
# c) signing out of order raises
# ---------------------------------------------------------------------------
def test_c_out_of_order_raises():
    eng = WorkflowEngine(ordered_def(), enforce_roles=False)
    r = _drive_to_signing(eng)

    for premature in ("vp:sign", "pi:sign"):
        raised = False
        try:
            eng.perform("signing", premature, r.context, U("eager"))
        except EngineError as exc:
            raised = True
            assert "Out-of-order" in str(exc), str(exc)
        assert raised, f"{premature} before director should raise"

    # And after director signs, signing director again (already signed) raises.
    r = eng.perform("signing", "director:sign", r.context, U("dee"))
    raised = False
    try:
        eng.perform("signing", "director:sign", r.context, U("dee2"))
    except EngineError as exc:
        raised = True
        assert "already" in str(exc), str(exc)
    assert raised, "re-signing director should raise"


# ---------------------------------------------------------------------------
# d) a decline takes the signing_declined path
# ---------------------------------------------------------------------------
def test_d_decline_path():
    eng = WorkflowEngine(ordered_def(), enforce_roles=False)
    r = _drive_to_signing(eng)

    # director signs, then PI declines -> signing_declined -> rejected
    r = eng.perform("signing", "director:sign", r.context, U("dee"))
    r = eng.perform("signing", "pi:decline", r.context, U("paula"))
    assert r.step_id == "rejected", r.step_id
    assert r.context["_branches"]["signing"]["pi"]["decision"] == "declined"


# ---------------------------------------------------------------------------
# e) blocks 1 & 2 still pass; sequential flow still runs unchanged
# ---------------------------------------------------------------------------
def test_e_blocks_1_2_and_sequential():
    for _label, fn, _summary in test_parallel._TESTS:
        fn()
    for _label, fn, _summary in test_fanout._TESTS:
        fn()
    # Plain sequential flow, unchanged.
    eng = WorkflowEngine(test_parallel.sequential_def(), enforce_roles=False)
    r = eng.start({})
    r = eng.perform("draft", "submit", r.context, U("u"))
    r = eng.perform("review", "approve", r.context, U("u"))
    r = eng.perform("signature", "sign", r.context, U("u"))
    assert r.step_id == "executed" and r.is_terminal
    assert "_branches" not in r.context


_TESTS = [
    ("a) in order -> executed", test_a_in_order_advances,
     "director -> pi -> vp signs in order -> advances to 'executed'"),
    ("b) only current slot offered", test_b_only_current_slot_offered,
     "available_actions offers only {director} then {pi} then {vp}"),
    ("c) out-of-order signing raises", test_c_out_of_order_raises,
     "vp/pi before director raise Out-of-order; re-signing director raises 'already'"),
    ("d) decline -> signing_declined", test_d_decline_path,
     "director signs, pi declines -> 'rejected' (signing_declined)"),
    ("e) blocks 1&2 + sequential", test_e_blocks_1_2_and_sequential,
     "all block-1 + block-2 tests pass; sequential flow unchanged"),
]


if __name__ == "__main__":
    print("=" * 72)
    print("Workflow engine — ordered signing tests")
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

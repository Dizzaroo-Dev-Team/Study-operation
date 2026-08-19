"""
test_decline_reason.py
======================

NEED 2 (engine slice): when an ordered-signing step's `signing_declined` transition
is authored with requires_comment=True, a signer DECLINE must carry a reason — the
engine rejects an empty one and records the reason it was given (which the service
then persists with the document + audit). Backward compatible: a decline transition
with requires_comment=False (the default, as in the other tests) is unchanged.

Pure engine — runnable anywhere.

Run:
    pytest tests/test_decline_reason.py -v
    python  tests/test_decline_reason.py
"""

import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

from app.modules.workflows.engine import EngineError, WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid):
    return CurrentUser(id=uid, roles=[])


def _def(require_reason: bool) -> WorkflowDefinitionBody:
    raw = {
        "key": "DEC_REASON", "name": "Decline reason", "start_step": "signing",
        "steps": [
            {"id": "signing", "type": "ordered_signing", "name": "Signatures",
             "config": {"signers": [{"id": "vp", "name": "VP"}]},
             "transitions": [
                 {"id": "ok", "to": "done", "label": "All signed", "action": "all_signed"},
                 {"id": "dec", "to": "rejected", "label": "Declined",
                  "action": "signing_declined", "requires_comment": require_reason}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
            {"id": "rejected", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def test_a_decline_action_advertises_required_comment():
    eng = WorkflowEngine(_def(True), enforce_roles=False)
    r = eng.start({})
    acts = {a.action: a for a in eng.available_actions("signing", r.context, U("vp"))}
    assert "decline" in acts and acts["decline"].requires_comment is True
    assert acts["sign"].requires_comment is False


def test_b_decline_without_reason_rejected():
    eng = WorkflowEngine(_def(True), enforce_roles=False)
    r = eng.start({})
    try:
        eng.perform("signing", "vp:decline", r.context, U("vp"), comment="   ")
    except EngineError as exc:
        assert "reason" in str(exc).lower()
    else:
        raise AssertionError("expected EngineError when declining with no reason")


def test_c_decline_with_reason_records_it():
    eng = WorkflowEngine(_def(True), enforce_roles=False)
    r = eng.start({})
    res = eng.perform("signing", "vp:decline", r.context, U("vp"),
                      comment="Indemnification clause is unacceptable")
    assert res.step_id == "rejected", res.step_id
    assert res.vote["decision"] == "declined"
    assert res.vote["reason"] == "Indemnification clause is unacceptable"
    # The reason is in the persisted branch state too (so it survives in context).
    assert res.context["_branches"]["signing"]["vp"]["reason"] == "Indemnification clause is unacceptable"


def test_d_backward_compat_optional_decline_unchanged():
    # requires_comment defaults False -> declining with no comment still works
    # (this is exactly what test_rework / test_ordered_signing rely on).
    eng = WorkflowEngine(_def(False), enforce_roles=False)
    r = eng.start({})
    res = eng.perform("signing", "vp:decline", r.context, U("vp"))
    assert res.step_id == "rejected" and res.vote["decision"] == "declined"
    assert "reason" not in res.vote


_TESTS = [
    ("a) decline advertises requires_comment", test_a_decline_action_advertises_required_comment,
     "the decline action carries the transition's requires_comment flag to the UI"),
    ("b) empty reason rejected", test_b_decline_without_reason_rejected,
     "declining with no reason raises when the step requires one"),
    ("c) reason recorded", test_c_decline_with_reason_records_it,
     "the reason is captured in the vote + context (service persists it with the doc + audit)"),
    ("d) optional decline unchanged", test_d_backward_compat_optional_decline_unchanged,
     "requires_comment=False -> decline needs no reason (existing behavior)"),
]


if __name__ == "__main__":
    print("=" * 78)
    print("Workflow engine — mandatory signer-decline reason (NEED 2)")
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

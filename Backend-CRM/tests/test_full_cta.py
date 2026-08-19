"""
test_full_cta.py
================

ASSEMBLY TEST: the complete real CTA, expressed as ONE workflow definition built
entirely from the blocks shipped in blocks 1-4 — parallel quorum review (1),
mixed notify+action fan-out (2), ordered signing (3), notify-all broadcast (4) —
plus the pre-existing form/approval/decision/terminal steps. No new engine
features; this is pure assembly + an end-to-end walk.

The engine is PURE, so the walk is driven directly. A small in-test `Runner`
mirrors EXACTLY what the real service does for persistence + audit
(start_instance / perform_action / _log / _log_notifications), so the asserted
audit trail is the same one the service would write to WorkflowAuditEntry.

Flow (matches the drawio diagram):
  draft (form)
  -> internal_review (PARALLEL: internal_legal + internal_financial, quorum all)
  -> cro_gate (DECISION on has_cro)
       has_cro=true -> cro_review (PARALLEL: cro_legal + cro_financial, quorum all)
       has_cro=false-> site_team (MIXED FAN-OUT: notify pi/site_manager/crc;
                                  action site_legal/site_financial; quorum all)
  -> returned_main (DECISION pass-through) -> send_for_signatures (approval)
  -> signatures (ORDERED: site_director -> pi) -> vp_sign (ORDERED: vp)
  -> returned_main_2 (DECISION pass-through) -> executed (approval)
  -> distribute (BROADCAST to 6) -> done (terminal)

Rework/discussion loops (quorum_failed -> rework -> back into review, and an
"internal review again" backward edge) are present as plain backward transitions
but are NOT traversed by the two happy paths — see the limitation note at the
bottom of this file.

Run:
    pytest tests/test_full_cta.py -v
    python  tests/test_full_cta.py
"""

import os
import sys

_HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..")))
sys.path.insert(0, _HERE)

from app.modules.workflows.engine import WorkflowEngine  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


DISTRIBUTE_RECIPIENTS = ["pi", "site_manager", "site_legal", "site_financial", "crc", "site_director"]
SITE_TEAM_NOTIFY = ["pi", "site_manager", "crc"]


def cta_def() -> WorkflowDefinitionBody:
    raw = {
        "key": "CTA_FULL",
        "name": "Clinical Trial Agreement (full assembly)",
        "description": "Complete CTA assembled from blocks 1-4.",
        "start_step": "draft",
        "context_schema": [{"key": "has_cro", "label": "CRO involved?", "type": "boolean"}],
        "steps": [
            # 1. Main user creates document
            {"id": "draft", "type": "form", "name": "Main User Creates Document",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "submit", "to": "internal_review",
                              "label": "Send for internal review", "action": "submit"}]},

            # 2. Internal review — PARALLEL (legal + financial), quorum all
            {"id": "internal_review", "type": "parallel", "name": "Internal Review",
             "config": {
                 "branches": [
                     {"id": "internal_legal", "name": "Internal Legal Reviewer",
                      "assignee": {"type": "role", "value": "legal"}},
                     {"id": "internal_financial", "name": "Internal Financial Reviewer",
                      "assignee": {"type": "role", "value": "financial"}},
                 ],
                 "quorum": {"mode": "all"}, "on_reject": "count"},
             "transitions": [
                 {"id": "ir_ok", "to": "cro_gate", "label": "Both approved", "action": "quorum_met"},
                 # rework / "internal review again": plain backward edge (NOT walked)
                 {"id": "ir_rework", "to": "draft", "label": "Send back to main user", "action": "quorum_failed"},
             ]},

            # 3. Does CRO exist? — DECISION on has_cro
            {"id": "cro_gate", "type": "decision", "name": "Does CRO Exist?",
             "transitions": [
                 {"id": "cro_yes", "to": "cro_review", "label": "CRO exists", "action": "auto",
                  "condition": {"all": [{"field": "has_cro", "op": "is_true"}]}},
                 {"id": "cro_no", "to": "site_team", "label": "No CRO", "action": "auto"},
             ]},

            # 4. CRO review — PARALLEL (cro legal + cro financial), quorum all
            {"id": "cro_review", "type": "parallel", "name": "CRO Review",
             "config": {
                 "branches": [
                     {"id": "cro_legal", "name": "CRO Legal Reviewer",
                      "assignee": {"type": "role", "value": "legal"}},
                     {"id": "cro_financial", "name": "CRO Financial Reviewer",
                      "assignee": {"type": "role", "value": "financial"}},
                 ],
                 "quorum": {"mode": "all"}, "on_reject": "count"},
             "transitions": [
                 {"id": "cro_ok", "to": "returned_main", "label": "Approved", "action": "quorum_met"},
                 # "Discussion with Internal Reviewer" rework loop (NOT walked)
                 {"id": "cro_rwk", "to": "cro_rework", "label": "Needs discussion", "action": "quorum_failed"},
             ]},
            {"id": "cro_rework", "type": "approval", "name": "Discussion with Internal Reviewer",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "cro_redo", "to": "cro_review",
                              "label": "Send back to CRO review", "action": "rework"}]},

            # 5. Site team — MIXED FAN-OUT (notify 3 + action 2), quorum all over action
            {"id": "site_team", "type": "parallel", "name": "Send to Site Team",
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
                 "quorum": {"mode": "all"}, "on_reject": "count"},
             "transitions": [
                 {"id": "st_ok", "to": "returned_main", "label": "Review Updates Finalized", "action": "quorum_met"},
                 {"id": "st_rwk", "to": "site_rework", "label": "Needs discussion", "action": "quorum_failed"},
             ]},
            {"id": "site_rework", "type": "approval", "name": "Discussion with Internal Reviewer (site)",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "st_redo", "to": "site_team",
                              "label": "Send back to site team", "action": "rework"}]},

            # 6. Convergence: Document Returned to Main User (pass-through) -> Send for Signatures
            {"id": "returned_main", "type": "decision", "name": "Document Returned to Main User",
             "transitions": [{"id": "rm_go", "to": "send_for_signatures",
                              "label": "Proceed to signatures", "action": "auto"}]},
            {"id": "send_for_signatures", "type": "approval", "name": "Send for Signatures",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "sfs_go", "to": "signatures", "label": "Send", "action": "send"}]},

            # 7. Site signatures — ORDERED (site director first, then PI)
            {"id": "signatures", "type": "ordered_signing", "name": "Site Signatures",
             "config": {"signers": [
                 {"id": "site_director", "name": "Site Director",
                  "assignee": {"type": "role", "value": "sponsor"}},
                 {"id": "pi", "name": "PI", "assignee": {"type": "role", "value": "coordinator"}},
             ]},
             "transitions": [{"id": "site_done", "to": "vp_sign",
                              "label": "All site signatures complete", "action": "all_signed"}]},

            # 8. VP signature — ORDERED (single signer)
            {"id": "vp_sign", "type": "ordered_signing", "name": "VP Signature",
             "config": {"signers": [{"id": "vp", "name": "VP",
                                     "assignee": {"type": "role", "value": "sponsor"}}]},
             "transitions": [{"id": "vp_done", "to": "returned_main_2",
                              "label": "VP signed", "action": "all_signed"}]},

            # 9. Document Returned to Main User (pass-through) -> Final Executed Document
            {"id": "returned_main_2", "type": "decision", "name": "Document Returned to Main User",
             "transitions": [{"id": "rm2_go", "to": "executed", "label": "Finalize", "action": "auto"}]},
            {"id": "executed", "type": "approval", "name": "Final Executed Document",
             "assignee": {"type": "role", "value": "study_manager"},
             "transitions": [{"id": "exec_go", "to": "distribute", "label": "Distribute final copy", "action": "distribute"}]},

            # 10. Distribute — BROADCAST to 6 -> done
            {"id": "distribute", "type": "broadcast", "name": "Distribute Final Copy",
             "config": {"recipients": [{"id": r, "name": r} for r in DISTRIBUTE_RECIPIENTS]},
             "transitions": [{"id": "dist_done", "to": "done", "label": "Distributed", "action": "broadcast_done"}]},

            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    return WorkflowDefinitionBody.model_validate(raw)


def U(uid: str) -> CurrentUser:
    return CurrentUser(id=uid, roles=[])  # open mode


class Runner:
    """Faithful in-test mirror of the real service's persistence + audit, so the
    asserted audit trail equals what WorkflowAuditEntry would receive."""

    def __init__(self, engine: WorkflowEngine):
        self.e = engine
        self.context: dict = {}
        self.current = None
        self.status = "active"
        self.audit: list[dict] = []
        self.visited: list[str] = []

    def start(self, context: dict):
        r = self.e.start(context)
        self.context, self.current = r.context, r.step_id
        self.visited += r.visited
        self.audit.append({"action": "started", "from": None, "to": r.step_id, "branch": None, "actor": None})
        self._log_notified(r)
        if r.is_terminal:
            self.status = "completed"
        return r

    def act(self, transition_id: str, user: CurrentUser, comment: str | None = None):
        frm = self.current
        r = self.e.perform(frm, transition_id, self.context, user, comment=comment)
        self.context, self.current = r.context, r.step_id
        self.visited += r.visited
        if r.vote:  # parallel/fanout vote or signature/decline
            action, branch = r.vote["decision"], r.vote["branch_id"]
        else:
            action, branch = self._verb(frm, transition_id), None
        self.audit.append({"action": action, "from": frm, "to": r.step_id, "branch": branch, "actor": user.id})
        self._log_notified(r)
        if r.is_terminal:
            self.status = "completed"
        return r

    def _log_notified(self, r):
        for bid in r.notified:
            self.audit.append({"action": "notified", "from": r.step_id, "to": r.step_id, "branch": bid, "actor": None})

    def _verb(self, step_id, transition_id):
        for t in self.e.step(step_id).transitions:
            if t.id == transition_id:
                return t.action
        return "action"

    # convenience filters for assertions
    def actions(self):
        return [a["action"] for a in self.audit]

    def votes(self, decision):
        return {a["branch"] for a in self.audit if a["action"] == decision and a["branch"]}

    def notified_count(self):
        return sum(1 for a in self.audit if a["action"] == "notified")


def _run_common_tail(run: Runner):
    """returned_main -> send_for_signatures -> ordered site sign -> vp -> executed
       -> distribute -> done. Shared by both paths."""
    assert run.current == "send_for_signatures", run.current
    run.act("sfs_go", U("main"))
    assert run.current == "signatures", run.current
    run.act("site_director:sign", U("dir"))
    assert run.current == "signatures"          # PI not yet
    run.act("pi:sign", U("pi_user"))
    assert run.current == "vp_sign", run.current
    run.act("vp:sign", U("vp_user"))
    assert run.current == "executed", run.current
    r = run.act("exec_go", U("main"))           # crosses broadcast -> done
    assert run.current == "done" and r.is_terminal, run.current


def walk_path_a():
    run = Runner(WorkflowEngine(cta_def(), enforce_roles=False))
    run.start({"has_cro": True})
    assert run.current == "draft"
    run.act("submit", U("main"))
    assert run.current == "internal_review"
    run.act("internal_legal:approve", U("il"))
    run.act("internal_financial:approve", U("if"))      # quorum -> cro_gate(true) -> cro_review
    assert run.current == "cro_review", run.current
    run.act("cro_legal:approve", U("cl"))
    run.act("cro_financial:approve", U("cf"))           # quorum -> returned_main -> send_for_signatures
    _run_common_tail(run)
    return run


def walk_path_b():
    run = Runner(WorkflowEngine(cta_def(), enforce_roles=False))
    run.start({"has_cro": False})
    run.act("submit", U("main"))
    run.act("internal_legal:approve", U("il"))
    run.act("internal_financial:approve", U("if"))      # quorum -> cro_gate(false) -> site_team
    assert run.current == "site_team", run.current
    run.act("site_legal:approve", U("sl"))
    run.act("site_financial:approve", U("sf"))           # action quorum -> returned_main -> send_for_signatures
    _run_common_tail(run)
    return run


# ---------------------------------------------------------------------------
# PATH A  (has_cro = true)
# ---------------------------------------------------------------------------
def test_path_a_with_cro():
    run = walk_path_a()
    assert run.status == "completed"
    # Every meaningful node was traversed.
    assert set(run.visited) >= {
        "draft", "internal_review", "cro_gate", "cro_review", "returned_main",
        "send_for_signatures", "signatures", "vp_sign", "returned_main_2",
        "executed", "distribute", "done",
    }
    # Audit: 4 approvals, 3 signatures, 6 notifications, plus start/submit/send/etc.
    assert run.votes("approve") == {"internal_legal", "internal_financial", "cro_legal", "cro_financial"}
    assert run.votes("signed") == {"site_director", "pi", "vp"}
    assert run.notified_count() == 6
    assert {a["branch"] for a in run.audit if a["action"] == "notified"} == set(DISTRIBUTE_RECIPIENTS)
    assert run.actions().count("started") == 1
    assert "submit" in run.actions() and "send" in run.actions() and "distribute" in run.actions()


# ---------------------------------------------------------------------------
# PATH B  (has_cro = false)
# ---------------------------------------------------------------------------
def test_path_b_no_cro():
    run = walk_path_b()
    assert run.status == "completed"
    assert set(run.visited) >= {
        "draft", "internal_review", "cro_gate", "site_team", "returned_main",
        "send_for_signatures", "signatures", "vp_sign", "returned_main_2",
        "executed", "distribute", "done",
    }
    assert "cro_review" not in run.visited      # CRO branch skipped
    # Internal + site action approvals (4 total); site_team notify (3) + distribute (6) notifications.
    assert run.votes("approve") == {"internal_legal", "internal_financial", "site_legal", "site_financial"}
    assert run.votes("signed") == {"site_director", "pi", "vp"}
    assert run.notified_count() == 3 + 6
    # site_team delivered to its 3 notify recipients (recorded in branch state).
    st = run.context["_branches"]["site_team"]
    assert all(st[n]["decision"] == "notified" for n in SITE_TEAM_NOTIFY)


# ---------------------------------------------------------------------------
# Audit completeness across the whole run (both paths)
# ---------------------------------------------------------------------------
def test_audit_trail_complete():
    for run in (walk_path_a(), walk_path_b()):
        kinds = {a["action"] for a in run.audit}
        # every category present: lifecycle, votes, signatures, notifications
        assert "started" in kinds
        assert "approve" in kinds            # parallel/fanout votes
        assert "signed" in kinds             # ordered signatures
        assert "notified" in kinds           # broadcast (+ fanout on path B)
        # nothing un-actored except system events (started / notified)
        for a in run.audit:
            if a["action"] in ("started", "notified"):
                assert a["actor"] is None
            else:
                assert a["actor"] is not None


_TESTS = [
    ("PATH A (has_cro=true)", test_path_a_with_cro,
     "draft -> internal parallel -> CRO parallel -> ordered sign -> VP -> distribute(6) -> done"),
    ("PATH B (has_cro=false)", test_path_b_no_cro,
     "draft -> internal parallel -> site mixed fan-out (3 notify + 2 action) -> ... -> done"),
    ("audit trail complete", test_audit_trail_complete,
     "every step, vote, signature and notification recorded across both runs"),
]


def _print_audit(title, run):
    print(f"\n--- audit trail: {title} ({len(run.audit)} rows) ---")
    for a in run.audit:
        b = f" [{a['branch']}]" if a["branch"] else ""
        who = a["actor"] or "system"
        print(f"  {a['action']:<10}{b:<18} {str(a['from']):<22} -> {a['to']:<22} ({who})")


if __name__ == "__main__":
    print("=" * 78)
    print("Workflow engine — FULL CTA assembly (blocks 1-4)")
    print("=" * 78)
    failures = 0
    for label, fn, summary in _TESTS:
        try:
            fn()
            print(f"PASS  {label}\n        -> {summary}")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {label}\n        -> {type(exc).__name__}: {exc}")
    # Show the two full audit trails for the report.
    _print_audit("PATH A (has_cro=true)", walk_path_a())
    _print_audit("PATH B (has_cro=false)", walk_path_b())
    print("=" * 78)
    print(f"{len(_TESTS) - failures}/{len(_TESTS)} passed")
    sys.exit(1 if failures else 0)

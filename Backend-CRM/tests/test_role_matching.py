"""
test_role_matching.py
=====================

Workflow authorization respects REAL IAM roles (no hardcoded allow-list, no
squash-to-participant) and the owner/drafter step binds to the agreement CREATOR
by id, not a role.

  * role_slug / role_matches — canonical slug comparison on BOTH sides, so
    "Contract Specialist" == "contract_specialist".
  * A user whose real IAM role is "Contract Specialist" can act on a step
    assigned that role (any casing/spacing) — not squashed away.
  * An owner step authored as {type: context, value: owner_user_id} matches the
    creator by id regardless of their role; a non-creator cannot act.
  * normalize_draft rebinds the document_create (draft) step to the owner context.

Pure engine + pure normalizer — no DB. Run: pytest tests/test_role_matching.py -v
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.modules.workflows.engine import (  # noqa: E402
    WorkflowEngine,
    role_matches,
    role_slug,
)
from app.modules.workflows.generate import normalize_draft  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def U(uid, *roles):
    return CurrentUser(id=uid, roles=list(roles))


def _draft_def(assignee):
    return {
        "key": "ROLE_T", "name": "Role test", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft", "assignee": assignee,
             "transitions": [{"id": "go", "to": "done", "label": "Submit", "action": "submit"}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }


def _eng(raw):
    # Default enforce_roles=True (strict) — the only behavior in the app.
    return WorkflowEngine(WorkflowDefinitionBody.model_validate(raw))


# ---------------------------------------------------------------------------
# Slug matching
# ---------------------------------------------------------------------------
def test_role_slug_canonicalizes():
    assert role_slug("Contract Specialist") == "contract_specialist"
    assert role_slug("CONTRACT-SPECIALIST") == "contract_specialist"
    assert role_slug("  study_manager ") == "study_manager"
    assert role_slug("CRA") == "cra"
    assert role_slug("") == "" and role_slug(None) == ""


def test_role_matches_both_sides_slugged():
    assert role_matches("Contract Specialist", ["contract_specialist"])
    assert role_matches("contract_specialist", ["Contract Specialist"])
    assert role_matches("legal", ["legal"])                       # legacy snake_case unaffected
    assert role_matches("Legal", ["legal", "Contract Specialist"])
    assert not role_matches("study_manager", ["Contract Specialist"])
    assert not role_matches("", ["anything"])


# ---------------------------------------------------------------------------
# A real IAM role is honored, not squashed
# ---------------------------------------------------------------------------
def test_user_with_real_iam_role_can_act():
    eng = _eng(_draft_def({"type": "role", "value": "Contract Specialist"}))
    r = eng.start({})
    # The user holds the role under a different casing/format — still matches.
    acts = eng.available_actions("draft", r.context, U("u1", "contract_specialist"))
    assert [a.transition_id for a in acts] == ["go"]
    # A user without that role cannot act.
    assert eng.available_actions("draft", r.context, U("u2", "Sponsor")) == []


def test_legacy_snake_case_role_still_matches():
    eng = _eng(_draft_def({"type": "role", "value": "legal"}))
    r = eng.start({})
    assert eng.available_actions("draft", r.context, U("l", "legal"))
    assert eng.available_actions("draft", r.context, U("x", "financial")) == []


# ---------------------------------------------------------------------------
# Owner step = the creator (context binding), independent of role
# ---------------------------------------------------------------------------
def test_owner_context_step_matches_creator_by_id_regardless_of_role():
    eng = _eng(_draft_def({"type": "context", "value": "owner_user_id"}))
    r = eng.start({"owner_user_id": "creator-1"})
    # The creator can act with NO role at all.
    assert eng.available_actions("draft", r.context, U("creator-1"))
    # A different user cannot — even with a strong-sounding role.
    assert eng.available_actions("draft", r.context, U("other", "study_manager")) == []


# ---------------------------------------------------------------------------
# The normalizer authors the owner/draft step as the creator (context)
# ---------------------------------------------------------------------------
def test_normalizer_keeps_draft_step_role_based():
    # DECISION: every step — including the draft/owner — is matched by ROLE. The
    # normalizer assigns module document_create but must NOT rebind the draft to a
    # creator/context assignee; it keeps the authored role.
    body = {
        "key": "GEN", "name": "Gen", "start_step": "draft",
        "steps": [
            {"id": "draft", "type": "form", "name": "Draft",
             "assignee": {"type": "role", "value": "CRA"},
             "transitions": [{"id": "submit", "to": "review", "label": "Submit", "action": "submit"}]},
            {"id": "review", "type": "approval", "name": "Legal Review",
             "assignee": {"type": "role", "value": "Contract Specialist"},
             "transitions": [
                 {"id": "ok", "to": "done", "label": "Approve", "action": "approve"},
                 {"id": "back", "to": "draft", "label": "Send back", "action": "send_back",
                  "requires_comment": True}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
        ],
    }
    fixed = normalize_draft(body)
    steps = {s["id"]: s for s in fixed["steps"]}
    # Draft is module document_create but STILL a ROLE assignee (not context).
    assert steps["draft"]["module"] == "document_create"
    assert steps["draft"]["assignee"] == {"type": "role", "value": "CRA"}
    # Reviewer keeps its real IAM role too.
    assert steps["review"]["assignee"] == {"type": "role", "value": "Contract Specialist"}
    WorkflowDefinitionBody.model_validate(fixed)


def test_real_roles_block_in_prompt_uses_vocabulary():
    # The generator prompt lists the real IAM roles and forbids invented ones.
    from app.modules.workflows.generate import build_system_prompt
    p = build_system_prompt(["CONTRACT_SPECIALIST", "CRA", "PRINCIPAL_INVESTIGATOR"])
    assert "REAL ROLES IN THIS SYSTEM" in p
    assert "CONTRACT_SPECIALIST" in p and "CRA" in p and "PRINCIPAL_INVESTIGATOR" in p
    # No vocabulary passed -> no real-roles block (graceful fallback).
    assert "REAL ROLES IN THIS SYSTEM" not in build_system_prompt()


_TESTS = [
    test_role_slug_canonicalizes,
    test_role_matches_both_sides_slugged,
    test_user_with_real_iam_role_can_act,
    test_legacy_snake_case_role_still_matches,
    test_owner_context_step_matches_creator_by_id_regardless_of_role,
    test_normalizer_keeps_draft_step_role_based,
    test_real_roles_block_in_prompt_uses_vocabulary,
]

if __name__ == "__main__":
    for t in _TESTS:
        t()
        print("PASS", t.__name__)
    print("ok")

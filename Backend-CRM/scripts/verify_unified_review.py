"""
Verify the UNIFIED review/comment module's CYCLE (run in the backend container),
exercising the real unified_review service against the engine.

Cycle: at the review step -> reviewer SEND_BACK -> engine loops to edit (draft) ->
owner revises + re-submits -> review step again -> reviewer APPROVE -> engine
forwards (terminal). Plus: owner-can't-self-approve (response is token-gated), the
context gate, and dispatch-is-creator-owns. Throwaway data; cleaned up.

(dispatch itself reuses send_agreement_for_review — verified by import; the CYCLE
core proven here is the reviewer response advancing the engine + the loop.)
"""
import asyncio
import secrets
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, AgreementReviewToken, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.agreements.services import unified_review as ur  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402


def body(key):
    return {"key": key, "name": "Review cycle", "start_step": "draft", "context_schema": [],
            "steps": [
                # Owner/drafter step is bound to the agreement CREATOR via context
                # (ensure_instance fills owner_user_id from Agreement.created_by) —
                # exactly how the real template-driven workflows author it.
                {"id": "draft", "type": "form", "name": "Edit", "module": "document_create",
                 "assignee": {"type": "context", "value": "owner_user_id"},
                 "transitions": [{"id": "submit", "to": "review", "label": "Send for review", "action": "submit"}]},
                # Review step carries NO assignee: the external reviewer is authorized
                # by their review TOKEN, not an IAM role. unified_review binds the step
                # to the reviewer's email via the engine reassignment override.
                # send_back carries requires_comment=True — the generator's default for
                # review rework — so this exercises the engine's comment gate that the
                # token reviewer's response must satisfy (respond() supplies the comment).
                {"id": "review", "type": "approval", "name": "Legal Review", "module": "review",
                 "transitions": [
                     {"id": "ok", "to": "done", "label": "Approve", "action": "approve"},
                     {"id": "back", "to": "draft", "label": "Send back", "action": "send_back",
                      "requires_comment": True}]},
                {"id": "done", "type": "terminal", "name": "Approved", "transitions": []}]}


async def _make(db, created_by):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                   title="REVIEW-CYCLE", status=AgreementStatus.DRAFT, is_legacy="false", created_by=created_by)
    db.add(ag); await db.flush()
    aid = str(ag.id); await db.commit()
    return aid


async def _seed_review_token(db, aid, email):
    tok = secrets.token_urlsafe(16)
    db.add(AgreementReviewToken(agreement_id=aid, token=tok, recipient_email=email,
                                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
                                created_by="owner-1", is_active="true"))
    await db.commit()
    return tok


async def _submit_draft(db, aid):
    """Owner advances the edit/draft step -> review (engine 'submit')."""
    inst = await wf.find_instance_by_subject(db, aid)
    async with transactional(db):
        await wf.perform_action(db, inst.id, CurrentUser(id="owner-1", roles=[]), "submit", {})


async def _current(db, aid):
    inst = await wf.find_instance_by_subject(db, aid)
    return inst.current_step, inst.status


async def _cleanup(db, aid, key):
    await db.execute(text("DELETE FROM agreement_review_tokens WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": key})).fetchone()
    if d:
        await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
    await db.commit()


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        aid = await _make(db, "owner-1")
        key = f"tpl:{aid}"
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(body(key)), publish=True, published_by="verify")
        async with transactional(db):
            await wf.ensure_instance(db, key, aid, {"agreement_id": aid})
        try:
            # permissions: dispatch is creator-owns
            assert (await wf.is_agreement_owner(db, aid, "owner-1"))["is_owner"]
            assert not (await wf.is_agreement_owner(db, aid, "intruder"))["is_owner"]
            results.append(("Permissions: dispatch is creator-owns", "owner True / other False"))

            # owner sends draft -> review
            await _submit_draft(db, aid)
            step, _ = await _current(db, aid)
            assert step == "review", step
            results.append(("Owner submits edit -> engine at review step", f"current={step}"))

            # reviewer link active; context offers approve + send_back
            tok1 = await _seed_review_token(db, aid, "reviewer@org.com")
            ctx = await ur.context(db, aid, tok1)
            assert ctx["active"] and ctx["can_approve"] and ctx["can_send_back"], ctx
            results.append(("Reviewer context: approve + send-back available", f"{ctx}"))

            # owner cannot self-approve: response is token-gated (bad token -> 401)
            try:
                await ur.respond(db, aid, "not-a-real-token", "approve")
                raise AssertionError("expected 401 for invalid token")
            except HTTPException as e:
                assert e.status_code == 401
            results.append(("Owner can't self-approve: response requires the reviewer token", "bad token -> 401"))

            # SEND BACK -> engine loops to edit (draft)
            r1 = await ur.respond(db, aid, tok1, "send_back")
            step, _ = await _current(db, aid)
            assert step == "draft", step
            results.append(("Reviewer SEND-BACK -> engine loops to edit", f"transition={r1['transition']}, current={step}"))
            # token consumed
            assert not (await ur.context(db, aid, tok1))["active"]

            # owner revises + re-sends -> review again
            await _submit_draft(db, aid)
            step, _ = await _current(db, aid)
            assert step == "review", step
            tok2 = await _seed_review_token(db, aid, "reviewer@org.com")
            assert (await ur.context(db, aid, tok2))["active"]
            results.append(("Owner revises + re-sends -> review again (cycle repeats)", f"current={step}"))

            # APPROVE -> engine forwards (terminal)
            r2 = await ur.respond(db, aid, tok2, "approve")
            step, status = await _current(db, aid)
            assert step == "done" or status == "completed", (step, status)
            results.append(("Reviewer APPROVE -> engine forwards to terminal", f"transition={r2['transition']}, current={step}, status={status}"))

            # gate: context inactive once the review step is gone (engine terminal).
            # (The former WORKFLOW_UNIFIED flag was removed — unified review is always
            # on. The external reviewer is authorized by their token, not a role: the
            # review step here carries NO assignee, and the cycle above proves the
            # token->step reassignment override admits the reviewer under strict
            # enforcement.)
            tok3 = await _seed_review_token(db, aid, "reviewer@org.com")
            assert (await ur.context(db, aid, tok3))["active"] is False
            results.append(("Gate: context inactive after the review step completes", "no approval step -> no actions"))
        finally:
            await _cleanup(db, aid, key)

    print("=" * 92)
    print("UNIFIED REVIEW/COMMENT MODULE — CYCLE VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

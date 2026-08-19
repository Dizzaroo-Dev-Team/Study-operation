"""
Verify PART A — the parallel multi-reviewer review capability (run in backend
container). A review step typed `parallel` + module "review": two reviewers (legal +
financial), each dispatched their own secure link; the engine advances ONLY when BOTH
approve (quorum=all); any send-back loops to edit; approval requires a reviewer token
(owner can't self-approve via the API). Throwaway data; cleaned up.
"""
import asyncio
import sys
import tempfile

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, AgreementDocument, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.agreements.services import unified_review as ur  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

EMAIL = "labesh@dizzaroo.com"


def body(key):
    return {"key": key, "name": "Parallel review", "start_step": "draft", "context_schema": [],
            "steps": [
                # Owner/drafter step bound to the agreement CREATOR via context
                # (ensure_instance fills owner_user_id from Agreement.created_by).
                {"id": "draft", "type": "form", "name": "Create Document", "module": "document_create",
                 "assignee": {"type": "context", "value": "owner_user_id"},
                 "transitions": [{"id": "submit", "to": "review", "label": "Send for review", "action": "submit"}]},
                # Parallel branches carry NO assignee: each reviewer is authorized by
                # their review TOKEN. parallel_dispatch binds each branch to its
                # reviewer's email via the engine reassignment override.
                {"id": "review", "type": "parallel", "name": "Legal and Financial Review", "module": "review",
                 "config": {"quorum": {"mode": "all"}, "on_reject": "fail_fast", "branches": [
                     {"id": "legal", "name": "Legal", "kind": "action", "action_approve": "approve", "action_reject": "reject"},
                     {"id": "financial", "name": "Financial", "kind": "action", "action_approve": "approve", "action_reject": "reject"}]},
                 "transitions": [{"id": "ok", "to": "end", "label": "Both approve", "action": "quorum_met"},
                                 {"id": "back", "to": "draft", "label": "Send back", "action": "quorum_failed"}]},
                {"id": "end", "type": "terminal", "name": "Done", "transitions": []}]}


async def _make(db, key):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites WHERE id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                   title="PAR-REVIEW", status=AgreementStatus.DRAFT, is_legacy="false", created_by="owner")
    db.add(ag); await db.flush()
    # Real DOCX — parallel_dispatch now reuses send_agreement_for_review, which clones a
    # review copy from the latest document, so an empty temp file won't do.
    db.add(AgreementDocument(agreement_id=ag.id, version_number=1,
                             document_file_path="/app/uploads/templates/template_75a4022f-98fb-4c2f-a483-91bdbbae1a1a.docx",
                             created_by="owner", is_signed_version="false"))
    await db.flush()
    aid = str(ag.id); await db.commit()
    async with transactional(db):
        await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(body(key)), publish=True, published_by="v")
    async with transactional(db):
        await wf.ensure_instance(db, key, aid, {"agreement_id": aid})
    inst = await wf.find_instance_by_subject(db, aid)
    async with transactional(db):
        await wf.perform_action(db, inst.id, CurrentUser(id="owner", roles=[]), "submit", {})
    return aid, ag


async def _tokens(db, aid):
    inst = await wf.find_instance_by_subject(db, aid)
    return {b: t for t, b in ((inst.context or {}).get("_review_token_branch") or {}).items()}


async def _cleanup(db, aid, key):
    for t in ("agreement_review_tokens", "agreement_documents", "agreement_comments"):
        await db.execute(text(f"DELETE FROM {t} WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": key})).fetchone()
    if d:
        await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
    await db.commit()


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        # ===== quorum: both must approve =====
        key1 = "tpl:zz-parreview-1"
        aid, ag = await _make(db, key1)
        try:
            st = await ur.parallel_status(db, aid)
            assert st["active"] and {r["id"] for r in st["reviewers"]} == {"legal", "financial"}
            assert all(r["state"] == "open" for r in st["reviewers"]), st
            results.append(("Parallel review status: both reviewers open at the review step", "legal+financial open"))

            async with transactional(db):
                disp = await ur.parallel_dispatch(db, ag, {"legal": EMAIL, "financial": EMAIL}, {})
            assert {d["branch"] for d in disp["dispatched"] if d["status"] == "sent"} == {"legal", "financial"}
            results.append(("Dispatch: a distinct review link per reviewer branch", "legal+financial sent"))

            toks = await _tokens(db, aid)
            assert set(toks) == {"legal", "financial"} and toks["legal"] != toks["financial"]

            # owner can't self-approve: an invalid/owner token is rejected
            try:
                await ur.respond(db, aid, "not-a-real-token", "approve"); raise AssertionError("expected 401")
            except HTTPException as e:
                assert e.status_code == 401
            results.append(("Approval requires the reviewer's token (owner can't self-approve via API)", "401 on bad token"))

            # legal approves -> still parked (quorum not met)
            await ur.respond(db, aid, toks["legal"], "approve")
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "review", inst.current_step
            st = await ur.parallel_status(db, aid)
            assert next(r for r in st["reviewers"] if r["id"] == "legal")["state"] == "approved"
            assert next(r for r in st["reviewers"] if r["id"] == "financial")["state"] == "open"
            results.append(("One approval is NOT enough — engine waits for quorum", "legal approved, still at review"))

            # financial approves -> quorum met -> advances
            await ur.respond(db, aid, toks["financial"], "approve")
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "end" or inst.status == "completed", (inst.current_step, inst.status)
            results.append(("Both approve -> quorum met -> engine advances past review", f"-> {inst.current_step}/{inst.status}"))
        finally:
            await _cleanup(db, aid, key1)

        # ===== send-back loops to edit =====
        key2 = "tpl:zz-parreview-2"
        aid2, ag2 = await _make(db, key2)
        try:
            async with transactional(db):
                await ur.parallel_dispatch(db, ag2, {"legal": EMAIL, "financial": EMAIL}, {})
            toks2 = await _tokens(db, aid2)
            await ur.respond(db, aid2, toks2["legal"], "send_back")
            inst = await wf.find_instance_by_subject(db, aid2)
            assert inst.current_step == "draft", ("send-back must loop to edit", inst.current_step)
            results.append(("Any reviewer send-back -> loops back to draft for edits", "review -> draft"))
        finally:
            await _cleanup(db, aid2, key2)

    print("=" * 92)
    print("PARALLEL REVIEW (Part A) — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

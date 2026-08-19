"""
Verify NEED 1 (tracked two-party discussion step) + NEED 2 (mandatory signer-decline
reason stored with the document + audit). DB-backed — RUN IN THE BACKEND CONTAINER:

    docker exec backend-crm-backend-1 python /app/scripts/verify_discussion_and_decline.py   # expect 9/9

It reuses agreement_comments for the discussion store (no new comment table) and the
existing engine advance for "resolve". Throwaway data; cleaned up at the end. Flag is
forced ON for the run only (process-local) — prod defaults stay OFF.
"""

import asyncio
import sys

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

settings.workflow_unified = True            # discussion endpoints + decline persistence gate
settings.workflow_enforce_roles = False     # open mode (the unified flow default)

PASS, FAIL = "PASS", "FAIL"
_results = []


def check(label, ok, detail=""):
    _results.append(ok)
    print(f"  {PASS if ok else FAIL}  {label}" + (f"  -> {detail}" if detail else ""))


def U(uid):
    return CurrentUser(id=uid, roles=[])


KEY = "VERIFY_DISC_DECL"


def _body():
    return {
        "key": KEY, "name": "Discussion + decline", "start_step": "discuss", "context_schema": [],
        "steps": [
            # NEED 1 — tracked two-party discussion; "resolved" advances to signing.
            {"id": "discuss", "type": "approval", "name": "Legal Coordination", "module": "discussion",
             "config": {"discussion": {"parties": [
                 {"role": "site_legal", "label": "Site Legal"},
                 {"role": "internal_legal", "label": "Internal Legal"}], "resolve": "owner"}},
             "transitions": [{"id": "resolved", "to": "signing", "label": "Mark resolved", "action": "resolved"}]},
            # NEED 2 — signing step whose decline REQUIRES a reason.
            {"id": "signing", "type": "ordered_signing", "name": "VP Signature", "module": "signing",
             "config": {"signers": [{"id": "vp", "name": "VP"}]},
             "transitions": [
                 {"id": "ok", "to": "done", "label": "Signed", "action": "all_signed"},
                 {"id": "dec", "to": "rejected", "label": "Declined", "action": "signing_declined",
                  "requires_comment": True}]},
            {"id": "done", "type": "terminal", "name": "Done", "transitions": []},
            {"id": "rejected", "type": "terminal", "name": "Rejected", "transitions": []},
        ],
    }


async def _make_agreement(db, created_by):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites LIMIT 1"))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                   title="VERIFY discussion+decline", status=AgreementStatus.DRAFT,
                   is_legacy="false", created_by=created_by)
    db.add(ag)
    await db.flush()
    aid = str(ag.id)
    await db.commit()
    return aid


async def _cleanup(db, aid):
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN "
                          "(SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    defn = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": KEY})).fetchone()
    if defn:
        await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:d"), {"d": defn[0]})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id=:d"), {"d": defn[0]})
    await db.commit()


async def main():
    print("=" * 78)
    print("Verify - discussion step (NEED 1) + signer-decline reason (NEED 2)")
    print("=" * 78)
    owner = "owner-user"
    async with AsyncSessionLocal() as db:
        aid = await _make_agreement(db, owner)
        try:
            async with transactional(db):
                await wf.create_or_update_definition(
                    db, WorkflowDefinitionBody.model_validate(_body()), publish=True, published_by="verify")
            async with transactional(db):
                inst = await wf.start_instance(db, KEY, {}, subject_ref=aid)
            iid = inst.id
            check("instance starts parked at the discussion step", inst.current_step == "discuss",
                  f"current={inst.current_step}")

            # ---- NEED 1: two parties exchange tracked comments ------------------
            async with transactional(db):
                await wf.post_discussion(db, iid, U("site-legal-user"), "Clause 5 indemnity is too broad.", "external")
            async with transactional(db):
                await wf.post_discussion(db, iid, U("internal-legal-user"), "Agreed — narrowing it now.", "internal")
            thread = await wf.list_discussion(db, iid)
            check("both parties' comments are stored + visible to both", len(thread) == 2, f"count={len(thread)}")
            check("comments are ordered + attributed to each party/author",
                  thread[0]["party"] == "external" and thread[0]["author"] == "site-legal-user"
                  and thread[1]["party"] == "internal" and thread[1]["author"] == "internal-legal-user",
                  f"{[(c['party'], c['author']) for c in thread]}")

            # resolve -> advances to signing
            async with transactional(db):
                inst = await wf.perform_action(db, iid, U(owner), "resolved", {}, None)
            check("marking the discussion resolved advances the workflow", inst.current_step == "signing",
                  f"current={inst.current_step}")

            # ---- NEED 2: signer decline requires + stores a reason --------------
            declined = False
            try:
                async with transactional(db):
                    await wf.perform_action(db, iid, U("vp-user"), "vp:decline", {}, None)
            except wf.ServiceError as exc:
                declined = "reason" in str(exc).lower()
            check("declining with NO reason is rejected (reason mandatory)", declined)

            reason = "I cannot sign — the budget exceeds my delegated authority."
            async with transactional(db):
                inst = await wf.perform_action(db, iid, U("vp-user"), "vp:decline", {}, reason)
            check("declining WITH a reason advances on the send-back path", inst.current_step == "rejected",
                  f"current={inst.current_step}")

            # reason is in the workflow audit trail
            audit_comment = (await db.execute(text(
                "SELECT comment FROM workflow_audit_entries WHERE instance_id=:i AND action='declined' "
                "ORDER BY id DESC LIMIT 1"), {"i": iid})).scalar()
            check("the reason is in the audit trail", audit_comment == reason, f"audit={audit_comment!r}")

            # reason is stored WITH the document (a system agreement comment)
            doc_comment = (await db.execute(text(
                "SELECT content FROM agreement_comments WHERE agreement_id=:a AND comment_type='SYSTEM' "
                "AND content LIKE '%DECLINED%' ORDER BY created_at DESC LIMIT 1"), {"a": aid})).scalar()
            check("the reason is stored WITH the document (system comment)",
                  bool(doc_comment) and reason in (doc_comment or ""), f"doc_comment={doc_comment!r}")

            # discussion comments did NOT leak into the audit/system noise
            check("discussion thread excludes system comments", all(c["party"] != "system" for c in thread))
        finally:
            await _cleanup(db, aid)

    print("=" * 78)
    passed = sum(1 for r in _results if r)
    print(f"{passed}/{len(_results)} passed")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

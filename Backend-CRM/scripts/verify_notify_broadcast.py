"""
Verify the final module batch (run in backend container): generic APPROVAL (engine
advances on approve/reject — not a fake button), NOTIFY (real in-app notice fires),
BROADCAST (real per-recipient delivery with per-recipient results), and the gate.
Throwaway data; cleaned up.
"""
import asyncio
import sys
import tempfile

sys.path.insert(0, "/app")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import Agreement, AgreementStatus, AgreementDocument, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.agreements.services import unified_notify  # noqa: E402
from app.modules.agreements.routes.unified_notify import _require_unified  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import CurrentUser, WorkflowDefinitionBody  # noqa: E402

U = CurrentUser(id="owner-1", roles=[])


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def make_pdf(path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=letter); c.drawString(72, 720, "Final"); c.showPage(); c.save()


def appr_body(key):
    return {"key": key, "name": "Approval", "start_step": "appr", "context_schema": [],
            "steps": [
                {"id": "appr", "type": "approval", "name": "Approve", "module": "approval",
                 "transitions": [{"id": "ok", "to": "done", "label": "Approve", "action": "approve"},
                                 {"id": "no", "to": "draft", "label": "Reject", "action": "reject"}]},
                {"id": "draft", "type": "form", "name": "Edit",
                 "transitions": [{"id": "s", "to": "appr", "label": "Resubmit", "action": "submit"}]},
                {"id": "done", "type": "terminal", "name": "Done", "transitions": []}]}


async def _make(db):
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                   title="NOTIFY-BCAST", status=AgreementStatus.DRAFT, is_legacy="false", created_by="owner-1")
    db.add(ag); await db.flush()
    pdf = await asyncio.to_thread(_tmpfile, ".pdf")
    make_pdf(pdf)
    db.add(AgreementDocument(agreement_id=ag.id, version_number=1, document_file_path=pdf, created_by="owner-1", is_signed_version="false"))
    await db.flush()
    aid = str(ag.id); await db.commit()
    return aid


async def _cleanup(db, aid, key):
    await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
    await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_documents WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreement_comments WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": key})).fetchone()
    if d:
        await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
        await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
    await db.commit()


async def main():
    results = []
    settings.workflow_unified = True
    async with AsyncSessionLocal() as db:
        aid = await _make(db)
        key = f"tpl:{aid}"
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(appr_body(key)), publish=True, published_by="verify")
        async with transactional(db):
            await wf.ensure_instance(db, key, aid, {"agreement_id": aid})
        try:
            # APPROVAL: reject -> loops to draft (real action advances engine)
            inst = await wf.find_instance_by_subject(db, aid)
            async with transactional(db):
                await wf.perform_action(db, inst.id, U, "no", {})  # reject
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "draft", inst.current_step
            results.append(("Approval: REJECT advances engine (loops to edit)", "appr -> draft"))
            async with transactional(db):
                await wf.perform_action(db, inst.id, U, "s", {})   # resubmit
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "appr"
            # APPROVAL: approve -> forwards to terminal
            async with transactional(db):
                await wf.perform_action(db, inst.id, U, "ok", {})  # approve
            inst = await wf.find_instance_by_subject(db, aid)
            assert inst.current_step == "done" or inst.status == "completed", (inst.current_step, inst.status)
            results.append(("Approval: APPROVE advances engine (forwards)", f"-> {inst.current_step}/{inst.status}"))

            # NOTIFY: real in-app notice fires
            agreement = await db.get(Agreement, aid)
            n = await unified_notify.notify(db, agreement, "Workflow update: your action is requested.")
            assert n["fired"] is True, n
            results.append(("Notify: in-app notification fired (reuses create_agreement_notice)", f"fired={n['fired']}"))

            # BROADCAST: real per-recipient delivery + per-recipient results
            b = await unified_notify.broadcast(db, agreement, [
                {"email": "a@example.com", "name": "PI"},
                {"email": "b@example.com", "name": "CRC"},
                {"name": "NoEmail"},  # missing email -> reported not-sent
            ], attach_document=True)
            assert b["total"] == 3 and b["sent_count"] == 2, b
            assert b["attached"] is True, "final document attached (local PDF)"
            no_email = next(r for r in b["results"] if r["recipient"] == "NoEmail")
            assert no_email["sent"] is False and no_email["reason"] == "no email"
            results.append(("Broadcast: real per-recipient delivery + results tracked",
                            f"sent {b['sent_count']}/{b['total']}, attached={b['attached']}, NoEmail->not sent"))

            # GATE
            settings.workflow_unified = False
            try:
                _require_unified(); raise AssertionError("expected 403")
            except HTTPException as e:
                assert e.status_code == 403
            settings.workflow_unified = True
            results.append(("Gate: notify/broadcast 403 when flag off", "prod-safe"))
        finally:
            await _cleanup(db, aid, key)
            settings.workflow_unified = False

    print("=" * 92)
    print("FINAL BATCH (approval / notify / broadcast) — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

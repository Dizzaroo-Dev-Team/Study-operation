"""
Verify the signed (executed) PDF is persisted DURABLY (not /tmp) and that compliance
is intact (the durable artifact's bytes still hash to the recorded document_hash).
Run in backend container. In this fresh process Azure storage is OFF, so the signed
PDF must land under upload_dir/agreements/{id}/ — outside /tmp, surviving a restart.
Throwaway; cleaned up.
"""
import asyncio
import hashlib
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402
from app.config import settings  # noqa: E402
from app.db import AsyncSessionLocal, transactional  # noqa: E402
from app.models import (  # noqa: E402
    Agreement, AgreementStatus, AgreementDocument, AgreementSigningToken, AgreementSigningOtp, TemplateType,
)
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.agreements.services import unified_signing as us  # noqa: E402
from app.modules.workflows import service as wf  # noqa: E402
from app.modules.workflows.schemas import WorkflowDefinitionBody  # noqa: E402

KEY = "tpl:zz-durable"


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def make_pdf(path):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=letter); c.drawString(72, 720, "Durable test"); c.showPage(); c.save()


def ordered_body(key):
    return {"key": key, "name": "Durable", "start_step": "sign", "context_schema": [],
            "steps": [
                {"id": "sign", "type": "ordered_signing", "name": "Sign", "module": "signing",
                 "config": {"handoff": "owner_gated", "signers": [{"id": "s1", "name": "Signer One"}]},
                 "transitions": [{"id": "done", "to": "end", "label": "All signed", "action": "all_signed"}]},
                {"id": "end", "type": "terminal", "name": "Done", "transitions": []}]}


async def main():
    settings.workflow_unified = True
    async with AsyncSessionLocal() as db:
        ss = (await db.execute(text(
            "SELECT id,study_id,site_id FROM study_sites WHERE id NOT IN "
            "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"))).fetchone()
        ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                       title="DURABLE", status=AgreementStatus.DRAFT, is_legacy="false", created_by="owner-1")
        db.add(ag); await db.flush()
        pdf = await asyncio.to_thread(_tmpfile, ".pdf"); make_pdf(pdf)
        db.add(AgreementDocument(agreement_id=ag.id, version_number=1, document_file_path=pdf,
                                 created_by="owner-1", is_signed_version="false"))
        await db.flush(); aid = str(ag.id); await db.commit()
        async with transactional(db):
            await wf.create_or_update_definition(db, WorkflowDefinitionBody.model_validate(ordered_body(KEY)), publish=True, published_by="v")
        async with transactional(db):
            await wf.ensure_instance(db, KEY, aid, {"agreement_id": aid})
        # seed token + otp for s1, then submit a real signature
        tok = "durtok123"; db.add(AgreementSigningToken(agreement_id=aid, token=tok, role="s1",
              recipient_email="labesh@dizzaroo.com", expires_at=datetime.now(timezone.utc)+timedelta(days=1), is_active="true"))
        await db.commit()
        doc = await us._latest_doc(db, aid)
        db.add(AgreementSigningOtp(agreement_id=aid, document_id=doc.id, role="s1", email="labesh@dizzaroo.com",
              otp_hash=us._hash_otp_value("111111"), expires_at=datetime.now(timezone.utc)+timedelta(minutes=10),
              attempts=0, last_sent_at=datetime.now(timezone.utc), is_active="true")); await db.commit()

        rec = await us.submit(db, aid, tok, "111111", "Signer One", "PI", "I approve", "9.9.9.9")

        # ---- assertions ----
        row = (await db.execute(text(
            "SELECT document_file_path, is_signed_version FROM agreement_documents "
            "WHERE agreement_id=:a ORDER BY version_number DESC LIMIT 1"), {"a": aid})).fetchone()
        signed_path, is_signed = row[0], row[1]
        sd = (await db.execute(text("SELECT file_path FROM agreement_signed_documents WHERE agreement_id=:a"), {"a": aid})).scalar()
        sig_hash = (await db.execute(text("SELECT document_hash FROM agreement_internal_signatures WHERE agreement_id=:a"), {"a": aid})).scalar()

        results = []
        tmp_root = tempfile.gettempdir()
        assert is_signed == "true", is_signed
        assert not signed_path.startswith(tmp_root), ("signed doc must NOT be in the temp dir", signed_path)
        assert "agreements" in signed_path and signed_path.endswith(".pdf"), signed_path
        assert Path(signed_path).exists(), ("durable file missing", signed_path)
        results.append(("Signed AgreementDocument points at DURABLE path (not temp dir), file exists", signed_path))

        assert sd and not sd.startswith(tmp_root) and Path(sd).exists(), ("signed_documents path", sd)
        results.append(("AgreementSignedDocument.file_path is durable + exists", sd))

        disk_hash = hashlib.sha256(Path(signed_path).read_bytes()).hexdigest()
        assert disk_hash == sig_hash == rec["document_hash"], (disk_hash, sig_hash, rec["document_hash"])
        results.append(("Compliance intact: sha256(durable file) == recorded document_hash", disk_hash[:16] + "…"))

        upload_root = str((Path(settings.upload_dir) / "agreements").resolve())
        assert signed_path.startswith(upload_root), ("under upload_dir (storage off)", signed_path, upload_root)
        results.append(("Storage OFF -> persisted under upload_dir (survives restart)", upload_root))

        # cleanup
        for t in ("agreement_internal_signatures", "agreement_signed_documents", "agreement_signing_otps",
                  "agreement_signing_tokens", "agreement_documents", "agreement_comments"):
            await db.execute(text(f"DELETE FROM {t} WHERE agreement_id=:a"), {"a": aid})
        await db.execute(text("DELETE FROM audit_logs WHERE target_id=:a"), {"a": aid})
        await db.execute(text("DELETE FROM workflow_audit_entries WHERE instance_id IN (SELECT id FROM workflow_instances WHERE subject_ref=:a)"), {"a": aid})
        await db.execute(text("DELETE FROM workflow_instances WHERE subject_ref=:a"), {"a": aid})
        await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
        d = (await db.execute(text("SELECT id FROM workflow_definitions WHERE key=:k"), {"k": KEY})).fetchone()
        if d:
            await db.execute(text("DELETE FROM workflow_definition_versions WHERE definition_id=:i"), {"i": d[0]})
            await db.execute(text("DELETE FROM workflow_definitions WHERE id=:i"), {"i": d[0]})
        await db.commit()
        settings.workflow_unified = False

    print("=" * 92)
    print("SIGNED PDF DURABLE PERSISTENCE — VERIFICATION")
    print("=" * 92)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 92)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

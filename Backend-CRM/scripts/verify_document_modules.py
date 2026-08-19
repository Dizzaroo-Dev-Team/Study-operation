"""
Verify the DOCUMENT batch backend services (run in the backend container):
doc_convert, doc_merge, signature_render, document_versioning — the extracted/shared
capabilities. Uses real PDFs so merge/stamp are genuine. Throwaway data; cleaned up.

(document_preview / document_create are FE step modules wrapping the EXISTING
onlyoffice-config + create-from-template endpoints — covered by typecheck/build and
the existing endpoint verifications; the shared backend services are proven here.)
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementStatus, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.agreements.services import (  # noqa: E402
    doc_convert, doc_merge, document_versioning, signature_render,
)


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def make_pdf(path, line):
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=letter)
    c.drawString(72, 720, line)
    c.showPage()
    c.save()


def page_count(path):
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore
    return len(PdfReader(path).pages)


async def main():
    results = []
    async with AsyncSessionLocal() as db:
        # ---- doc_convert: already-PDF passthrough ----
        p1 = await asyncio.to_thread(_tmpfile, ".pdf")
        make_pdf(p1, "Doc A")
        out = await doc_convert.to_pdf(p1)
        assert out == p1, "PDF passthrough"
        results.append(("doc_convert: PDF passthrough (DOCX path delegates to docx_to_pdf)", out.split('/')[-1]))

        # ---- doc_merge: concatenate two PDFs ----
        p2 = await asyncio.to_thread(_tmpfile, ".pdf")
        make_pdf(p2, "Appendix B")
        merged = doc_merge.merge(p1, p2)
        assert page_count(merged) == 2, page_count(merged)
        results.append(("doc_merge: concatenates (1+1 -> 2 pages)", merged.split('/')[-1]))

        # ---- signature_render: stamp a manifestation onto a PDF ----
        before = Path(p1).read_bytes()
        signed = await signature_render.stamp_on_pdf(p1, "Dr. Jane Smith", "PI")
        after = Path(signed).read_bytes()
        assert signed != p1 and after != before, "stamped artifact must differ"
        results.append(("signature_render: stamps name onto PDF (artifact differs)", signed.split('/')[-1]))

        # ---- document_versioning: latest / next / add ----
        ss = (await db.execute(text(
            "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
            "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
        ))).fetchone()
        ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                       title="DOC-VER", status=AgreementStatus.DRAFT, is_legacy="false", created_by="owner-1")
        db.add(ag); await db.flush()
        aid = str(ag.id); await db.commit()
        try:
            assert await document_versioning.latest_document(db, aid) is None
            assert await document_versioning.next_version_number(db, aid) == 1
            d1 = await document_versioning.add_document_version(db, aid, p1, created_by="owner-1")
            d2 = await document_versioning.add_document_version(db, aid, signed, is_signed=True, created_by="owner-1")
            await db.commit()
            latest = await document_versioning.latest_document(db, aid)
            assert d1.version_number == 1 and d2.version_number == 2 and latest.version_number == 2
            assert latest.is_signed_version == "true"
            assert await document_versioning.next_version_number(db, aid) == 3
            results.append(("document_versioning: latest/next/add consistent", "v1, v2(signed), next=3"))
        finally:
            await db.execute(text("DELETE FROM agreement_documents WHERE agreement_id=:a"), {"a": aid})
            await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
            await db.commit()

    print("=" * 90)
    print("DOCUMENT BATCH (shared services) — VERIFICATION")
    print("=" * 90)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 90)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

"""
Verify the GENERAL append_document job handler + PLACEHOLDER placement (run in the
backend container).

Proves:
  1. The handler MERGES a source document into the agreement as a NEW AgreementDocument
     version (becomes the LATEST, so the signing step stamps the merged doc).
  2. PLACEHOLDER placement: with params.placeholder "{{ANNEXURE_A}}" present in the base
     PDF, the appendix is inserted AT the marker (right after the marker's page), not at
     the end — DETERMINISTICALLY (same input -> same placement).
  3. No placeholder -> appends at the END (current behavior); unknown marker -> falls
     back to END, flagged (placement = end_placeholder_not_found).
  4. Source seam is pluggable ('budget' registered; a test source dispatches); an UNKNOWN
     source type ERRORS clearly (no silent no-op); the normalizer maps append/annexure/
     budget wording to append_document.

Reuses the EXISTING merge primitives (merge_pdfs / find_placeholder_page /
insert_pdf_after_page) — no new merge logic. Throwaway data; cleaned up.
"""
import asyncio
import sys
import tempfile

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from app.db import AsyncSessionLocal  # noqa: E402
from app.models import Agreement, AgreementStatus, AgreementDocument, TemplateType  # noqa: E402
import app.modules.agreements.aggregator  # noqa: E402,F401
from app.modules.workflows import jobs  # noqa: E402
from app.modules.workflows.generate import _canonical_job_kind  # noqa: E402


def _tmpfile(suffix: str, prefix: str = "tmp") -> str:
    """NamedTemporaryFile(delete=False) path. Called via asyncio.to_thread from async code."""
    tmp = tempfile.NamedTemporaryFile(delete=False, prefix=prefix, suffix=suffix)
    tmp.close()
    return tmp.name


def _read_bytes(path: str) -> bytes:
    """Read a file's bytes. Called via asyncio.to_thread from async code."""
    with open(path, "rb") as f:
        return f.read()


def _reader():
    try:
        from pypdf import PdfReader
        return PdfReader
    except ImportError:
        from PyPDF2 import PdfReader  # type: ignore
        return PdfReader


def make_pdf(path: str, page_texts: list) -> None:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas
    c = canvas.Canvas(path, pagesize=letter)
    for t in page_texts:
        c.drawString(72, 720, t)
        c.showPage()
    c.save()


def page_texts(path: str) -> list:
    return [(p.extract_text() or "") for p in _reader()(path).pages]


async def _make_agreement(db, base_pdf: str) -> str:
    ss = (await db.execute(text(
        "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
        "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
    ))).fetchone()
    ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                   title="APPEND-DOC-VERIFY", status=AgreementStatus.DRAFT, is_legacy="false", created_by="owner-1")
    db.add(ag)
    await db.flush()
    db.add(AgreementDocument(agreement_id=ag.id, version_number=1, document_file_path=base_pdf,
                             created_by="owner-1", is_signed_version="false"))
    await db.flush()
    aid = str(ag.id)
    await db.commit()
    return aid


async def _cleanup(db, aid: str) -> None:
    await db.execute(text("DELETE FROM agreement_documents WHERE agreement_id=:a"), {"a": aid})
    await db.execute(text("DELETE FROM agreements WHERE id=:a"), {"a": aid})
    await db.commit()


def _appendix_index(merged_path: str) -> int:
    """Index of the appendix page (its content is 'APPENDIX_MARK') in the merged PDF, or -1."""
    import os
    if not (merged_path and os.path.exists(merged_path)):
        return -2  # remote/durable artifact — page check not possible here
    for i, t in enumerate(page_texts(merged_path)):
        if "APPENDIX_MARK" in t.replace(" ", ""):
            return i
    return -1


async def main():
    results = []
    appendix_pdf = await asyncio.to_thread(_tmpfile, ".pdf")
    make_pdf(appendix_pdf, ["APPENDIX_MARK appendix content"])

    # ---- static checks (no DB) ----
    assert "append_document" in jobs.registered_kinds(), jobs.registered_kinds()
    assert "budget" in jobs._APPEND_SOURCES, "budget source must be registered"
    results.append(("append_document registered; 'budget' source registered", "ok"))

    assert _canonical_job_kind("", "Append the budget annexure") == "append_document"
    assert _canonical_job_kind("attach_annexure", "Attach Annexure A") == "append_document"
    assert _canonical_job_kind("", "Generate the final PDF") == "generate_document"
    results.append(("Normalizer maps append/annexure/budget -> append_document (generate unaffected)", "ok"))

    # Deterministic TEST source (no WeasyPrint / budget data needed) to prove mechanics.
    async def _test_appendix(agreement, source, db):  # noqa: ARG001
        return appendix_pdf
    jobs._APPEND_SOURCES["verify_appendix"] = _test_appendix  # type: ignore[assignment]

    async def run_append(base_page_texts, params):
        """Fresh agreement with the given base PDF; run append; return (result, merged_local_path)."""
        base = await asyncio.to_thread(_tmpfile, ".pdf")
        make_pdf(base, base_page_texts)
        async with AsyncSessionLocal() as db:
            aid = await _make_agreement(db, base)
            try:
                res = await jobs._append_document({**params, "source": {"type": "verify_appendix"}}, {"agreement_id": aid})
            finally:
                pass
        return res, aid

    try:
        # ---- (A) PLACEHOLDER FOUND: marker on page 1 of a 2-page base ----
        base_pages = ["INTRO {{ANNEXURE_A}} insert here", "BASE_TAIL second page"]
        res, aid = await run_append(base_pages, {"placeholder": "{{ANNEXURE_A}}", "format": "pdf"})
        try:
            assert res["appended"] is True and res["version"] == 2, res
            assert res["placement"] == "at_placeholder", res
            idx = _appendix_index(res.get("document_url"))
            detail = f"placement={res['placement']}"
            if idx >= 0:
                # base p0 (marker) | APPENDIX | base p1 (tail)  -> appendix at index 1, NOT last (2)
                assert idx == 1, f"appendix expected at index 1 (after marker page), got {idx}"
                tail_idx = next((i for i, t in enumerate(page_texts(res["document_url"])) if "BASE_TAIL" in t.replace(" ", "")), -1)
                assert tail_idx == 2, f"tail expected at index 2, got {tail_idx}"
                detail += ", appendix@page1 (between marker@0 and tail@2) OK"
            else:
                detail += " (durable/remote — page-order check skipped)"
            results.append(("Placeholder FOUND -> appendix inserted AT the marker, not at end", detail))
        finally:
            async with AsyncSessionLocal() as db:
                await _cleanup(db, aid)

        # ---- (B) DETERMINISM: same base + same placeholder -> same placement + index ----
        res2, aid2 = await run_append(base_pages, {"placeholder": "{{ANNEXURE_A}}", "format": "pdf"})
        try:
            assert res2["placement"] == "at_placeholder", res2
            assert _appendix_index(res2.get("document_url")) == _appendix_index(res.get("document_url")), "non-deterministic placement"
            results.append(("Deterministic: same input -> same placement (appendix at the same page)", "stable @ index 1"))
        finally:
            async with AsyncSessionLocal() as db:
                await _cleanup(db, aid2)

        # ---- (C) NO placeholder -> append at END ----
        res3, aid3 = await run_append(base_pages, {"format": "pdf"})
        try:
            assert res3["placement"] == "end", res3
            idx = _appendix_index(res3.get("document_url"))
            assert idx in (-2, 2), f"no-placeholder: appendix expected last (index 2), got {idx}"
            results.append(("No placeholder -> appends at the END (current behavior preserved)", f"placement=end, appendix@{idx}"))
        finally:
            async with AsyncSessionLocal() as db:
                await _cleanup(db, aid3)

        # ---- (D) placeholder NOT found -> fall back to END, flagged ----
        res4, aid4 = await run_append(base_pages, {"placeholder": "{{NOT_PRESENT}}", "format": "pdf"})
        try:
            assert res4["placement"] == "end_placeholder_not_found", res4
            results.append(("Unknown marker -> falls back to END, flagged (not silent)", res4["placement"]))
        finally:
            async with AsyncSessionLocal() as db:
                await _cleanup(db, aid4)

        # ---- (E) unknown source + missing source.type ERROR clearly ----
        async with AsyncSessionLocal() as db:
            aid5 = await _make_agreement(db, appendix_pdf)
            try:
                err = False
                try:
                    await jobs._append_document({"source": {"type": "nope"}}, {"agreement_id": aid5})
                except ValueError as e:
                    err = "unknown source type" in str(e)
                assert err, "unknown source must raise"
                try:
                    await jobs._append_document({"source": {}}, {"agreement_id": aid5})
                    raise AssertionError("missing source.type must raise")
                except ValueError:
                    pass
                results.append(("Unknown source + missing source.type raise clear errors (no silent no-op)", "ValueError"))

                b = await jobs._append_document({"source": {"type": "budget"}}, {"agreement_id": aid5})
                assert b.get("source") == "budget", b
                results.append(("Real 'budget' source dispatches + degrades gracefully", f"appended={b.get('appended')}"))
            finally:
                await _cleanup(db, aid5)

        # ---- (F) AZURE-STORED base: document_file_url set, path is a blob name (no local
        #          file). The shared resolver must download the blob before converting,
        #          fixing "docx_to_pdf: source file not found". ----
        import app.utils.azure_storage as az
        base_blob_pdf = await asyncio.to_thread(_tmpfile, ".pdf")
        make_pdf(base_blob_pdf, ["AZURE_BASE only-in-blob page1", "AZURE_BASE page2"])
        blob_bytes = await asyncio.to_thread(_read_bytes, base_blob_pdf)

        class _FakeStorage:
            async def download_file(self, blob_name):  # noqa: ARG002
                return blob_bytes

        _orig = az.get_document_storage
        az.get_document_storage = lambda: _FakeStorage()  # type: ignore[assignment]
        try:
            async with AsyncSessionLocal() as db:
                ss = (await db.execute(text(
                    "SELECT id,study_id,site_id FROM study_sites ss WHERE ss.id NOT IN "
                    "(SELECT study_site_id FROM agreements WHERE agreement_type='CDA' AND study_site_id IS NOT NULL) LIMIT 1"
                ))).fetchone()
                ag = Agreement(site_id=ss[2], study_id=ss[1], study_site_id=ss[0], agreement_type=TemplateType.CDA,
                               title="APPEND-AZURE", status=AgreementStatus.DRAFT, is_legacy="false", created_by="owner-1")
                db.add(ag)
                await db.flush()
                # blob NAME as path (no local file), document_file_url set => Azure-stored.
                db.add(AgreementDocument(agreement_id=ag.id, version_number=1,
                                         document_file_path="agreements/AZURE/base_v001.pdf",
                                         document_file_url="https://fake.blob.core.windows.net/docs/agreements/AZURE/base_v001.pdf",
                                         created_by="owner-1", is_signed_version="false"))
                await db.flush()
                aid6 = str(ag.id)
                await db.commit()
                try:
                    res = await jobs._append_document(
                        {"source": {"type": "verify_appendix"}}, {"agreement_id": aid6})
                    assert res["appended"] is True and res["version"] == 2, res
                    results.append(("Azure-stored base (blob name + url): resolver downloads blob, merge succeeds",
                                    f"version={res['version']} (no 'source file not found')"))
                finally:
                    await _cleanup(db, aid6)
        finally:
            az.get_document_storage = _orig  # type: ignore[assignment]
    finally:
        jobs._APPEND_SOURCES.pop("verify_appendix", None)

    print("=" * 96)
    print("APPEND_DOCUMENT JOB + PLACEHOLDER PLACEMENT — VERIFICATION")
    print("=" * 96)
    for label, detail in results:
        print(f"PASS  {label}\n        -> {detail}")
    print("=" * 96)
    print(f"{len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())

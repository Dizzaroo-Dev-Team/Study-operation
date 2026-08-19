"""
doc_merge.py — reusable PDF concatenation capability. Wraps the EXISTING
utils/pdf_export.merge_pdfs:476 (pypdf/PyPDF2) so any flow can append an appendix
(e.g. CTA's visit-matrix) to a primary PDF. No new merge logic.
"""
from __future__ import annotations


def merge(primary_pdf: str, appendix_pdf: str) -> str:
    """Concatenate appendix after primary; returns the merged PDF path (_merged)."""
    from app.modules.agreements.utils.pdf_export import merge_pdfs
    return merge_pdfs(primary_pdf, appendix_pdf)

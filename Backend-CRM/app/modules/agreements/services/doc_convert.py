"""
doc_convert.py — reusable document-bytes resolution + DOCX->PDF capability. Extracts the
conversion seam so any flow can produce the final PDF artifact, AND centralises the
Azure-vs-local resolution so every converter/merger reads REAL local bytes.

Wraps the EXISTING converter (utils/pdf_export.docx_to_pdf — OnlyOffice ConvertService
-> LibreOffice headless fallback); no new conversion logic.

Why resolve_local_path matters: when Azure Blob Storage is configured, an
AgreementDocument's `document_file_path` is the BLOB NAME (not a local file) and
`document_file_url` is set. Anything that treats the path as a local file then fails with
"docx_to_pdf: source file not found". resolve_local_path downloads the blob to a temp
file first — the SAME logic unified signing uses — so a stored doc converts everywhere.
"""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _make_named_tempfile(suffix: str, data: Optional[bytes] = None):
    """Create a NamedTemporaryFile(delete=False) with ``suffix``, optionally
    write ``data`` into it, and return the (closed) tempfile object — callers
    rely on its full-path ``.name``. Sync on purpose — call via
    ``asyncio.to_thread`` from async code so the blocking file I/O stays off
    the event loop."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        if data is not None:
            tmp.write(data)
    finally:
        tmp.close()
    return tmp


async def resolve_local_path(file_path: str, file_url: Optional[str] = None) -> Optional[str]:
    """Return a LOCAL filesystem path to the document bytes.

    Documents may live in Azure (``file_url`` set, ``file_path`` = blob name) OR on local
    disk (Azure off in dev). When Azure-keyed and storage is configured, download the blob
    to a temp file and return its path; otherwise use the local path. Returns None when the
    bytes can't be obtained (caller raises a clear error). Mirrors the proven
    unified_signing resolution so EVERY flow handles Azure-stored docs identically."""
    if file_url:
        from app.utils.azure_storage import get_document_storage
        storage = get_document_storage()
        if storage and file_path:
            try:
                blob = await storage.download_file(file_path)
            except Exception:  # noqa: BLE001 — fall through to the local check, then None
                logger.exception("doc_convert.resolve_local_path: Azure download failed for %s", file_path)
                blob = None
            if blob:
                tmp = await asyncio.to_thread(
                    _make_named_tempfile, (Path(file_path).suffix or ".docx"), blob)
                return tmp.name
        # Azure-keyed but storage is OFF this run -> blob unreachable; the local check
        # below will fail and the caller gets a clear "bytes unavailable" error.
    if file_path and Path(file_path).exists():
        return file_path
    return None


async def to_pdf(path: str, file_url: Optional[str] = None) -> str:
    """Return a PDF path for `path`. Already-PDF -> returned as-is; DOCX -> converted via
    the existing docx_to_pdf. When `file_url` is given (Azure-stored), the bytes are
    downloaded to a local temp file FIRST (so conversion never 'source file not found's on
    a blob name). Raises whatever the converter raises (caller maps to an HTTP error)."""
    if file_url:
        resolved = await resolve_local_path(path, file_url)
        if not resolved:
            raise FileNotFoundError(
                f"to_pdf: document bytes unavailable (path={path}, azure_url set) — "
                f"is Azure Blob Storage configured/reachable?")
        path = resolved
    if path.lower().endswith(".pdf"):
        return path
    from app.modules.agreements.utils.pdf_export import docx_to_pdf
    return await docx_to_pdf(path)

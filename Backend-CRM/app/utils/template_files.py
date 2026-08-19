"""
Template file retrieval utility – Azure Blob Storage with local fallback.
"""
import asyncio
import os
import tempfile
from pathlib import Path
from typing import Optional

from app.config import settings
from app.utils.azure_storage import get_template_storage

import logging

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


async def get_template_file_path(
    template_file_path: str,
    template_file_url: Optional[str] = None,
) -> str:
    """
    Resolve a template to a local file path for reading / serving.

    If the template is stored in Azure (template_file_url is set), it is
    downloaded to a temp file.  Otherwise the local path is returned.

    Returns:
        Local file path (caller must clean up temp files).
    Raises:
        FileNotFoundError when the template cannot be located.
    """
    if not template_file_path:
        raise ValueError("Template file path is required")

    if template_file_url:
        storage = get_template_storage()
        if storage:
            try:
                blob_name = template_file_path
                content = await storage.download_file(blob_name)
                if content:
                    tmp = await asyncio.to_thread(_make_named_tempfile, ".docx", content)
                    logger.info("Downloaded template from Azure: %s", blob_name)
                    return tmp.name
            except Exception as e:
                logger.exception("Failed to download template from Azure: %s", e)

    local = Path(template_file_path)
    if local.exists():
        return str(local)

    upload_dir_path = Path(settings.upload_dir) / template_file_path
    if upload_dir_path.exists():
        return str(upload_dir_path)

    raise FileNotFoundError(f"Template file not found: {template_file_path}")


def is_azure_template(template_file_url: Optional[str]) -> bool:
    return bool(template_file_url and template_file_url.startswith("https://"))


async def cleanup_temp_file(file_path: str):
    try:
        if file_path and Path(file_path).exists():
            os.unlink(file_path)
    except Exception:
        pass

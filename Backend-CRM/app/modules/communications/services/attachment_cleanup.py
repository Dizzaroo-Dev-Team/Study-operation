"""Orphan attachment-file reconciler (Batch-4 ATT-ORPHAN-BLOBS).

There is no delete endpoint for conversations/threads/messages, and uploaded
files on local disk are never removed today — so `upload_dir` accrues orphans.
We deliberately do NOT invent deletion endpoints. Instead this is a safe,
idempotent sweep that finds files in `settings.upload_dir` which no attachment
row references and, only when explicitly allowed, deletes them.

Safety contract:
  * ``dry_run=True`` (the default) → list only, never delete. Deletion happens
    ONLY on an explicit ``dry_run=False`` invocation; nothing auto-deletes —
    there is no scheduled/automatic caller, so files are only removed when an
    operator deliberately runs the reconciler with ``dry_run=False``.
  * Files are deleted with ``missing_ok=True`` so an already-gone file never
    crashes the sweep.
"""
from pathlib import Path
from typing import Dict, Set
import logging

from app.config import settings
from app.db.mongo import get_mongo_db

logger = logging.getLogger(__name__)


async def _referenced_filenames() -> Set[str]:
    """Basenames of every file referenced by an attachment row in Mongo.

    Conversation and thread attachments both resolve to the `attachments`
    collection (thread attachments link to an attachment via attachment_id),
    and that row carries the on-disk `file_path`. So the set of referenced
    basenames is exactly the `file_path` basenames in `attachments`.
    """
    db = await get_mongo_db()
    referenced: Set[str] = set()
    cursor = db["attachments"].find({}, {"file_path": 1})
    async for doc in cursor:
        fp = doc.get("file_path")
        if fp:
            referenced.add(Path(str(fp)).name)
    return referenced


async def reconcile_orphan_attachment_files(dry_run: bool = True) -> Dict:
    """Find (and, when allowed, delete) files in upload_dir with no referencing row.

    Returns a report dict:
      upload_dir, scanned, referenced, orphans[], would_delete[], deleted[],
      dry_run, cleanup_enabled.
    """
    upload_dir = Path(settings.upload_dir)
    report: Dict = {
        "upload_dir": str(upload_dir),
        "scanned": 0,
        "referenced": 0,
        "orphans": [],
        "would_delete": [],
        "deleted": [],
        "dry_run": dry_run,
    }
    if not upload_dir.exists():
        return report

    referenced = await _referenced_filenames()
    report["referenced"] = len(referenced)

    files = [p for p in upload_dir.iterdir() if p.is_file()]
    report["scanned"] = len(files)
    orphans = [p for p in files if p.name not in referenced]
    report["orphans"] = [p.name for p in orphans]

    # Actual deletion only when explicitly requested (not dry-run). Otherwise
    # just report what WOULD be deleted.
    if dry_run:
        report["would_delete"] = [p.name for p in orphans]
        return report

    for p in orphans:
        try:
            p.unlink(missing_ok=True)  # tolerate an already-missing file
            report["deleted"].append(p.name)
        except OSError as e:
            logger.warning(
                "reconcile_orphan_attachment_files: could not delete %s: %s", p, e
            )
    return report

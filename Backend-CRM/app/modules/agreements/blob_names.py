"""Azure/local blob path helpers for agreement documents (no route imports)."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional


def _sanitize_blob_part(value: str) -> str:
    value = re.sub(r'[<>:"/\\|?*]', "_", value or "")
    value = re.sub(r"\s+", "_", value)
    return value.strip("_") or "unknown"


def _extract_blob_seq(path_or_name: Optional[str]) -> int:
    if not path_or_name:
        return 0
    m = re.search(r"_v(\d{3})_", path_or_name)
    return int(m.group(1)) if m else 0


def _build_pretty_document_blob_name(
    study_name: str,
    site_name: str,
    agreement_title: str,
    seq: int,
    when_utc: Optional[datetime] = None,
) -> str:
    """
    agreements/{study}_{site}_{title}/{study}_{site}_{title}_v001_2026-03-24_09-56.docx
    """
    safe_study = _sanitize_blob_part(study_name)
    safe_site = _sanitize_blob_part(site_name)
    safe_title = _sanitize_blob_part(agreement_title)
    prefix = f"{safe_study}_{safe_site}_{safe_title}"
    ts = (when_utc or datetime.now(timezone.utc)).strftime("%Y-%m-%d_%H-%M")
    return f"agreements/{prefix}/{prefix}_v{seq:03d}_{ts}.docx"


def _build_review_working_blob_name(
    study_name: str,
    site_name: str,
    agreement_title: str,
    review_document_id,
    seq: int,
    when_utc: Optional[datetime] = None,
) -> str:
    """New blob per review save — same naming style as main agreement files."""
    safe_study = _sanitize_blob_part(study_name)
    safe_site = _sanitize_blob_part(site_name)
    safe_title = _sanitize_blob_part(agreement_title)
    prefix = f"{safe_study}_{safe_site}_{safe_title}"
    ts = (when_utc or datetime.now(timezone.utc)).strftime("%Y-%m-%d_%H-%M")
    rid = str(review_document_id).replace("-", "")[:8]
    return f"agreement_reviews/{prefix}/{prefix}_rev_{rid}_v{seq:03d}_{ts}.docx"

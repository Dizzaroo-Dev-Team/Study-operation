"""Feature-doc loader for the assistant's help answers.

Inlines the small set of ``docs/features/*.md`` into the agent context so
"how do I…" questions are answered from the docs — no pgvector / embedding
pipeline (the corpus is tiny). Docs are cached after first read.

Path resolution (first existing wins):
  1. ``ASSISTANT_DOCS_DIR`` setting/env (Docker sets it to the mounted repo docs).
  2. repo-root ``docs/features`` relative to this file (host runs).
  3. ``/repo-docs/features`` (the Docker mount, as a fallback).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Guard against a runaway corpus blowing the model context / cost.
_MAX_TOTAL_CHARS = 24000

_cache: Optional[str] = None


def _candidate_dirs() -> List[Path]:
    from app.config import settings

    candidates: List[Path] = []
    if settings.assistant_docs_dir:
        candidates.append(Path(settings.assistant_docs_dir))
    here = Path(__file__).resolve()
    # .../Backend-CRM/app/modules/assistant/docs.py -> parents[4] == repo root
    for up in (4, 5):
        if up < len(here.parents):
            candidates.append(here.parents[up] / "docs" / "features")
    candidates.append(Path("/repo-docs/features"))
    return candidates


def _load() -> str:
    for directory in _candidate_dirs():
        try:
            if not directory.is_dir():
                continue
            md_files = sorted(directory.glob("*.md"))
            if not md_files:
                continue
            chunks: List[str] = []
            total = 0
            for path in md_files:
                if path.name.lower() == "readme.md":
                    continue
                text = path.read_text(encoding="utf-8", errors="ignore").strip()
                if not text:
                    continue
                block = f"===== FEATURE DOC: {path.stem} =====\n{text}"
                if total + len(block) > _MAX_TOTAL_CHARS:
                    block = block[: max(0, _MAX_TOTAL_CHARS - total)]
                chunks.append(block)
                total += len(block)
                if total >= _MAX_TOTAL_CHARS:
                    break
            if chunks:
                logger.info("assistant: loaded %d feature doc(s) from %s", len(chunks), directory)
                return "\n\n".join(chunks)
        except Exception:  # noqa: BLE001
            logger.exception("assistant: failed reading docs from %s", directory)
    logger.warning("assistant: no feature docs found in any candidate directory")
    return ""


def get_feature_docs() -> str:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache

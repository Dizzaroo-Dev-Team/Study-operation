"""
Loads the SDTM schema metadata text once and exposes:
  - SDTM_SCHEMA_TEXT  — the full ~190 KB metadata document used as Gemini context
  - ALLOWED_TABLES    — lowercase domain names extracted from the doc, used by
                         sql_guard to reject any reference to a table outside SDTM

Resolution order for the metadata file:
  1. STUDY_DB_01_SCHEMA_PATH env var (absolute or repo-relative)
  2. <repo_root>/metadata_schema_db_01.txt   (assuming this file lives at
     Backend-CRM/app/modules/study_dashboard/ai_assistant/sdtm_schema.py the
     repo root is parents[5])
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Set


_SCHEMA_FILENAME = "metadata_schema_db_01.txt"


def _candidate_paths() -> list[Path]:
    paths: list[Path] = []
    env_override = os.getenv("STUDY_DB_01_SCHEMA_PATH")
    if env_override:
        paths.append(Path(env_override).expanduser())
    here = Path(__file__).resolve()
    # repo root candidates (try a few levels in case layout changes)
    for ancestor in here.parents[3:7]:
        paths.append(ancestor / _SCHEMA_FILENAME)
    return paths


@lru_cache(maxsize=1)
def _load_schema() -> tuple[str, frozenset[str]]:
    last_err: Exception | None = None
    for candidate in _candidate_paths():
        try:
            text = candidate.read_text(encoding="utf-8")
            tables = _extract_table_names(text)
            return text, frozenset(tables)
        except FileNotFoundError as exc:
            last_err = exc
            continue
    raise FileNotFoundError(
        f"Could not locate {_SCHEMA_FILENAME}. Tried: "
        + ", ".join(str(p) for p in _candidate_paths())
    ) from last_err


def _extract_table_names(text: str) -> Set[str]:
    # "Table Name: AE" — capture the identifier and lowercase it
    return {m.group(1).lower() for m in re.finditer(r"^Table Name:\s*([A-Za-z0-9_]+)", text, flags=re.MULTILINE)}


def get_schema_text() -> str:
    """Lazy-loads the metadata file. Raises FileNotFoundError only when called."""
    return _load_schema()[0]


def get_allowed_tables() -> frozenset[str]:
    """Lazy-loads the metadata file. Raises FileNotFoundError only when called."""
    return _load_schema()[1]

# NOTE: there are no module-level constants here on purpose. Eager-loading the
# metadata at import time silently broke the whole study-dashboard router (the
# registration in main.py wraps the import in try/except). Always call the
# helpers above instead.

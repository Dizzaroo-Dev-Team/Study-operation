"""IRB catalog rules: all IRBs are allowed in pickers."""
from __future__ import annotations

from typing import Optional


def normalize_irb_list_name(name: Optional[str]) -> str:
    if not name:
        return ""
    return " ".join(str(name).strip().lower().split())


def is_irb_excluded_from_catalog(name: Optional[str], unique_code: Optional[str] = None) -> bool:
    """No IRBs are excluded from dropdowns or mapping."""
    return False

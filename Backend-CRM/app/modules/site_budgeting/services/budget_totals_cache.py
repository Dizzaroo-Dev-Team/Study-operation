"""Process-local cache for computed budget totals (invalidated on mutating writes)."""
from __future__ import annotations

import threading
from typing import Any, Optional
from uuid import UUID


_lock = threading.Lock()
_store: dict[str, dict[str, Any]] = {}


def totals_key(template_id: UUID, country_code: Optional[str], site_id: Optional[UUID]) -> str:
    return "|".join(
        (
            str(template_id),
            (country_code or "").upper().strip(),
            str(site_id) if site_id is not None else "",
        )
    )


def get_totals(cache_key: str) -> Optional[dict[str, Any]]:
    with _lock:
        hit = _store.get(cache_key)
        return hit.copy() if hit is not None else None


def set_totals(cache_key: str, payload: dict[str, Any]) -> None:
    with _lock:
        _store[cache_key] = payload.copy()


def clear_all() -> None:
    with _lock:
        _store.clear()

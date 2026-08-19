"""
waits.py
========

The WAIT-CONDITION seam: pluggable predicates a `wait_condition` step holds on until
they become true. Mirrors jobs.py's handler registry and the append_document source
seam — register a checker here and any workflow can ``wait_condition`` on it.

A checker is ``async def checker(agreement, params: dict, db) -> bool``:
  * ``agreement`` is the workflow subject (an Agreement, or None for non-agreement
    subjects); the checker queries whatever real state it needs.
  * returns True  -> the condition is satisfied; the engine releases the held step
                     (fires its ``condition_met`` transition) on the next sweep.
  * returns False -> the workflow stays PARKED at the step; re-checked next sweep.

The mechanism is GENERIC: "budget_ready" is one condition; "document_uploaded",
"date_reached", "external_approval", etc. register here with no engine changes.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)

# (agreement, params, db) -> bool
WaitChecker = Callable[[Any, dict, Any], Awaitable[bool]]

_WAIT_CONDITIONS: dict[str, WaitChecker] = {}


def register_condition(name: str, checker: WaitChecker) -> None:
    _WAIT_CONDITIONS[name] = checker


def get_condition_checker(name: str) -> Optional[WaitChecker]:
    return _WAIT_CONDITIONS.get(name)


def registered_conditions() -> set[str]:
    """The condition names with a live checker — the generator/validator use this to
    emit/accept only conditions that can ACTUALLY be evaluated."""
    return set(_WAIT_CONDITIONS)


# ---------------------------------------------------------------------------
# Built-in conditions
# ---------------------------------------------------------------------------
async def _budget_ready(agreement, params: dict, db) -> bool:  # noqa: ARG001 — params reserved
    """True when the site's budget has actual, renderable visit-matrix DATA — i.e. the
    budget is filled in and the append will attach real content.

    "Ready" means data-present, NOT a formal approval status: it reuses the SAME
    cascade-aware loader the append uses (_load_visit_matrix_data — site → country →
    trial), so an empty site template that inherits a populated trial-level budget still
    counts as ready, AND "the wait released" guarantees "the append will attach the
    budget" (the two can't disagree). Returns False (keep waiting) when there is no
    agreement/study or no renderable budget rows yet."""
    if agreement is None:
        return False
    study_id = getattr(agreement, "study_id", None)
    site_id = getattr(agreement, "site_id", None)
    if not study_id:
        return False

    from app.modules.agreements.utils.pdf_export import _load_visit_matrix_data

    try:
        matrix = await _load_visit_matrix_data(study_id, site_id, db)
    except Exception:  # noqa: BLE001 — a load error must not crash the sweep; keep waiting
        logger.exception("waits._budget_ready: matrix load failed (study=%s site=%s)", study_id, site_id)
        return False
    ready = bool(matrix.get("rows"))
    logger.debug("waits._budget_ready: study=%s site=%s rows=%s -> %s",
                 study_id, site_id, len(matrix.get("rows") or []), ready)
    return ready


register_condition("budget_ready", _budget_ready)

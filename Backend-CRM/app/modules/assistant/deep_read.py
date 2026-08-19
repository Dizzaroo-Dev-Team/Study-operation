"""Deep-read — fetch a screen's UNDERLYING data from the app's REAL routes, only on
the user's EXPLICIT request ('give me the full data', 'pull the full dataset', 'all
N pages/rows').

Contrast with the on-screen reader (agent._read_current_screen), which sees only the
rendered/visible content. Deep-read calls the real backend route in-process (as the
user) and returns exactly what that route allows.

DELIBERATELY NO Orbit-side entitlement gate: deep-read inherits whatever the route
itself enforces. Today the clinical/SDTM study-dashboard routes enforce nothing, so
deep-read returns everything — a documented, product-owner-approved deferral,
acceptable in dev/test with non-real data only. When a route-layer study guard is
later added, deep-read is AUTOMATICALLY scoped and a non-entitled deep-read is refused
with the route's own denial — no change needed here. See
docs/agent-assistant/known-gaps.md.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.modules.assistant.invoker import invoke_get

logger = logging.getLogger(__name__)

# The study dashboard's real underlying data endpoints (operational aggregates).
_DASHBOARD_ENDPOINTS = {
    "enrollment": "/api/study-dashboard/enrollment",
    "milestones": "/api/study-dashboard/milestones",
    "disposition": "/api/study-dashboard/disposition",
    "deviations": "/api/study-dashboard/deviations",
    "visit_compliance": "/api/study-dashboard/visit-compliance",
    "ae_kpis": "/api/study-dashboard/ae-summary",
}


async def _deep_dashboard(context: Optional[dict], bearer: Optional[str]) -> Dict[str, Any]:
    study_id = (context or {}).get("study_id")
    if not study_id:
        return {"available": True, "screen": "dashboard", "study_selected": False,
                "note": "No study is selected — ask the user to pick a study to pull its data."}
    # NO entitlement check here on purpose — the route governs access (deferred).
    data: Dict[str, Any] = {}
    for key, path in _DASHBOARD_ENDPOINTS.items():
        r = await invoke_get(path, params={"study_id": study_id}, bearer_token=bearer)
        if not r.ok:
            # If/when the route adds a guard, a non-entitled call lands here (e.g. 403)
            # and we surface that denial honestly rather than inventing data.
            data[key] = {"unavailable": True, "status": r.status_code}
            continue
        payload = r.data if isinstance(r.data, dict) else {}
        data[key] = payload.get("kpis", payload) if key == "ae_kpis" else payload
    denied = [k for k, v in data.items() if isinstance(v, dict) and v.get("status") in (401, 403)]
    return {"available": True, "screen": "dashboard", "study_selected": True,
            "study_id": study_id, "route_governed": True, "denied_endpoints": denied, "data": data}


DEEP_READERS = {
    "dashboard": _deep_dashboard,
    "study-dashboard": _deep_dashboard,
    "study_dashboard": _deep_dashboard,
}


async def deep_read(mode: Optional[str], context: Optional[dict], bearer: Optional[str]) -> Dict[str, Any]:
    """Fetch the underlying data for the current screen via its real route(s).
    Unknown screen → available: False so the agent declines honestly."""
    reader = DEEP_READERS.get((mode or "").strip().lower())
    if reader is None:
        return {"available": False, "screen": mode or "unknown", "reason": "no_route",
                "note": "There is no backend data route wired for a deep-read of this screen."}
    try:
        return await reader(context, bearer)
    except Exception:  # noqa: BLE001 — never break the turn
        logger.exception("deep_read failed for mode=%s", mode)
        return {"available": False, "screen": mode, "reason": "error"}

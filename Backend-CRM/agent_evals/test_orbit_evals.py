"""Orbit live agent evals — runs the REAL Orbit agent against the goldens.

Requires the backend runtime (app importable, dev Postgres/Mongo/Redis,
GEMINI_API_KEY). Canonical invocation:

    docker exec -e PYTHONPATH=/app -e DEEPEVAL_TELEMETRY_OPT_OUT=YES \
        backend-crm-backend-1 deepeval test run agent_evals/test_orbit_evals.py

All agent turns run sequentially inside ONE event loop (module cache) before
any assertion: the session hub / confirmation store / async DB engine are
process singletons whose Redis clients and pools bind to the loop that first
uses them — one loop for everything avoids cross-loop breakage.

Set EVAL_SKIP_JUDGE=1 to run the deterministic layer only (no Gemini judge).
Set EVAL_ONLY=<id>[,<id>...] to run a subset of goldens (cheap single-case reruns).
"""
from __future__ import annotations

import asyncio
import os

import pytest
from deepeval import assert_test

from agent_evals.core.goldens import load_suite
from agent_evals.core.runner import build_test_case, metrics_for

_GOLDENS = os.path.join(os.path.dirname(__file__), "goldens", "orbit.yaml")
SUITE = load_suite(_GOLDENS)
_USE_JUDGE = os.environ.get("EVAL_SKIP_JUDGE") != "1"
_ONLY = {s for s in os.environ.get("EVAL_ONLY", "").split(",") if s}
CASES = [c for c in SUITE.cases if not _ONLY or c.id in _ONLY]

_results: dict = {}
_run_errors: dict = {}


def _run_all_once() -> None:
    """Execute every golden's turn once, in one event loop, caching results."""
    if _results or _run_errors:
        return

    async def _go():
        from agent_evals.connectors import orbit

        for case in CASES:
            try:
                _results[case.id] = await orbit.run(case.input)
            except Exception as exc:  # noqa: BLE001 — surface per-case, don't halt suite
                _run_errors[case.id] = repr(exc)

    asyncio.run(_go())


@pytest.mark.parametrize("case", CASES, ids=[c.id for c in CASES])
def test_orbit_golden(case):
    _run_all_once()
    if case.id in _run_errors:
        pytest.fail(f"connector run failed for '{case.id}': {_run_errors[case.id]}")
    result = _results[case.id]
    test_case = build_test_case(case, result)
    assert_test(test_case, metrics_for(case, use_judge=_USE_JUDGE), run_async=False)

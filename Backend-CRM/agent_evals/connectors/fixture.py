"""FIXTURE connector — replays a canned answer + trace. NOT a real agent.

Used for (a) the toolkit's own CI self-tests (no DB, no LLM, no network) and
(b) demonstrating the connector contract. Every result it produces is clearly
labeled as fixture data in ``trace.raw.source``.

Golden input shape::

    input:
      fixture:
        answer: "..."
        trace: { actions: [...], audit: [...], flags: {...} }
"""
from __future__ import annotations

from typing import Any, Dict

from agent_evals.core.connector import RunResult


async def run(input: Dict[str, Any]) -> RunResult:
    fx = (input or {}).get("fixture") or {}
    trace = dict(fx.get("trace") or {})
    raw = dict(trace.get("raw") or {})
    raw["source"] = "FIXTURE (replayed, not a live agent run)"
    trace["raw"] = raw
    return RunResult(answer=str(fx.get("answer") or ""), trace=trace)

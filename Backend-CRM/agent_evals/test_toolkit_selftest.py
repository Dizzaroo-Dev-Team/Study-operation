"""Toolkit self-tests — fixture connector, deterministic metrics only.

CI-safe: no database, no Redis, no Gemini, no live agent. Proves the generic
grading layer (checks / goldens loader / DeepEval integration) works before
any live eval is trusted.

Run:  deepeval test run agent_evals/test_toolkit_selftest.py
  or: pytest agent_evals/test_toolkit_selftest.py
"""
from __future__ import annotations

import asyncio
import os

import pytest
from deepeval import assert_test

from agent_evals.connectors import fixture
from agent_evals.core.checks import run_checks
from agent_evals.core.goldens import load_suite
from agent_evals.core.runner import build_test_case, metrics_for

_GOLDENS = os.path.join(os.path.dirname(__file__), "goldens", "fixture_selftest.yaml")
SUITE = load_suite(_GOLDENS)


@pytest.mark.parametrize("case", SUITE.cases, ids=[c.id for c in SUITE.cases])
def test_fixture_selftest(case):
    result = asyncio.run(fixture.run(case.input))
    test_case = build_test_case(case, result)
    # use_judge=False: self-tests stay deterministic (no LLM in CI).
    assert_test(test_case, metrics_for(case, use_judge=False), run_async=False)


def test_checks_fail_loud_on_unknown_type():
    results = run_checks([{"type": "no_such_check"}], "", {})
    assert len(results) == 1 and not results[0].passed


def test_checks_fail_on_missing_flag():
    results = run_checks([{"type": "flag_equals", "path": "a.b", "value": 1}], "", {"flags": {}})
    assert not results[0].passed


def test_goldens_loader_rejects_duplicate_ids(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "connector: fixture\ncases:\n"
        "  - {id: x, input: {}}\n  - {id: x, input: {}}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_suite(str(bad))

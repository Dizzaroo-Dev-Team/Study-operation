"""DeepEval metric wrappers.

Three layers, in order of trust:
  1. DeterministicChecksMetric — pure predicates over the normalized trace
     (the connector assembled it from ground truth: audit log / event stream).
     Threshold defaults to 1.0: every check must pass.
  2. Tool-use metric — DeepEval's built-in ToolCorrectnessMetric (deterministic
     string comparison of expected vs. actually-called tools).
  3. G-Eval on the Gemini judge — ONLY for fuzzy criteria a predicate can't
     express (tone-of-refusal honesty, grounding of a summary).
"""
from __future__ import annotations

from typing import List, Optional

from deepeval.metrics import BaseMetric, GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from agent_evals.core.checks import run_checks
from agent_evals.core.judge import GeminiJudge


class DeterministicChecksMetric(BaseMetric):
    """Grades the golden's ``checks:`` list against the trace. No LLM.

    The trace travels on ``test_case.additional_metadata['trace']`` (DeepEval's
    LLMTestCase has no first-class trace field).
    """

    def __init__(self, checks: List[dict], threshold: float = 1.0):
        self.checks = checks or []
        self.threshold = threshold
        self.async_mode = False
        self.strict_mode = False
        self.include_reason = True
        self.error: Optional[str] = None
        self.evaluation_cost = None
        self.score: Optional[float] = None
        self.reason: Optional[str] = None
        self.success: Optional[bool] = None

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        trace = (test_case.additional_metadata or {}).get("trace", {})
        results = run_checks(self.checks, test_case.actual_output or "", trace)
        if not results:
            self.score, self.reason = 1.0, "no deterministic checks declared"
        else:
            passed = [r for r in results if r.passed]
            failed = [r for r in results if not r.passed]
            self.score = len(passed) / len(results)
            if failed:
                self.reason = "FAILED: " + " | ".join(f"[{r.check}] {r.detail}" for r in failed)
            else:
                self.reason = f"all {len(results)} checks passed: " + "; ".join(
                    r.check for r in results
                )
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):  # noqa: A003 — DeepEval displays this
        return "Deterministic Trace Checks"


class ExpectedToolsMetric(BaseMetric):
    """Deterministic task-completion proxy: every expected tool must appear in
    the tools the agent actually called (extra calls are allowed — the checks
    layer constrains those). No LLM: DeepEval 4.x's ToolCorrectnessMetric
    became judge-backed, which we don't want for a right/wrong comparison."""

    def __init__(self, threshold: float = 1.0):
        self.threshold = threshold
        self.async_mode = False
        self.strict_mode = False
        self.include_reason = True
        self.error: Optional[str] = None
        self.evaluation_cost = None
        self.score: Optional[float] = None
        self.reason: Optional[str] = None
        self.success: Optional[bool] = None

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        expected = [t.name for t in (test_case.expected_tools or [])]
        called = [t.name for t in (test_case.tools_called or [])]
        if not expected:
            self.score, self.reason = 1.0, "no expected tools declared"
        else:
            hit = [t for t in expected if t in called]
            missing = [t for t in expected if t not in called]
            self.score = len(hit) / len(expected)
            self.reason = (
                f"expected={expected}, called={called}"
                + (f", MISSING={missing}" if missing else " — all present")
            )
        self.success = self.score >= self.threshold
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self):  # noqa: A003
        return "Expected Tools Called"


def build_tool_metric(threshold: float = 1.0) -> ExpectedToolsMetric:
    """Deterministic task-completion proxy: were the expected tools called?"""
    return ExpectedToolsMetric(threshold=threshold)


def build_judge_metric(judge_spec: dict, judge_model=None) -> GEval:
    """G-Eval with plain-English criteria on the Gemini judge (fuzzy cases only)."""
    return GEval(
        name=judge_spec.get("name", "LLM judge"),
        criteria=judge_spec["criteria"],
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=judge_model or GeminiJudge(),
        threshold=float(judge_spec.get("threshold", 0.7)),
        async_mode=False,
    )

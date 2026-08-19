"""Glue: golden + RunResult -> DeepEval LLMTestCase + metric bundle."""
from __future__ import annotations

import json
from typing import List, Optional

from deepeval.test_case import LLMTestCase, ToolCall

from agent_evals.core.connector import RunResult
from agent_evals.core.goldens import GoldenCase
from agent_evals.core.metrics import (
    DeterministicChecksMetric,
    build_judge_metric,
    build_tool_metric,
)


def build_test_case(golden: GoldenCase, result: RunResult) -> LLMTestCase:
    # The judge sees the whole input dict (message + any screen/form payloads)
    # so grounding criteria can reference what the agent was actually given.
    input_str = json.dumps(golden.input, ensure_ascii=False, default=str)
    tools_called = [
        ToolCall(name=a.get("name"))
        for a in (result.trace.get("actions") or [])
        if a.get("name") and a.get("executed", True)
    ]
    return LLMTestCase(
        name=golden.id,
        input=input_str,
        actual_output=result.answer or "",
        tools_called=tools_called or None,
        expected_tools=[ToolCall(name=t) for t in golden.expected_tools] or None,
        additional_metadata={"trace": result.trace, "golden_id": golden.id,
                             "review": golden.review},
    )


def metrics_for(golden: GoldenCase, judge_model=None, use_judge: bool = True) -> List:
    metrics: List = [DeterministicChecksMetric(golden.checks)]
    if golden.expected_tools:
        metrics.append(build_tool_metric())
    if golden.judge and use_judge:
        metrics.append(build_judge_metric(golden.judge, judge_model=judge_model))
    return metrics

"""Gemini judge model for DeepEval — local-first, no OpenAI, no cloud account.

A custom ``DeepEvalBaseLLM`` over the shared deepeval-free ``GeminiClient``
(see ``core.gemini_client``). When DeepEval passes a Pydantic schema (G-Eval
does), Gemini's native structured output enforces the verdict JSON.

This module imports deepeval and is therefore OFFLINE-ONLY. The live scorer
(``core.live``) uses ``GeminiClient`` directly so the production app never
needs deepeval installed.

CAVEAT (put a human in the loop): the judge model's quality is the ceiling of
any LLM-graded metric. Spot-check its verdicts early and often; prefer the
deterministic checks in ``checks.py`` wherever a right/wrong answer exists.
"""
from __future__ import annotations

from typing import Optional

from deepeval.models.base_model import DeepEvalBaseLLM

from agent_evals.core.gemini_client import GeminiClient

DEFAULT_JUDGE_MODEL = "gemini-3.5-flash"


class GeminiJudge(DeepEvalBaseLLM):
    """LLM-judge on Gemini via the google-genai SDK (sync + async)."""

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        self._client = GeminiClient(model_name=model_name or DEFAULT_JUDGE_MODEL,
                                    api_key=api_key)
        self.model_name = self._client.model_name

    def load_model(self):
        return self._client

    def generate(self, prompt: str, schema=None):
        return self._client.generate(prompt, schema=schema)

    async def a_generate(self, prompt: str, schema=None):
        return await self._client.a_generate(prompt, schema=schema)

    def get_model_name(self) -> str:
        return f"{self.model_name} (Gemini judge)"

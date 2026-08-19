"""Minimal Gemini client — deliberately free of any deepeval import.

Two consumers share it:
  * the OFFLINE judge (``core.judge.GeminiJudge``) wraps it behind DeepEval's
    ``DeepEvalBaseLLM`` interface, and
  * the LIVE scorer (``core.live``) calls it directly, so the production app
    process never needs the deepeval package installed (dependency-permanence
    decision: google-genai is already an app dependency; deepeval stays a
    dev/offline-eval tool).
"""
from __future__ import annotations

import os
from typing import Optional


class GeminiClient:
    """Thin sync/async wrapper over google-genai with structured output."""

    def __init__(self, model_name: Optional[str] = None, api_key: Optional[str] = None):
        self.model_name = model_name or os.environ.get("EVAL_JUDGE_MODEL", "gemini-3.5-flash")
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY")
        self._client = None

    def _load(self):
        if self._client is None:
            if not self._api_key:
                raise RuntimeError(
                    "GeminiClient needs an API key (GEMINI_API_KEY env or api_key=...)"
                )
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _config(self, schema):
        cfg = {"temperature": 0.0}
        if schema is not None:
            cfg["response_mime_type"] = "application/json"
            cfg["response_schema"] = schema
        return cfg

    def generate(self, prompt: str, schema=None):
        resp = self._load().models.generate_content(
            model=self.model_name, contents=prompt, config=self._config(schema)
        )
        if schema is not None:
            return schema.model_validate_json(resp.text)
        return resp.text

    async def a_generate(self, prompt: str, schema=None):
        resp = await self._load().aio.models.generate_content(
            model=self.model_name, contents=prompt, config=self._config(schema)
        )
        if schema is not None:
            return schema.model_validate_json(resp.text)
        return resp.text

"""Gemini provider (newer ``google-genai`` SDK) with manual tool calling.

Kept separate from the legacy ``app/integrations/ai/client.py`` (deprecated SDK,
no function calling), which stays untouched for existing features. Manual — not
automatic — function calling is used: the SDK returns ``function_call`` parts and
the agent decides whether/how to execute them (so writes can be gated in CP2).
"""
from __future__ import annotations

import asyncio
import logging
from typing import List, Optional

from google import genai
from google.genai import types

from app.config import settings
from app.modules.assistant.providers.base import LLMTurn, ToolCall, ToolResult

logger = logging.getLogger(__name__)

# Hard ceiling on a single model round. Without it, a stalled upstream HTTPS
# connection hangs run_turn forever server-side — no events, no `done`, a
# leaked task, and a client stuck on the watchdog. A timeout turns that into
# an honest `error` event instead.
_GENERATE_TIMEOUT_SECONDS = 90


class GeminiProvider:
    def __init__(self, model: Optional[str] = None, api_key: Optional[str] = None) -> None:
        self.model = model or settings.assistant_model
        self.client = genai.Client(api_key=api_key or settings.gemini_api_key)

    def agent_session(
        self, *, system: Optional[str], tool: Optional[types.Tool],
        history: Optional[List[dict]] = None,
    ) -> "GeminiAgentSession":
        return GeminiAgentSession(self.client, self.model, system=system, tool=tool, history=history)


class GeminiAgentSession:
    """Holds the native ``contents`` list for one assistant turn's tool loop."""

    def __init__(
        self,
        client: genai.Client,
        model: str,
        *,
        system: Optional[str],
        tool: Optional[types.Tool],
        history: Optional[List[dict]] = None,
    ) -> None:
        self._client = client
        self._model = model
        self._contents: list = []
        # Seed a short rolling history of prior turns (plain text) so multi-turn
        # continuations ("continue", "fill the rest") keep context. Text-only —
        # no prior tool calls are replayed (they'd re-execute nothing; only the
        # conversational context matters here).
        for h in history or []:
            role = "model" if h.get("role") == "assistant" else "user"
            text = (h.get("text") or "").strip()
            if text:
                self._contents.append(types.Content(role=role, parts=[types.Part(text=text)]))
        self._config = types.GenerateContentConfig(
            system_instruction=system,
            tools=[tool] if tool else None,
            # We handle execution ourselves so write commands can be confirmation-gated.
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    async def _generate(self) -> LLMTurn:
        try:
            resp = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=self._contents,
                    config=self._config,
                ),
                timeout=_GENERATE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            # str(TimeoutError()) is empty — raise something the error event can show.
            raise RuntimeError(
                "The model took too long to respond. Please try again."
            ) from None
        candidate = resp.candidates[0] if resp.candidates else None
        texts: List[str] = []
        calls: List[ToolCall] = []
        if candidate and candidate.content:
            # Keep the model's turn in history so tool responses have context.
            self._contents.append(candidate.content)
            for part in candidate.content.parts or []:
                if getattr(part, "text", None):
                    texts.append(part.text)
                fc = getattr(part, "function_call", None)
                if fc:
                    calls.append(
                        ToolCall(
                            name=fc.name,
                            args=dict(fc.args or {}),
                            id=getattr(fc, "id", None),
                        )
                    )
        return LLMTurn(text="".join(texts) or None, tool_calls=calls)

    async def send_user(self, text: str) -> LLMTurn:
        self._contents.append(types.Content(role="user", parts=[types.Part(text=text)]))
        return await self._generate()

    async def send_tool_results(self, results: List[ToolResult]) -> LLMTurn:
        parts = [
            types.Part.from_function_response(name=r.call.name, response=r.content)
            for r in results
        ]
        self._contents.append(types.Content(role="user", parts=parts))
        return await self._generate()


_provider: Optional[GeminiProvider] = None


def get_provider() -> GeminiProvider:
    """Lazy singleton so the API key is read at first use, not import time."""
    global _provider
    if _provider is None:
        _provider = GeminiProvider()
    return _provider


def create_agent_session(*, system: Optional[str], tool: Optional[types.Tool],
                         history: Optional[List[dict]] = None):
    """Factory used by the agent loop. Swap here to change providers."""
    return get_provider().agent_session(system=system, tool=tool, history=history)

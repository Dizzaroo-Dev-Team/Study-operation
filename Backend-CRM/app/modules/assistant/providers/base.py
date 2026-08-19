"""Provider seam for the agent's tool-calling loop.

The agent orchestrates a turn as: send the user message -> get an ``LLMTurn``
(final text and/or tool calls) -> execute any tool calls via the route-invoker
-> send the results back -> repeat until the model returns a final answer or the
iteration cap is hit. A provider keeps its own native conversation state behind
this interface, so swapping Gemini for Anthropic later only means implementing
``AgentSession`` again.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class ToolCall:
    """A model request to invoke one registered command."""
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    id: Optional[str] = None


@dataclass
class ToolResult:
    """The outcome of executing a ToolCall, fed back to the model."""
    call: ToolCall
    content: Dict[str, Any]


@dataclass
class LLMTurn:
    """One model response: optional final text plus any tool calls it wants run."""
    text: Optional[str] = None
    tool_calls: List[ToolCall] = field(default_factory=list)


@runtime_checkable
class AgentSession(Protocol):
    async def send_user(self, text: str) -> LLMTurn:
        ...

    async def send_tool_results(self, results: List[ToolResult]) -> LLMTurn:
        ...

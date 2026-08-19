"""LLM provider seam for the assistant.

Kept separate from the app's legacy ``app/integrations/ai`` (which uses the
deprecated ``google.generativeai`` SDK with no function calling). The agent
builds on the newer ``google-genai`` SDK so tool-calling works. The
``AgentSession`` protocol in ``base`` keeps an Anthropic swap possible later.
"""
from .base import AgentSession, LLMTurn, ToolCall, ToolResult
from .gemini import create_agent_session

__all__ = [
    "AgentSession",
    "LLMTurn",
    "ToolCall",
    "ToolResult",
    "create_agent_session",
]

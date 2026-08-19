"""
app.integrations.ai - focused AI feature modules.

Layout:
  client.py         Gemini client wrapper (init, availability, generate_json).
  formatters.py     Message-to-prompt-text formatters (pure functions).
  summarization.py  Conversation and thread summarization.
  compose_assist.py Multi-draft reply generation + pre-send checks.
  classification.py Auto-classification + per-message tone analysis.
  chat.py           Document-grounded chat + general chat with history.
  similarity.py     Thread similarity analysis for combine-threads workflow.
  service.py        AIService backward-compat facade (delegates to the above).

New code should import feature functions directly, e.g.:

    from app.integrations.ai import summarization, AIClient
    summary = await summarization.summarize_conversation(client, conv, messages)

Existing code that does ``from app.integrations.ai import ai_service`` or
``from app.integrations.ai import AIService`` continues to work via the shim file.
"""
from app.integrations.ai.client import AIClient
from app.integrations.ai.service import AIService
from app.integrations.ai import (
    chat,
    classification,
    compose_assist,
    formatters,
    similarity,
    summarization,
)

# Module-level singleton (preserves the historical pattern set by
# app/ai_service.py:1199 - `ai_service = AIService()` at import time).
ai_service = AIService()

__all__ = [
    "AIClient",
    "AIService",
    "ai_service",
    "chat",
    "classification",
    "compose_assist",
    "formatters",
    "similarity",
    "summarization",
]

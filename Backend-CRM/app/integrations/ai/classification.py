"""Conversation auto-classification + per-message tone / delta analysis."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.integrations.ai.client import AIClient


async def classify_conversation(
    client: AIClient,
    context_text: str,
    latest_message_text: str,
) -> Optional[Dict[str, Any]]:
    """Classify a conversation into category/priority/sentiment/next action.

    Returns a normalised dict with keys:
      ai_category, ai_priority, ai_sentiment, ai_next_best_action
    """
    if not client.is_available():
        return None

    prompt = f"""
You are analysing a CRM conversation.

Conversation context:
{context_text}

Most recent message:
{latest_message_text}

Classify the conversation and suggest a next best action.

Allowed values:
- aiCategory: "ops", "admission", "sales", "support", "other"
- aiPriority: "low", "medium", "high", "urgent"
- aiSentiment: "negative", "neutral", "positive"

Output STRICTLY the following JSON (no comments, no extra text):
{{
  "aiCategory": "ops|admission|sales|support|other",
  "aiPriority": "low|medium|high|urgent",
  "aiSentiment": "negative|neutral|positive",
  "aiNextBestAction": "short natural‑language recommendation"
}}
"""
    data = await client.generate_json(prompt)
    if not data:
        # If Gemini fails or returns invalid JSON, skip classification for this conversation.
        # UI will simply not show any pills instead of showing generic defaults.
        return None

    # Normalise / validate with safe fallbacks
    cat = str(data.get("aiCategory") or "other").lower()
    if cat not in {"ops", "admission", "sales", "support", "other"}:
        cat = "other"

    prio = str(data.get("aiPriority") or "medium").lower()
    if prio not in {"low", "medium", "high", "urgent"}:
        prio = "medium"

    sent = str(data.get("aiSentiment") or "neutral").lower()
    if sent not in {"negative", "neutral", "positive"}:
        sent = "neutral"

    nba = str(data.get("aiNextBestAction") or "")

    return {
        "ai_category": cat,
        "ai_priority": prio,
        "ai_sentiment": sent,
        "ai_next_best_action": nba,
    }


async def analyse_new_message(
    client: AIClient,
    history_text: str,
    new_message_text: str,
) -> Optional[Dict[str, Any]]:
    """Analyse a new message: update summary delta + tone.

    Returns dict { 'delta_summary': str, 'tone': str }.
    """
    if not client.is_available():
        return None

    prompt = f"""
You are analysing the latest message in a CRM conversation or thread.

Conversation / thread history (including older messages):
{history_text}

Newest message:
{new_message_text}

Tasks:
1. Briefly summarise what changed with this latest message compared to the previous history.
2. Classify the tone of the latest message into one of:
   "neutral", "polite", "angry", "confused", "urgent".

Output STRICTLY this JSON (no extra text):
{{
  "deltaSummary": "string",
  "tone": "neutral|polite|angry|confused|urgent"
}}
"""
    data = await client.generate_json(prompt)
    if not data:
        return None

    tone = str(data.get("tone") or "neutral").lower()
    if tone not in {"neutral", "polite", "angry", "confused", "urgent"}:
        tone = "neutral"

    return {
        "delta_summary": str(data.get("deltaSummary") or ""),
        "tone": tone,
    }

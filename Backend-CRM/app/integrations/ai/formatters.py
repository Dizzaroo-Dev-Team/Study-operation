"""Pure formatters that turn message lists into prompt-ready text blocks.

These functions accept either SQLAlchemy ORM objects or MongoDB-style dicts
(the codebase uses both) and produce a single string suitable for inclusion
in a Gemini prompt.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List


def format_messages_for_summary(messages: List[Any]) -> str:
    """Format messages into a readable text format for summarization.

    Reused for compose-assist / classification prompts as well.
    """
    formatted: List[str] = []
    for msg in messages:
        try:
            # Support both SQLAlchemy objects and MongoDB dicts
            if isinstance(msg, dict):
                author = msg.get("author_name") or msg.get("author_id") or "Unknown"
                direction_val = msg.get("direction", "outbound")
                direction = "Sent" if str(direction_val) == "outbound" else "Received"
                channel_val = msg.get("channel", "email")
                channel = str(channel_val).upper()
                ts = msg.get("created_at")
                if ts is None:
                    timestamp = "Unknown time"
                elif hasattr(ts, "strftime"):
                    timestamp = ts.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        timestamp = ts[:19] if len(ts) >= 19 else ts
                else:
                    timestamp = str(ts)
                body = str(msg.get("body", "") or "")
            else:
                author = msg.author_name or msg.author_id or "Unknown"
                direction = "Sent" if msg.direction.value == "outbound" else "Received"
                channel = msg.channel.value.upper()
                if hasattr(msg.created_at, "strftime"):
                    timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    timestamp = str(msg.created_at)
                body = str(msg.body or "")

            formatted.append(f"[{timestamp}] {author} ({direction} via {channel}): {body}")
        except Exception as e:
            print(f"⚠️ Error formatting message for summary: {e}")
            continue

    return "\n".join(formatted) if formatted else "No messages to format."


def format_thread_messages_for_summary(messages: List[Any]) -> str:
    """Format thread messages into a readable text format for summarization."""
    formatted: List[str] = []
    for msg in messages:
        try:
            if isinstance(msg, dict):
                author = msg.get("author_name") or msg.get("author_id") or "Unknown"
                ts = msg.get("created_at")
                if ts is None:
                    timestamp = "Unknown time"
                elif hasattr(ts, "strftime"):
                    timestamp = ts.strftime("%Y-%m-%d %H:%M:%S")
                elif isinstance(ts, str):
                    try:
                        dt = datetime.fromisoformat(ts.replace('Z', '+00:00'))
                        timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        timestamp = ts[:19] if len(ts) >= 19 else ts
                else:
                    timestamp = str(ts)
                body = str(msg.get("body", "") or "")
            else:
                author = msg.author_name or msg.author_id or "Unknown"
                if hasattr(msg.created_at, "strftime"):
                    timestamp = msg.created_at.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    timestamp = str(msg.created_at)
                body = str(msg.body or "")

            formatted.append(f"[{timestamp}] {author}: {body}")
        except Exception as e:
            print(f"⚠️ Error formatting thread message for summary: {e}")
            continue

    return "\n".join(formatted) if formatted else "No messages to format."


def format_thread_messages_for_analysis(messages: List[Dict[str, Any]]) -> str:
    """Format thread messages (dict form) for AI similarity analysis."""
    if not messages:
        return "No messages"

    formatted = []
    for msg in messages:
        author = msg.get('author_name') or msg.get('author_id', 'Unknown')
        body = msg.get('body', '')
        created_at = msg.get('created_at', '')
        formatted.append(f"- {author}: {body} ({created_at})")

    return "\n".join(formatted)

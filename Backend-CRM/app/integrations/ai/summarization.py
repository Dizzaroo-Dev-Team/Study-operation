"""Conversation and thread summarization."""
from __future__ import annotations

import asyncio
from typing import List, Optional

from app.models import Conversation, Message, Thread, ThreadMessage
from app.integrations.ai.cache import cached_text_generate
from app.integrations.ai.client import AIClient
from app.integrations.ai.formatters import (
    format_messages_for_summary,
    format_thread_messages_for_summary,
)


async def summarize_conversation(
    client: AIClient,
    conversation: Conversation,
    messages: List[Message],
    max_messages: int = 50,
) -> Optional[str]:
    """Generate a summary of a conversation using Gemini AI."""
    if not client.is_available():
        print("❌ AI service not available in summarize_conversation")
        return None

    if not client.model:
        print("❌ AI model not initialized in summarize_conversation")
        return None

    if not messages:
        return "No messages in this conversation."

    # Take the most recent messages if there are too many
    messages_to_summarize = messages[-max_messages:] if len(messages) > max_messages else messages

    # Build context, supporting both SQLAlchemy objects and Mongo dicts
    context_parts: List[str] = []

    if isinstance(conversation, dict):
        subject = conversation.get("subject")
        study_id = conversation.get("study_id")
        participant_phone = conversation.get("participant_phone")
        participant_email = conversation.get("participant_email")
    else:
        subject = getattr(conversation, "subject", None)
        study_id = getattr(conversation, "study_id", None)
        participant_phone = getattr(conversation, "participant_phone", None)
        participant_email = getattr(conversation, "participant_email", None)

    if subject:
        context_parts.append(f"Subject: {subject}")
    if study_id:
        context_parts.append(f"Study ID: {study_id}")
    if participant_phone:
        context_parts.append(f"Participant Phone: {participant_phone}")
    if participant_email:
        context_parts.append(f"Participant Email: {participant_email}")

    context = "\n".join(context_parts) if context_parts else "No additional context"

    messages_text = format_messages_for_summary(messages_to_summarize)

    prompt = f"""Please provide a concise summary of the following clinical trial CRM conversation.
Focus on key points, decisions, issues, and action items.

Conversation Context:
{context}

Messages ({len(messages_to_summarize)} of {len(messages)} total):
{messages_text}

Please provide a summary that includes:
1. Main topic or issue discussed
2. Key participants and their contributions
3. Important decisions or outcomes
4. Any action items or next steps
5. Overall status or resolution

Summary:"""

    # Read-through cache: repeated summaries of an unchanged conversation
    # return in ~5ms instead of paying another 5-30s Gemini call. Cache key
    # is sha256(prompt) so when messages change, the prompt changes, and the
    # cache misses correctly.
    try:
        return await cached_text_generate(
            client,
            prompt,
            cache_namespace="summarize_conversation",
            ttl_seconds=3600,
        )
    except Exception as e:
        print(f"Error generating conversation summary: {e}")
        import traceback
        traceback.print_exc()
        return None


async def summarize_thread(
    client: AIClient,
    thread: Thread,
    messages: List[ThreadMessage],
    max_messages: int = 50,
) -> Optional[str]:
    """Generate a summary of a thread using Gemini AI."""
    if not client.is_available():
        return None

    if not messages:
        return "No messages in this thread."

    messages_to_summarize = messages[-max_messages:] if len(messages) > max_messages else messages

    # Build context, supporting both SQLAlchemy objects and Mongo dicts
    if isinstance(thread, dict):
        title = thread.get("title")
        thread_type = thread.get("thread_type")
        status = thread.get("status")
        priority = thread.get("priority")
        description = thread.get("description")
        related_patient_id = thread.get("related_patient_id")
        related_study_id = thread.get("related_study_id")
    else:
        title = getattr(thread, "title", None)
        thread_type = getattr(thread, "thread_type", None)
        status = getattr(thread, "status", None)
        priority = getattr(thread, "priority", None)
        description = getattr(thread, "description", None)
        related_patient_id = getattr(thread, "related_patient_id", None)
        related_study_id = getattr(thread, "related_study_id", None)

    context_parts: List[str] = [
        f"Thread Title: {title}",
        f"Thread Type: {thread_type}",
        f"Status: {status}",
        f"Priority: {priority}",
    ]

    if description:
        context_parts.append(f"Description: {description}")
    if related_patient_id:
        context_parts.append(f"Related Patient ID: {related_patient_id}")
    if related_study_id:
        context_parts.append(f"Related Study ID: {related_study_id}")

    context = "\n".join(context_parts)

    messages_text = format_thread_messages_for_summary(messages_to_summarize)

    prompt = f"""Please provide a concise summary of the following clinical trial CRM thread discussion.
Focus on key points, issues, decisions, and action items.

Thread Context:
{context}

Messages ({len(messages_to_summarize)} of {len(messages)} total):
{messages_text}

Please provide a summary that includes:
1. Main issue or topic being discussed
2. Key participants and their contributions
3. Important decisions or resolutions
4. Any action items or next steps
5. Current status and any blockers

Summary:"""

    try:
        return await cached_text_generate(
            client,
            prompt,
            cache_namespace="summarize_thread",
            ttl_seconds=3600,
        )
    except Exception as e:
        print(f"Error generating thread summary: {e}")
        import traceback
        traceback.print_exc()
        return None

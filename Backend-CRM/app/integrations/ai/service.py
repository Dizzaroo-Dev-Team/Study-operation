"""
AIService facade.

Backward-compatible facade over the feature modules. Existing callers still
do ``ai_service.summarize_conversation(...)`` etc. - those calls now delegate
to the focused per-feature modules, but the public surface is unchanged.

To switch to function-style imports incrementally, callers can do:

    from app.integrations.ai import summarization
    summary = await summarization.summarize_conversation(client, ...)

instead of going through ``AIService``. New code should prefer that style.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.models import Conversation, Message, Thread, ThreadMessage
from app.integrations.ai.client import AIClient
from app.integrations.ai import (
    chat as _chat,
    classification as _classification,
    compose_assist as _compose,
    similarity as _similarity,
    summarization as _summarization,
)
from app.integrations.ai.formatters import (
    format_messages_for_summary as _format_messages_for_summary,
    format_thread_messages_for_summary as _format_thread_messages_for_summary,
)


class AIService(AIClient):
    """Compatibility facade: extends AIClient with the feature methods that
    used to live directly on the monolithic class.

    The methods below are 1-line delegations to module-level functions in
    app/services/ai/<feature>.py. Do not add new logic here - put it in the
    feature module.
    """

    async def summarize_conversation(
        self,
        conversation: Conversation,
        messages: List[Message],
        max_messages: int = 50,
    ) -> Optional[str]:
        return await _summarization.summarize_conversation(self, conversation, messages, max_messages)

    async def summarize_thread(
        self,
        thread: Thread,
        messages: List[ThreadMessage],
        max_messages: int = 50,
    ) -> Optional[str]:
        return await _summarization.summarize_thread(self, thread, messages, max_messages)

    async def compose_reply(
        self,
        history_text: str,
        latest_draft: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        return await _compose.compose_reply(self, history_text, latest_draft)

    async def check_message_before_send(
        self,
        context_text: str,
        draft_body: str,
        attachments: List[str],
    ) -> Optional[Dict[str, Any]]:
        return await _compose.check_message_before_send(self, context_text, draft_body, attachments)

    async def classify_conversation(
        self,
        context_text: str,
        latest_message_text: str,
    ) -> Optional[Dict[str, Any]]:
        return await _classification.classify_conversation(self, context_text, latest_message_text)

    async def analyse_new_message(
        self,
        history_text: str,
        new_message_text: str,
    ) -> Optional[Dict[str, Any]]:
        return await _classification.analyse_new_message(self, history_text, new_message_text)

    async def chat_with_document(
        self,
        question: str,
        document_path: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        mode: str = "general",
    ) -> Optional[str]:
        return await _chat.chat_with_document(self, question, document_path, chat_history, mode)

    def _format_messages_for_summary(self, messages: List[Any]) -> str:
        return _format_messages_for_summary(messages)

    def _format_thread_messages_for_summary(self, messages: List[Any]) -> str:
        return _format_thread_messages_for_summary(messages)

    async def analyze_thread_similarity(
        self,
        thread1_data: Dict[str, Any],
        thread2_data: Dict[str, Any],
        thread1_messages: List[Dict[str, Any]],
        thread2_messages: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        return await _similarity.analyze_thread_similarity(
            self, thread1_data, thread2_data, thread1_messages, thread2_messages
        )

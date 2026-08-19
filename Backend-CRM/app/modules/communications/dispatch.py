"""Outbound dispatch helpers for the Communications message handlers (FF-1).

Centralizes how the conversation message handler enqueues its Celery tasks so
the dispatch logic lives in ONE place and is unit-testable.

Enqueue calls ``.delay()`` directly: it is a fast, non-blocking Redis publish,
so enqueuing happens synchronously and reliably — no ThreadPoolExecutor, no
un-retained ``create_task``, and no 1s ``wait_for`` wrapper that could let the
enqueue task be garbage-collected before it ran (the original FF-1 bug).

Only the conversation handler is covered here: the thread handler already calls
``.delay()`` directly, so it has no FF-1 bug to fix.
"""
import logging

logger = logging.getLogger(__name__)


async def enqueue_send_message(msg_id: str) -> None:
    """Enqueue the outbound-send task for a conversation message."""
    from app.workers.tasks import send_message_task
    try:
        send_message_task.delay(str(msg_id))
    except Exception:
        logger.exception("Failed to enqueue send_message_task for msg %s", msg_id)


async def enqueue_ai_message(msg_id: str, conversation_id: str, body: str) -> None:
    """Enqueue the background AI-analysis task for a conversation message."""
    from app.workers.tasks import process_message_ai_task
    try:
        process_message_ai_task.delay(str(msg_id), str(conversation_id), body)
    except Exception:
        logger.exception("Failed to enqueue process_message_ai_task for msg %s", msg_id)

"""Outbound conversation/thread message delivery (email via @mentions)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from app import crud
from app.config import settings
from app.db import AsyncSessionLocal
from app.integrations.smtp_service import smtp_service
from app.models import MessageChannel, MessageStatus
from app.modules.communications.repositories import (
    ThreadMessageRepository,
    ThreadRepository,
)
from app.utils.email_mentions import extract_mention_emails
from app.websocket_manager import manager

logger = logging.getLogger(__name__)

_MENTION_IN_BODY = re.compile(
    r"@([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"
)


async def _with_timeout(coro, timeout=10, default=None, operation_name="operation"):
    import asyncio

    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning("%s timed out after %ss", operation_name, timeout)
        return default
    except Exception as exc:
        logger.exception("%s failed: %s", operation_name, exc)
        return default


def _recipient_emails(msg: dict) -> list[str]:
    """Resolve @email mention recipients from stored field or message body."""
    mentioned = list(msg.get("mentioned_emails") or [])
    if not mentioned:
        mentioned = extract_mention_emails(msg.get("body") or "")
    out: list[str] = []
    seen: set[str] = set()
    for email in mentioned:
        normalized = str(email).strip().lower()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def _conversation_alias_email(context: dict, source_type: str) -> tuple[str, Optional[str]]:
    """Return (from_email, reply_to) using the verified SMTP user as From."""
    from app.utils.email_alias import (
        build_conversation_alias,
        build_thread_alias,
        format_display_alias,
    )

    smtp_user = (settings.smtp_user or "").strip()
    smtp_domain = smtp_user.split("@")[1] if "@" in smtp_user else "dizzaroo.com"

    if source_type == "thread":
        local_part = format_display_alias(
            context.get("study_external_id") or context.get("related_study_id"),
            context.get("site_external_id") or context.get("site_id"),
            "t",
            context.get("thread_number"),
        )
    else:
        local_part = format_display_alias(
            context.get("study_external_id") or context.get("study_id"),
            context.get("site_external_id") or context.get("site_id"),
            "c",
            context.get("conversation_number"),
        )

    if not local_part:
        local_part = context.get("email_alias")
    if not local_part:
        if source_type == "thread":
            local_part = build_thread_alias(
                context.get("study_external_id") or context.get("related_study_id"),
                context.get("site_external_id") or context.get("site_id"),
                context.get("id"),
                thread_number=context.get("thread_number"),
            )
        else:
            local_part = build_conversation_alias(
                context.get("study_external_id") or context.get("study_id"),
                context.get("site_external_id") or context.get("site_id"),
                context.get("id"),
                conversation_number=context.get("conversation_number"),
            )

    reply_to = f"{local_part}@{smtp_domain}" if local_part else None
    # Mailgun delivers most reliably when From matches the authenticated SMTP user.
    from_email = smtp_user or reply_to or f"noreply@{smtp_domain}"
    return from_email, reply_to


async def deliver_outbound_message(
    message_id: str,
    source_type: str = "conversation",
) -> None:
    """Send a queued outbound message (email when channel=email + @mentions)."""
    async with AsyncSessionLocal() as db:
        msg = None
        context = None
        is_email_send = False

        if source_type == "thread":
            msg = await _with_timeout(
                ThreadMessageRepository.get_by_id(UUID(message_id)),
                timeout=5,
                default=None,
                operation_name="Get thread message for sending",
            )
            if not msg:
                logger.warning("Thread message %s not found", message_id)
                return
            existing = msg.get("status")
            if isinstance(existing, MessageStatus):
                existing = existing.value
            if existing in (MessageStatus.SENT.value, MessageStatus.DELIVERED.value):
                return
            context = await _with_timeout(
                ThreadRepository.get_by_id(msg["thread_id"]),
                timeout=5,
                default=None,
                operation_name="Get thread for sending",
            )
            if not context:
                logger.warning("Thread %s not found", msg.get("thread_id"))
                return
            is_email_send = True
        else:
            msg = await _with_timeout(
                crud.get_message(db, UUID(message_id)),
                timeout=5,
                default=None,
                operation_name="Get message for sending",
            )
            if not msg:
                logger.warning("Message %s not found", message_id)
                return
            existing = msg.get("status")
            if isinstance(existing, MessageStatus):
                existing = existing.value
            if existing in (MessageStatus.SENT.value, MessageStatus.DELIVERED.value):
                return
            context = await _with_timeout(
                crud.get_conversation(db, msg["conversation_id"]),
                timeout=5,
                default=None,
                operation_name="Get conversation for sending",
            )
            if not context:
                logger.warning("Conversation %s not found", msg.get("conversation_id"))
                return
            channel = msg.get("channel")
            if isinstance(channel, str):
                channel = MessageChannel(channel)
            is_email_send = channel == MessageChannel.EMAIL

        if is_email_send:
            recipient_emails = _recipient_emails(msg)
            if not recipient_emails:
                logger.info(
                    "Message %s has no @email mentions — skipping email send",
                    message_id,
                )
                if source_type == "thread":
                    await _with_timeout(
                        ThreadMessageRepository.update_fields(
                            UUID(message_id),
                            {
                                "status": MessageStatus.DELIVERED.value,
                                "delivered_at": datetime.now(timezone.utc),
                            },
                        ),
                        timeout=5,
                        operation_name="Mark thread message delivered (no email)",
                    )
                else:
                    await _with_timeout(
                        crud.update_message_status(
                            db, UUID(message_id), MessageStatus.DELIVERED, sent_at=None
                        ),
                        timeout=5,
                        operation_name="Mark message delivered (no email)",
                    )
                return

            logger.info(
                "Sending email for message %s to %s",
                message_id,
                recipient_emails,
            )

            from_email, reply_to = _conversation_alias_email(context, source_type)
            subject = (
                context.get("subject")
                or context.get("title")
                or "Message from Clinical Trials CRM"
            )
            raw_body = msg.get("body") or ""
            body = _MENTION_IN_BODY.sub("", raw_body)
            body = re.sub(r"[ \t]{2,}", " ", body)
            body = re.sub(r"\n{3,}", "\n\n", body).strip() or "Message sent"

            tracker = context.get("tracker_code")
            if tracker and tracker not in subject:
                subject = f"{subject} [{tracker}]"

            author = (msg.get("author_name") or "").strip()
            if author:
                body = f"{body}\n\n— {author}"

            try:
                result = smtp_service.send_email(
                    to=recipient_emails,
                    subject=subject,
                    body=body,
                    from_email=from_email,
                    from_name="Clinical Trials CRM",
                    reply_to=reply_to,
                )
            except Exception as exc:
                logger.exception("SMTP send_email raised: %s", exc)
                result = {"success": False, "error": str(exc)}

            if result.get("success"):
                if source_type == "thread":
                    await _with_timeout(
                        ThreadMessageRepository.update_fields(
                            UUID(message_id),
                            {
                                "status": MessageStatus.SENT.value,
                                "provider_message_id": result.get("message_id"),
                                "sent_at": datetime.now(timezone.utc),
                            },
                        ),
                        timeout=5,
                        operation_name="Update thread message to SENT",
                    )
                else:
                    await _with_timeout(
                        crud.update_message_status(
                            db,
                            UUID(message_id),
                            MessageStatus.SENT,
                            provider_message_id=result.get("message_id"),
                            sent_at=datetime.now(timezone.utc),
                        ),
                        timeout=5,
                        operation_name="Update message to SENT",
                    )
                    await _with_timeout(
                        manager.publish_event(
                            context["id"],
                            {
                                "type": "message_status",
                                "message_id": message_id,
                                "status": "sent",
                            },
                        ),
                        timeout=3,
                        operation_name="Publish message sent event",
                    )
                return

            logger.error(
                "Email delivery failed for message %s: %s",
                message_id,
                result.get("error"),
            )
            if source_type == "thread":
                await _with_timeout(
                    ThreadMessageRepository.update_fields(
                        UUID(message_id), {"status": MessageStatus.FAILED.value}
                    ),
                    timeout=5,
                    operation_name="Mark thread message FAILED",
                )
            else:
                await _with_timeout(
                    crud.update_message_status(db, UUID(message_id), MessageStatus.FAILED),
                    timeout=5,
                    operation_name="Mark message FAILED",
                )
            return

        # Non-email channels — mock provider
        from app.workers.provider import MockProvider

        provider = MockProvider()
        channel = msg.get("channel")
        if isinstance(channel, str):
            channel = MessageChannel(channel)
        provider_id = provider.send(
            channel=channel,
            to=context.get("participant_phone"),
            body=msg.get("body"),
        )
        await _with_timeout(
            crud.update_message_status(
                db,
                UUID(message_id),
                MessageStatus.SENT,
                provider_message_id=provider_id,
                sent_at=datetime.now(timezone.utc),
            ),
            timeout=5,
            operation_name="Update non-email message to SENT",
        )


def schedule_outbound_message(message_id: str, source_type: str = "conversation") -> None:
    """Queue Celery delivery; fall back to inline send if broker is unavailable."""
    from app.workers.tasks import run_async, send_message_task

    try:
        send_message_task.delay(message_id, source_type=source_type)
        logger.info("Queued send_message_task for %s", message_id)
    except Exception as exc:
        logger.warning(
            "Celery enqueue failed for message %s (%s) — delivering inline",
            message_id,
            exc,
        )
        run_async(deliver_outbound_message(message_id, source_type=source_type))

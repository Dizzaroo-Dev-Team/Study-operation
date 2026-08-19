from app.workers.celery_app import celery_app
from app.workers.provider import MockProvider
from app.db import AsyncSessionLocal
from app import crud
from app.models import MessageStatus, MessageDirection, MessageChannel
from app.config import settings
from app.websocket_manager import manager
from app.integrations.ai import ai_service

from app.modules.communications.repositories import (
    ConversationRepository,
    MessageRepository,
    ThreadRepository,
    ThreadMessageRepository,
)

from datetime import datetime, timezone
from typing import Any, Dict
from uuid import UUID
import asyncio
import re
import logging

logger = logging.getLogger(__name__)
provider = MockProvider()


# -------------------------------------------------
# Async runner (Celery-safe)
# -------------------------------------------------
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    result = loop.run_until_complete(coro)

    # TASK-ENGINE-DISPOSE: we do NOT dispose the SQLAlchemy pool after every task.
    # Under the default Celery prefork pool this run_async reuses one stable
    # per-process event loop, and the module-singleton async engine's asyncpg
    # pool is bound to it — so reusing the pool avoids per-task reconnect churn.
    # (Only valid on the prefork pool, NOT gevent/eventlet/threads, where
    # multiple loops would share the singleton pool unsafely.)

    return result


# -------------------------------------------------
# Timeout helper for async operations
# -------------------------------------------------
async def with_timeout(coro, timeout=10, default=None, operation_name="operation"):
    """Wrap async operations with timeout to prevent hanging."""
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(f"{operation_name} timed out after {timeout}s")
        return default
    except Exception as e:
        logger.exception(f"{operation_name} failed: {e}")
        return default


def inbound_sender_allowed(allowed_senders, sender) -> bool:
    """Decide whether an inbound email `sender` may post into a conversation/thread.

    Anti-forgery rule: enforce the allowlist only when we actually have one.

    * Non-empty allowlist → the sender MUST be in it (rejects forged replies).
    * Empty allowlist → accept. The inbound email already matched this
      conversation/thread's private alias and there are no recorded
      correspondents to compare against, so there is no basis to reject a
      legitimate reply. Rejecting here would silently drop real replies, because
      conversation recipients arrive via @mentions in message bodies rather than
      a stored participant list — so the allowlist is built from the actual
      correspondents (see `_collect_correspondent_emails`) before this check.
    """
    normalized = (sender or "").lower().strip()
    if not allowed_senders:
        return True
    return normalized in allowed_senders


async def _collect_correspondent_emails(messages_coro) -> set:
    """Emails a conversation/thread has actually corresponded with — the
    ``mentioned_emails`` recorded on its prior messages (the people we emailed,
    who would legitimately reply). Building the inbound allowlist from these
    makes anti-forgery enforcement meaningful even though recipients are not
    stored as participants. Fails open to an empty set (never blocks on error).
    """
    msgs = await with_timeout(
        messages_coro,
        timeout=5,
        default=[],
        operation_name="Load messages for inbound allowlist",
    )
    out: set = set()
    for m in (msgs or []):
        mentioned = m.get("mentioned_emails") if isinstance(m, dict) else None
        for e in (mentioned or []):
            if e:
                out.add(str(e).lower().strip())
    return out


# =================================================
# TWO-PHASE SEND MARKER (Option B) — shared helpers
# =================================================
# Non-enum string statuses stored on the Mongo message doc. Kept as plain
# strings (not added to the SQLEnum MessageStatus) so there is no Postgres enum
# migration — messages live in Mongo and these are written as strings only.
STATUS_SENDING = "sending"
STATUS_NEEDS_REVIEW = "needs_review"


async def _msg_set_fields(message_id: str, source_type: str, fields: Dict[str, Any]):
    """Set arbitrary fields on a conversation OR thread message (Mongo)."""
    if source_type == "thread":
        return await ThreadMessageRepository.update_fields(UUID(message_id), fields)
    return await MessageRepository.update_fields(UUID(message_id), fields)


async def _reload_message(message_id: str, source_type: str):
    if source_type == "thread":
        return await ThreadMessageRepository.get_by_id(UUID(message_id))
    return await MessageRepository.get_by_id(UUID(message_id))


async def _claim_for_send(message_id: str, source_type: str):
    """Atomic queued→sending claim across the right collection. Returns the doc
    if claimed by THIS caller, else None."""
    if source_type == "thread":
        return await ThreadMessageRepository.claim_for_send(UUID(message_id))
    return await MessageRepository.claim_for_send(UUID(message_id))



# =================================================
# OUTBOUND MESSAGE TASK
# =================================================
# `acks_late=True` makes Celery hold the message in the queue until this task
# returns, so a worker crash mid-send re-queues instead of dropping. The
# idempotency check below means the re-run is safe — a message already
# marked SENT/DELIVERED short-circuits before re-hitting SMTP, so customers
# don't get duplicate emails after a worker restart.
@celery_app.task(
    acks_late=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def send_message_task(message_id: str, source_type: str = "conversation"):
    from app.modules.communications.services.message_delivery import deliver_outbound_message

    run_async(deliver_outbound_message(message_id, source_type=source_type))


# =================================================
# GENERIC OUTBOUND EMAIL TASK
# =================================================
# Background sink for transactional emails (signing invites, OTP, feasibility
# confirmations, monitoring notifications, …). Previously these were sent by
# directly calling `smtp_service.send_email(...)` from inside `async def`
# routes — each call blocked the FastAPI event loop for ~1-5s on the SMTP
# handshake. Enqueue this task instead and return immediately.
#
# The task itself is intentionally a plain sync function: SMTP is sync, the
# Celery worker is a separate process, and async-wrapping just to call sync
# code adds nothing. Failures are logged at WARNING and reraised so the
# Celery default-retry can kick in on transient errors.
@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,           # 2s, 4s, 8s, 16s …
    retry_backoff_max=300,        # cap at 5 minutes between retries
    retry_jitter=True,
    max_retries=3,
)
def send_email_task(
    self,
    to,                # str | list[str]
    subject: str,
    body: str,
    from_email: str,
    from_name: str | None = None,
    html: bool = False,
    attachments=None,  # list[str] | None
    reply_to: str | None = None,
):
    """Celery task wrapper around `smtp_service.send_email`.

    Returns the same dict shape as `send_email` so a caller that needs the
    result can `.get()` the AsyncResult — but the common case is fire-and-
    forget via `enqueue_email(...)`.
    """
    # Import lazily so the Celery worker bootstrap stays cheap and avoids
    # circular imports at module load time.
    from app.integrations.smtp_service import smtp_service

    try:
        result = smtp_service.send_email(
            to=to,
            subject=subject,
            body=body,
            from_email=from_email,
            from_name=from_name,
            html=html,
            attachments=attachments,
            reply_to=reply_to,
        )
    except Exception as exc:
        logger.warning("send_email_task: SMTP raised: %s", exc)
        raise

    if not result.get("success"):
        # Treat SMTP soft-failures the same as exceptions so the retry policy
        # above gets a shot at transient issues (DNS hiccup, rate-limit).
        err = result.get("error", "unknown SMTP error")
        logger.warning("send_email_task: SMTP returned failure: %s", err)
        raise RuntimeError(f"SMTP send failed: {err}")

    return result


# =================================================
# AI PROCESSING TASK (BACKGROUND)
# =================================================
@celery_app.task
def process_message_ai_task(message_id: str, conversation_id: str, message_body: str):
    """Process AI analysis for a message in the background without blocking the request."""
    async def _process_ai():
        try:
            if not ai_service.is_available():
                logger.info("AI service not available, skipping AI processing")
                return

            from app.modules.communications.repositories import (
    MessageRepository,
    ConversationRepository,
)
            
            # Get conversation with timeout
            conv = await with_timeout(
                ConversationRepository.get_by_id(UUID(conversation_id)),
                timeout=5,
                default=None,
                operation_name="Get conversation for AI"
            )
            if not conv:
                logger.warning(f"Conversation {conversation_id} not found for AI processing")
                return

            # Load recent messages with timeout
            history = await with_timeout(
                MessageRepository.list_by_conversation(UUID(conversation_id), limit=50, offset=0),
                timeout=5,
                default=[],
                operation_name="Load message history for AI"
            )

            if history:
                # Pin analysis to the message this task was actually queued for, not
                # whichever message happens to be most recent at execution time. If
                # two messages arrive back-to-back, the second one was overwriting
                # the first one's analysis.
                target_uuid = UUID(message_id)
                target = next(
                    (m for m in history if str(m.get('id')) == str(target_uuid)),
                    None,
                )
                older = [m for m in history if str(m.get('id')) != str(target_uuid)]
                history_text = ai_service._format_messages_for_summary(older[::-1])  # oldest->newest

                # Use the queued body if the target message has been deleted in flight.
                target_body = (target or {}).get('body') if target else message_body

                # Analyze new message with timeout
                analysis = await with_timeout(
                    ai_service.analyse_new_message(history_text, target_body or ''),
                    timeout=10,
                    default=None,
                    operation_name="AI message analysis"
                )
                if analysis and target:
                    await with_timeout(
                        MessageRepository.update_fields(target.get('id'), {
                            'ai_tone': analysis.get('tone'),
                            'ai_delta_summary': analysis.get('delta_summary'),
                        }),
                        timeout=5,
                        default=None,
                        operation_name="Update message AI fields"
                    )

                    # Broadcast so the right-sidebar Tone/Changes tabs refresh live.
                    try:
                        await with_timeout(
                            manager.publish_event(
                                UUID(conversation_id),
                                {
                                    "type": "ai_message_update",
                                    "conversation_id": str(conversation_id),
                                    "message": {
                                        "id": str(target.get('id')),
                                        "ai_tone": analysis.get('tone'),
                                        "ai_delta_summary": analysis.get('delta_summary'),
                                    },
                                },
                            ),
                            timeout=3,
                            default=None,
                            operation_name="Publish AI message update",
                        )
                    except Exception as pub_err:
                        logger.warning(f"Failed to publish AI message update: {pub_err}")

            # Auto-classify conversation and refresh summary with timeouts
            messages_text = ai_service._format_messages_for_summary(history[::-1] if history else [])
            
            classification = await with_timeout(
                ai_service.classify_conversation(messages_text or "", message_body),
                timeout=10,
                default=None,
                operation_name="AI conversation classification"
            )
            
            summary = await with_timeout(
                ai_service.summarize_conversation(conv, history[::-1] if history else []),
                timeout=10,
                default=None,
                operation_name="AI conversation summary"
            )
            
            updates = {}
            if classification:
                updates.update(classification)
            if summary:
                updates['ai_summary'] = summary
                updates['ai_summary_updated_at'] = datetime.now(timezone.utc)
            
            if updates:
                await with_timeout(
                    ConversationRepository.update(UUID(conversation_id), updates),
                    timeout=5,
                    default=None,
                    operation_name="Update conversation AI fields"
                )

                # Broadcast conversation-level AI updates so the Summary tab can
                # refresh without requiring the user to click "Generate" again.
                if 'ai_summary' in updates:
                    try:
                        await with_timeout(
                            manager.publish_event(
                                UUID(conversation_id),
                                {
                                    "type": "ai_conversation_update",
                                    "conversation_id": str(conversation_id),
                                    "ai_summary": updates.get('ai_summary'),
                                },
                            ),
                            timeout=3,
                            default=None,
                            operation_name="Publish AI conversation update",
                        )
                    except Exception as pub_err:
                        logger.warning(f"Failed to publish AI conversation update: {pub_err}")

            logger.info(f"✅ AI processing completed for message {message_id}")
        except Exception as e:
            logger.error(f"AI processing failed for message {message_id}: {e}", exc_info=True)

    run_async(_process_ai())


# =================================================
# INBOUND MAILGUN WEBHOOK TASK
# =================================================
@celery_app.task
def process_webhook_task(payload: dict):
    async def _process():
        async with AsyncSessionLocal() as db:

            if payload.get("event_type") != "inbound":
                return

            recipient = payload.get("recipient")
            sender = payload.get("sender")

            body = (
                payload.get("stripped_text")
                or payload.get("body_plain")
                or payload.get("stripped_html")
                or ""
            )

            logger.warning("📩 Inbound email received")
            logger.warning(f"   From: {sender}")
            logger.warning(f"   To: {recipient}")
            logger.warning(f"   Body preview: {body[:200]}")

            if not recipient:
                logger.warning("Missing recipient")
                return

            # Alias rule: local_part = clean(study_name) + clean(site_name)
            #   clean = lowercase, strip every non-[a-z0-9] character.
            # We can't reliably split the concatenation, so we look up by
            # rebuilding the same alias for each candidate conversation.
            local_part = recipient.split("@")[0] if "@" in recipient else recipient
            local_part_norm = re.sub(r"[^a-z0-9]+", "", local_part.lower())

            from app.db.mongo import get_mongo_db
            mongo = await with_timeout(
                get_mongo_db(),
                timeout=5,
                default=None,
                operation_name="Get MongoDB connection",
            )
            if mongo is None:
                logger.error("Failed to get MongoDB connection, aborting webhook processing")
                return

            from app.utils.email_alias import (
                alias_base,
                build_conversation_alias,
                build_thread_alias,
                iter_prefixes,
            )

            # 1) Fast path: indexed lookup on the stamped email_alias field.
            conv_doc = await with_timeout(
                mongo["conversations"].find_one({"email_alias": local_part_norm}),
                timeout=5,
                default=None,
                operation_name="Find conversation by email_alias",
            )
            thread_doc = None
            if not conv_doc:
                thread_doc = await with_timeout(
                    mongo["threads"].find_one({"email_alias": local_part_norm}),
                    timeout=5,
                    default=None,
                    operation_name="Find thread by email_alias",
                )

            # 1b) Indexed longest-prefix fallback: external mail clients sometimes
            # strip or mutate the trailing `c<6hex>` / `t<8hex>` disambiguator on
            # reply. We stamp `email_alias_base = clean(study)+clean(site)` on every
            # doc and look up by `$in`-of-all-prefixes against that field — single
            # indexed query, no scan.
            if not conv_doc and not thread_doc:
                prefixes = iter_prefixes(local_part_norm)
                if prefixes:
                    conv_candidates = await with_timeout(
                        mongo["conversations"]
                        .find({"email_alias_base": {"$in": prefixes}})
                        .to_list(length=50),
                        timeout=5,
                        default=[],
                        operation_name="Find conversation by email_alias_base prefix",
                    )
                    if conv_candidates:
                        # Longest matching base wins; tie-break by most recent.
                        conv_candidates.sort(
                            key=lambda d: (
                                len(d.get("email_alias_base") or ""),
                                d.get("updated_at") or d.get("created_at") or 0,
                            ),
                            reverse=True,
                        )
                        conv_doc = conv_candidates[0]
                        logger.info(
                            f"📬 Resolved inbound via email_alias_base prefix: "
                            f"conv={conv_doc.get('id')} base='{conv_doc.get('email_alias_base')}' "
                            f"recipient_local='{local_part_norm}'"
                        )
                    else:
                        thread_candidates = await with_timeout(
                            mongo["threads"]
                            .find({"email_alias_base": {"$in": prefixes}})
                            .to_list(length=50),
                            timeout=5,
                            default=[],
                            operation_name="Find thread by email_alias_base prefix",
                        )
                        if thread_candidates:
                            thread_candidates.sort(
                                key=lambda d: (
                                    len(d.get("email_alias_base") or ""),
                                    d.get("updated_at") or d.get("created_at") or 0,
                                ),
                                reverse=True,
                            )
                            thread_doc = thread_candidates[0]
                            logger.info(
                                f"📬 Resolved inbound via email_alias_base prefix: "
                                f"thread={thread_doc.get('id')} base='{thread_doc.get('email_alias_base')}' "
                                f"recipient_local='{local_part_norm}'"
                            )

            # 2) Slow path: legacy docs with no email_alias field. Scan, rebuild,
            #    compare, and lazy-backfill the alias on the matched doc so the next
            #    inbound is fast.
            #
            #    We fetch full docs (no projection) so that downstream sender
            #    verification has access to participant_emails / participants_emails.
            if not conv_doc and not thread_doc:
                legacy_conv = await with_timeout(
                    mongo["conversations"]
                    .find({"email_alias_base": {"$in": [None, ""]}})
                    .limit(500)
                    .to_list(length=500),
                    timeout=8,
                    default=[],
                    operation_name="Scan legacy conversations for alias rebuild",
                )
                best_conv = None
                best_conv_base_len = 0
                for candidate in legacy_conv:
                    base = alias_base(candidate.get("study_id"), candidate.get("site_id"))
                    rebuilt = build_conversation_alias(
                        candidate.get("study_id"),
                        candidate.get("site_id"),
                        candidate.get("id"),
                    )
                    matched = False
                    if rebuilt and rebuilt == local_part_norm:
                        matched = True  # strict-equality wins outright
                        best_conv = (candidate, base, rebuilt)
                        best_conv_base_len = 1 << 30
                        break
                    if base and local_part_norm.startswith(base) and len(base) > best_conv_base_len:
                        best_conv = (candidate, base, rebuilt)
                        best_conv_base_len = len(base)
                if best_conv:
                    candidate, base, rebuilt = best_conv
                    conv_doc = candidate
                    backfill: Dict[str, Any] = {}
                    if rebuilt and not candidate.get("email_alias"):
                        backfill["email_alias"] = rebuilt
                    if base and not candidate.get("email_alias_base"):
                        backfill["email_alias_base"] = base
                    if backfill:
                        await with_timeout(
                            mongo["conversations"].update_one(
                                {"_id": candidate["_id"]}, {"$set": backfill}
                            ),
                            timeout=3, default=None, operation_name="Backfill conversation alias",
                        )

                if not conv_doc:
                    legacy_threads = await with_timeout(
                        mongo["threads"]
                        .find({"email_alias_base": {"$in": [None, ""]}})
                        .limit(500)
                        .to_list(length=500),
                        timeout=8,
                        default=[],
                        operation_name="Scan legacy threads for alias rebuild",
                    )
                    best_thread = None
                    best_thread_base_len = 0
                    for candidate in legacy_threads:
                        base = alias_base(candidate.get("related_study_id"), candidate.get("site_id"))
                        rebuilt = build_thread_alias(
                            candidate.get("related_study_id"),
                            candidate.get("site_id"),
                            candidate.get("id"),
                        )
                        if rebuilt and rebuilt == local_part_norm:
                            best_thread = (candidate, base, rebuilt)
                            best_thread_base_len = 1 << 30
                            break
                        if base and local_part_norm.startswith(base) and len(base) > best_thread_base_len:
                            best_thread = (candidate, base, rebuilt)
                            best_thread_base_len = len(base)
                    if best_thread:
                        candidate, base, rebuilt = best_thread
                        thread_doc = candidate
                        backfill = {}
                        if rebuilt and not candidate.get("email_alias"):
                            backfill["email_alias"] = rebuilt
                        if base and not candidate.get("email_alias_base"):
                            backfill["email_alias_base"] = base
                        if backfill:
                            await with_timeout(
                                mongo["threads"].update_one(
                                    {"_id": candidate["_id"]}, {"$set": backfill}
                                ),
                                timeout=3, default=None, operation_name="Backfill thread alias",
                            )

            if not conv_doc and not thread_doc:
                logger.warning(
                    f"No conversation or thread found for recipient={recipient} "
                    f"(local_part_norm='{local_part_norm}'). Inbound email will not be processed."
                )
                return

            if conv_doc:
                logger.info(
                    f"✅ Found conversation: {conv_doc.get('id')} "
                    f"for study={conv_doc.get('study_id')}, site={conv_doc.get('site_id')}"
                )
            else:
                logger.info(
                    f"✅ Found thread: {thread_doc.get('id')} "
                    f"for study={thread_doc.get('related_study_id')}, site={thread_doc.get('site_id')}"
                )

            # ====== Thread inbound branch ======
            if thread_doc:
                import uuid as _uuid

                thread_id_raw = thread_doc.get("id")
                try:
                    thread_id = thread_id_raw if isinstance(thread_id_raw, UUID) else UUID(str(thread_id_raw))
                except (ValueError, TypeError):
                    logger.exception(f"Invalid thread ID format: {thread_id_raw}")
                    return

                # Sender verification: re-load the full thread doc so we can check
                # the participants list. The projected `thread_doc` from the find
                # only has the fields we asked for.
                full_thread = await with_timeout(
                    ThreadRepository.get_by_id(thread_id),
                    timeout=5,
                    default=None,
                    operation_name="Reload thread for sender verification",
                ) or thread_doc

                allowed_senders = {
                    str(email).lower().strip()
                    for email in (full_thread.get("participants_emails") or [])
                    if email
                }
                created_by = str(full_thread.get("created_by") or "").lower().strip()
                if created_by and "@" in created_by:
                    allowed_senders.add(created_by)
                # Include everyone this thread has actually emailed (mentioned in
                # prior messages) so a legitimate reply is accepted while forged
                # senders are still rejected.
                allowed_senders |= await _collect_correspondent_emails(
                    ThreadMessageRepository.list_by_thread(thread_id)
                )

                if not inbound_sender_allowed(allowed_senders, sender):
                    logger.warning(
                        "Rejecting inbound: sender '%s' not permitted for thread %s "
                        "(allowlist=%s).",
                        sender, thread_id, sorted(allowed_senders),
                    )
                    return

                # Append inbound thread message.
                msg_id = _uuid.uuid4()
                thread_msg_data = {
                    "id": msg_id,
                    "thread_id": thread_id,
                    "message_id": None,
                    "body": body,
                    "author_id": sender,
                    "author_name": sender,
                    "mentioned_emails": [],
                    "message_type": None,
                    "metadata": {
                        "subject": payload.get("subject"),
                        "from": sender,
                        "direction": "inbound",
                        "channel": "email",
                    },
                }
                created = await with_timeout(
                    ThreadMessageRepository.create(thread_msg_data),
                    timeout=5,
                    default=None,
                    operation_name="Create inbound thread message",
                )
                if not created:
                    logger.error("Failed to create inbound thread message")
                    return

                created_at = created.get("created_at") if isinstance(created, dict) else None
                created_at_str = created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or datetime.now(timezone.utc).isoformat())

                # Touch thread updated_at so the inbox re-orders.
                await with_timeout(
                    ThreadRepository.update(thread_id, {"updated_at": datetime.now(timezone.utc)}),
                    timeout=5,
                    default=None,
                    operation_name="Update thread updated_at after inbound",
                )

                # Notify subscribed clients.
                try:
                    await with_timeout(
                        manager.publish_event(
                            thread_id,
                            {
                                "type": "new_thread_message",
                                "thread_id": str(thread_id),
                                "message": {
                                    "id": str(msg_id),
                                    "body": body,
                                    "author_id": sender,
                                    "author_name": sender,
                                    "created_at": created_at_str,
                                    "direction": "inbound",
                                    "channel": "email",
                                },
                            },
                        ),
                        timeout=3,
                        default=None,
                        operation_name="Publish inbound thread message event",
                    )
                except Exception as e:
                    logger.error(f"Failed to publish thread WebSocket event: {e}", exc_info=True)

                logger.warning("✅ Inbound email saved to thread & broadcast")
                return

            # ====== Conversation inbound branch ======

            conversation = ConversationRepository._normalize_doc(conv_doc)

            # Sender verification: only accept replies from a known participant.
            # Anyone who guesses the alias would otherwise be able to inject messages.
            participant_emails = conversation.get("participant_emails") or []
            participant_email = conversation.get("participant_email")

            allowed_senders = {
                str(email).lower().strip()
                for email in [*(participant_emails or []), participant_email]
                if email
            }
            # Conversation recipients arrive via @mentions, not a stored
            # participant list, so build the allowlist from everyone this
            # conversation has actually emailed (mentioned in prior messages).
            # A legitimate reply is accepted; a forged sender is still rejected.
            conv_uuid_for_lookup = conversation.get("id")
            try:
                conv_uuid_for_lookup = (
                    conv_uuid_for_lookup
                    if isinstance(conv_uuid_for_lookup, UUID)
                    else UUID(str(conv_uuid_for_lookup))
                )
                allowed_senders |= await _collect_correspondent_emails(
                    MessageRepository.list_by_conversation(conv_uuid_for_lookup)
                )
            except (ValueError, TypeError):
                pass

            if not inbound_sender_allowed(allowed_senders, sender):
                logger.warning(
                    "Rejecting inbound: sender '%s' not permitted for conversation %s "
                    "(allowlist=%s).",
                    sender, conversation.get('id'), sorted(allowed_senders),
                )
                return

            conv_id_str = conversation["id"]
            
            # Convert conv_id to UUID if it's a string
            if isinstance(conv_id_str, str):
                try:
                    conv_id = UUID(conv_id_str)
                except ValueError:
                    logger.exception(f"Invalid conversation ID format: {conv_id_str}")
                    return
            else:
                conv_id = conv_id_str

            # -------- Create inbound message --------
            from app.schemas import MessageCreate

            msg_create = MessageCreate(
                channel=MessageChannel.EMAIL,
                body=body,
                metadata={
                    "subject": payload.get("subject"),
                    "from": sender,
                },
            )

            try:
                db_msg = await with_timeout(
                    crud.create_message(
                        db,
                        conv_id,
                        msg_create,
                        MessageDirection.INBOUND,
                        author_id=sender,
                        author_name=sender,
                    ),
                    timeout=5,
                    default=None,
                    operation_name="Create inbound message"
                )
                if not db_msg:
                    logger.error("Failed to create inbound message (timeout or error)")
                    return
                msg_id = db_msg.get('id') if isinstance(db_msg, dict) else db_msg.id
                msg_body = db_msg.get('body') if isinstance(db_msg, dict) else db_msg.body
                msg_created_at = db_msg.get('created_at') if isinstance(db_msg, dict) else db_msg.created_at
                msg_conv_id = db_msg.get('conversation_id') if isinstance(db_msg, dict) else db_msg.conversation_id
                logger.info(f"✅ Created inbound message: {msg_id} for conversation: {conv_id} (stored as: {msg_conv_id})")
            except Exception as e:
                logger.error(f"Exception creating inbound message: {e}", exc_info=True)
                return

            # Publish WebSocket event
            try:
                created_at_str = msg_created_at.isoformat() if hasattr(msg_created_at, 'isoformat') else str(msg_created_at)
                await with_timeout(
                    manager.publish_event(
                        conv_id,
                        {
                            "type": "new_message",
                            "conversation_id": str(conv_id),
                            "message": {
                                "id": str(msg_id),
                                "direction": "inbound",
                                "channel": "email",
                                "body": msg_body,
                                "author_id": sender,
                                "author_name": sender,
                                "created_at": created_at_str,
                            },
                        },
                    ),
                    timeout=3,
                    default=None,
                    operation_name="Publish inbound message event"
                )
                logger.info(f"✅ WebSocket event published for message: {msg_id}")
            except Exception as e:
                logger.error(f"Failed to publish WebSocket event: {e}", exc_info=True)
                # Don't fail the whole process if WebSocket fails

            logger.warning("✅ Inbound email saved & broadcast")

            # =================================================
            # AI PROCESSING (ASYNC, SAFE, OPTIONAL) - WITH TIMEOUTS
            # =================================================
            try:
                if ai_service.is_available():
                    history = await with_timeout(
                        MessageRepository.list_by_conversation(conv_id, limit=50),
                        timeout=5,
                        default=[],
                        operation_name="Load message history for inbound AI"
                    )

                    if history:
                        summary = await with_timeout(
                            ai_service.summarize_conversation(conversation, history[::-1]),
                            timeout=10,
                            default=None,
                            operation_name="AI summarize conversation (inbound)"
                        )

                        if summary:
                            await with_timeout(
                                ConversationRepository.update(
                                    conv_id,
                                    {
                                        "ai_summary": summary,
                                        "ai_summary_updated_at": datetime.now(timezone.utc),
                                    },
                                ),
                                timeout=5,
                                default=None,
                                operation_name="Update conversation summary (inbound)"
                            )

            except Exception as e:
                logger.warning(f"AI processing failed: {e}")

    run_async(_process())


# =================================================
# WORKFLOW PLATFORM V2 (Phase 4): timer scheduler + job executor sweeps.
# Each due timer / pending job becomes a system event routed through the same
# pure kernel.decide as every human action; the sweep functions live in
# app.modules.workflows.service and own no commit - we commit here.
# =================================================
@celery_app.task(acks_late=True)
def workflow_run_due_timers():
    async def _sweep():
        from app.modules.workflows import service as wf_service
        async with AsyncSessionLocal() as db:
            fired = await wf_service.run_due_timers(db)
            await db.commit()
            return fired
    return run_async(_sweep())


@celery_app.task(acks_late=True)
def workflow_run_pending_jobs():
    async def _sweep():
        from app.modules.workflows import service as wf_service
        async with AsyncSessionLocal() as db:
            processed = await wf_service.run_pending_jobs(db)
            await db.commit()
            return processed
    return run_async(_sweep())


@celery_app.task(acks_late=True)
def workflow_run_pending_waits():
    async def _sweep():
        from app.modules.workflows import service as wf_service
        async with AsyncSessionLocal() as db:
            advanced = await wf_service.run_pending_waits(db)
            await db.commit()
            return advanced
    return run_async(_sweep())


# =================================================
# ORBIT DERIVED MEMORY — nightly distillation (off the request path)
# =================================================
# Reads the short-TTL raw turn buffer, distils concise non-PHI memory items for
# each eligible user, merges/de-dups under the per-user cap, then prunes expired
# turns. Never writes memory during a live assistant turn. Fired by the embedded
# celery-beat schedule (assistant-memory-distill @ 03:00 UTC).
@celery_app.task(acks_late=True)
def assistant_memory_distill():
    async def _run():
        from app.modules.assistant.memory.derivation import run_distillation
        return await run_distillation()
    return run_async(_run())

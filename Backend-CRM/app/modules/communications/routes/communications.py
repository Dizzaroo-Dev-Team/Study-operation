from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header, Query, UploadFile, File, Form, Request, Body
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, delete, update
from sqlalchemy.orm import selectinload
from typing import Optional, List
from uuid import UUID
from datetime import timedelta, datetime, timezone
import asyncio
import os
import hashlib
import shutil
import aiofiles
from pathlib import Path
import secrets
from app.db import get_db, init_db
from app import crud, schemas
from app.models import MessageDirection, MessageStatus, MessageChannel, ConversationAccessLevel, ThreadAttachment, Attachment, Conversation, ChatDocument, PrimarySiteStatus, UserRoleAssignment, Site, Study, StudySite, SiteStatus, SiteWorkflowStep, SiteDocument, WorkflowStepName, StepStatus, DocumentCategory, DocumentType, ReviewStatus, ProjectFeasibilityCustomQuestion, FeasibilityRequest, FeasibilityResponse, FeasibilityRequestStatus, FeasibilityAttachment
from app.websocket_manager import manager
from app.config import settings
from app.auth import (
    create_access_token,
    get_password_hash,
    get_current_user,
    get_current_user_optional,
    _resolve_user_from_token,
    ACCESS_TOKEN_EXPIRE_MINUTES,
)
from app.modules.sites.services.site_status_service import (
    get_study_status_summary,
    get_country_site_counts,
    get_sites_by_status,
    get_site_status_detail,
)
from app.integrations.ai import ai_service
from app.modules.communications.services.conversation_service import ensure_public_notice_board
from app.modules.communications.guards import (
    require_conversation_member,
    require_conversation_admin,
    require_thread_member,
)
from app.modules.communications.audit_helpers import best_effort_audit
from app.utils.log_redact import mask_email
from app.utils.log_sanitize import sfmt
from app.utils.upload_safety import (
    safe_extension,
    stream_to_disk_safely,
    validate_upload_metadata,
    verify_magic_bytes,
)
import uuid
import logging
# Tasks imported where needed to avoid circular imports


router = APIRouter(tags=["Communications"])
logger = logging.getLogger(__name__)

# Strong references to fire-and-forget tasks so the event loop can't GC them
# before they finish (tasks remove themselves on completion).
_background_tasks: set = set()

# Thread message-handler dispatch timeouts (COMMS_DISPATCH_FIX). Module-level so
# they can be tightened in tests.
_THREAD_AI_TIMEOUT = 10.0
_THREAD_WS_TIMEOUT = 3.0

@router.post("/conversations", response_model=schemas.ConversationResponse)
async def create_conversation(
    conv: schemas.ConversationCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    # CRITICAL: Enforce study_id + site_id requirement for data isolation
    if not conv.study_id:
        raise HTTPException(status_code=400, detail="study_id is required for conversation creation")
    if not conv.site_id:
        raise HTTPException(status_code=400, detail="site_id is required for conversation creation")

    # Write-guard: require authentication so an anonymous request can't create
    # a conversation.
    if not (current_user or {}).get("user_id"):
        raise HTTPException(
            status_code=403, detail="Authentication required to create conversations"
        )

    # Cross-study guard: the caller must be entitled to the study they're
    # creating a conversation in (owner or grant) — the same study gate the
    # conversation-access check applies on the read side.
    from app.integrations.iam.membership import user_can_act_in_study
    if not await user_can_act_in_study((current_user or {}).get("user_id"), str(conv.study_id)):
        raise HTTPException(status_code=403, detail="You are not entitled to this study.")

    # Belt-and-suspenders against the notice_board unique-index collision:
    # user-created conversations are ALWAYS threads, and ALWAYS unpinned.
    # 'notice_board' + is_pinned='true' is reserved for the system-managed
    # per-(study, site) board created by `ensure_public_notice_board` /
    # `find_or_create_pinned_notice_board`. Forcing these here means even if
    # a stale Pydantic default ('notice_board') is still live in someone's
    # deployment, this route can't trip the partial-filter unique index.
    conv_dict = conv.dict()
    conv_dict['conversation_type'] = 'thread'
    conv_dict['is_pinned'] = False
    # Bind ownership to the authenticated caller; never trust a body-supplied
    # created_by (anti-spoof). user_id is guaranteed present by the guard above.
    conv_dict['created_by'] = (current_user or {}).get("user_id")
    conv = schemas.ConversationCreate(**conv_dict)
    db_conv = await crud.create_conversation(db, conv)

    # Activity feed: surface the new thread on the (study, site) Public Notice
    # Board so everyone else who lands on this site sees that a new
    # conversation just started. Best-effort — the thread is already persisted
    # and a notice-board write failure must never surface as a 500 here.
    try:
        from app.utils.system_notices import post_site_event_notice

        actor = (
            (current_user or {}).get("name")
            or (current_user or {}).get("email")
            or (current_user or {}).get("user_id")
            or "a user"
        )
        title = (
            (db_conv.get("title") if isinstance(db_conv, dict) else getattr(db_conv, "title", None))
            or (db_conv.get("subject") if isinstance(db_conv, dict) else getattr(db_conv, "subject", None))
            or "(no subject)"
        )
        await post_site_event_notice(
            db,
            site_ref=conv.site_id,
            study_ref=conv.study_id,
            event_type="conversation_created",
            message=f"New conversation '{title}' started by {actor}.",
            metadata={
                "conversation_id": str(
                    db_conv.get("id") if isinstance(db_conv, dict) else getattr(db_conv, "id", "")
                ),
            },
        )
    except Exception:
        logger.exception(
            "create_conversation: notice-board hook failed for study=%s site=%s",
            conv.study_id, conv.site_id,
        )

    await best_effort_audit(
        db, user=(current_user or {}).get("user_id"),
        action="conversation.create", target_type="conversation",
        target_id=str(db_conv.get("id") if isinstance(db_conv, dict) else getattr(db_conv, "id", "")),
        details={"study_id": conv.study_id, "site_id": conv.site_id},
    )
    return db_conv


@router.get("/conversations", response_model=List[schemas.ConversationResponse])
async def list_conversations(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    study_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    channel: Optional[MessageChannel] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """List conversations that are public within sites the user can access."""
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required to access conversations")

    if site_id:
        await ensure_public_notice_board(site_id, study_id)

    user_email = (current_user or {}).get("email")
    # Over-fetch a small buffer (not 10x — that produced 500-doc pulls and
    # one Postgres round-trip per doc). 2x is enough for typical pages where
    # the user has access to most listed conversations; pathological cases
    # (heavily filtered) just return slightly fewer than `limit`, which the
    # legacy 10x path also already accepted whenever buffer exhausted.
    fetch_size = max(limit * 2, limit + 25)
    conversations = await crud.list_conversations(
        db,
        limit=fetch_size,
        offset=offset,
        study_id=study_id,
        site_id=site_id,
        channel=channel,
        user_id=None,
    )

    # Auto-heal: the notice board MUST always be in the inbox when a site is
    # selected. The pre-create step above SHOULD guarantee that, but if anything
    # went wrong (silent upsert failure, stale index, partial deploy), refuse
    # to return a notice-board-less list. Force a create+refetch instead. This
    # only runs on the first page (offset == 0) since the board only ever lives
    # at the top of the sort.
    if site_id and offset == 0:
        has_notice_board = any(
            str((c or {}).get("conversation_type") or "").lower() == "notice_board"
            for c in conversations
        )
        if not has_notice_board:
            logger.warning(
                "list_conversations: notice_board missing for site=%s study=%s after "
                "ensure_public_notice_board; auto-healing with a second create+refetch.",
                sfmt(site_id), sfmt(study_id),
            )
            await ensure_public_notice_board(site_id, study_id)
            conversations = await crud.list_conversations(
                db,
                limit=fetch_size,
                offset=offset,
                study_id=study_id,
                site_id=site_id,
                channel=channel,
                user_id=None,
            )

    # One Postgres query for the whole page's ConversationAccess grants,
    # instead of one query per conversation. The set is consulted in-memory
    # by `check_user_can_access_conversation_by_role` below.
    candidate_ids = [c.get("id") for c in conversations if c.get("id")]
    access_set = await crud.bulk_check_conversation_access(db, candidate_ids, user_id)

    # The repository already returns docs sorted notice-board-first then by
    # created_at desc (DB-side sort via cursor + compound index). The access
    # filter below preserves order, so a trailing trim to `limit` is enough —
    # no second Python sort needed.
    visible = []
    for conv in conversations:
        if await crud.check_user_can_access_conversation_by_role(
            db, user_id, conv, user_email=user_email, access_set=access_set,
        ):
            visible.append(conv)

    return visible[:limit]


@router.get("/conversations/stats")
async def get_stats(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Get conversation and message statistics filtered by user access."""
    user_id = current_user.get("user_id") if current_user else None
    stats = await crud.get_conversation_stats(db, user_id=user_id)
    return stats


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(
    conversation_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a conversation and its messages. Notice boards cannot be deleted."""
    existing = await crud.get_conversation(db, conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_email = current_user.get("email")
    if not await crud.check_user_can_access_conversation_by_role(
        db, current_user["user_id"], existing, user_email=user_email
    ):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    try:
        deleted = await crud.delete_conversation(db, conversation_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Cascade: remove any Orbit memory / buffered turns derived from this
    # conversation (best-effort — never block the delete on the memory cleanup).
    try:
        from app.db import transactional
        from app.modules.assistant.memory import repository as memory_repo

        async with transactional(db):
            await memory_repo.delete_memory_for_conversation(db, conversation_id)
    except Exception:  # noqa: BLE001
        logger.exception("assistant memory: conversation-delete cascade failed")

    return {"status": "deleted", "conversation_id": str(conversation_id)}


@router.get("/conversations/{conversation_id}", response_model=schemas.ConversationWithMessages)
async def get_conversation(
    conversation_id: UUID,
    limit: int = Query(200, ge=1, le=500),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0)
):
    """Get conversation with messages (public within accessible site)."""
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required to access conversations")

    user_email = (current_user or {}).get("email")
    conv = await crud.get_conversation_with_messages(db, conversation_id, limit, offset)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not await crud.check_user_can_access_conversation_by_role(db, user_id, conv, user_email=user_email):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    # Handle dict from MongoDB - ensure messages have metadata field and proper format
    if isinstance(conv, dict):
        messages = conv.get('messages', [])
        
        # Normalize all messages
        normalized_messages = []
        for msg in messages:
            # Convert UUIDs to strings for JSON serialization
            normalized_msg = dict(msg)
            if 'id' in normalized_msg:
                normalized_msg['id'] = str(normalized_msg['id']) if isinstance(normalized_msg['id'], UUID) else normalized_msg['id']
            if 'conversation_id' in normalized_msg:
                normalized_msg['conversation_id'] = str(normalized_msg['conversation_id']) if isinstance(normalized_msg['conversation_id'], UUID) else normalized_msg['conversation_id']
            # Map metadata field
            if 'message_metadata' in normalized_msg and 'metadata' not in normalized_msg:
                normalized_msg['metadata'] = normalized_msg.pop('message_metadata')
            # Ensure status and direction are strings (handle both enum and string cases)
            if 'status' in normalized_msg:
                if hasattr(normalized_msg['status'], 'value'):
                    normalized_msg['status'] = normalized_msg['status'].value
                elif not isinstance(normalized_msg['status'], str):
                    normalized_msg['status'] = str(normalized_msg['status'])
            if 'direction' in normalized_msg:
                if hasattr(normalized_msg['direction'], 'value'):
                    normalized_msg['direction'] = normalized_msg['direction'].value
                elif not isinstance(normalized_msg['direction'], str):
                    normalized_msg['direction'] = str(normalized_msg['direction'])
                normalized_msg['direction'] = normalized_msg['direction'].lower()
            if 'channel' in normalized_msg:
                if hasattr(normalized_msg['channel'], 'value'):
                    normalized_msg['channel'] = normalized_msg['channel'].value
                elif not isinstance(normalized_msg['channel'], str):
                    normalized_msg['channel'] = str(normalized_msg['channel'])
                normalized_msg['channel'] = normalized_msg['channel'].lower()
            normalized_messages.append(normalized_msg)
        
        conv['messages'] = normalized_messages
    else:
        # Legacy SQLAlchemy model handling
        for msg in conv.messages:
            if hasattr(msg, 'message_metadata'):
                msg.metadata = msg.message_metadata
    return conv


@router.get("/conversations/{conversation_id}/summary")
async def get_conversation_summary(
    conversation_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Get AI-generated summary of a conversation (public within accessible site)."""
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required to access conversations")
    
    user_email = (current_user or {}).get("email")
    # Get conversation with messages
    conv = await crud.get_conversation_with_messages(db, conversation_id, limit=200, offset=0)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    if not await crud.check_user_can_access_conversation_by_role(db, user_id, conv, user_email=user_email):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")
    
    # Check if AI service is available
    if not ai_service.is_available():
        api_key_status = "configured" if settings.gemini_api_key else "not configured"
        raise HTTPException(
            status_code=503, 
            detail=f"AI service is not available. GEMINI_API_KEY is {api_key_status}. Please check your .env file."
        )
    
    # Generate summary
    try:
        # Handle dict from MongoDB
        messages = conv.get('messages', []) if isinstance(conv, dict) else conv.messages
        if not messages:
            return {"summary": "No messages in this conversation.", "conversation_id": str(conversation_id)}

        try:
            summary = await asyncio.wait_for(
                ai_service.summarize_conversation(conv, messages),
                timeout=20.0,
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=504,
                detail="AI summary request timed out. Please try again.",
            )

        if summary is None:
            raise HTTPException(status_code=500, detail="Failed to generate summary. Check backend logs for details.")

        return {"summary": summary, "conversation_id": str(conversation_id)}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error in get_conversation_summary")
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")


# ---------------------------------------------------------------------------
# AI: Compose reply + pre‑send checks
# ---------------------------------------------------------------------------


@router.post("/conversations/{conversation_id}/messages", response_model=schemas.MessageResponse)
async def create_message(
    conversation_id: UUID,
    msg: schemas.MessageCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required to post messages")

    # Per-(user, conversation) flood guard. Stops a runaway client from spamming
    # the AI pipeline / outbound queue. Configured generously for normal use.
    from app.utils.rate_limit import hit
    if not hit(("msg_create", str(user_id), str(conversation_id)), limit=30, window_seconds=60.0):
        raise HTTPException(
            status_code=429,
            detail="Too many messages in this conversation. Slow down and try again in a minute.",
        )

    # Verify conversation exists
    conv = await crud.get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # The Public Notice Board is system-write-only: it's the activity feed for
    # a (study, site), not a real conversation. Users see it but can't post —
    # the frontend hides the compose form, but a curl call would otherwise
    # bypass that, so block here as well.
    if str((conv or {}).get("conversation_type") or "").strip().lower() == "notice_board":
        raise HTTPException(
            status_code=403,
            detail="The Public Notice Board is read-only — system events are posted here automatically.",
        )

    # Symmetric with the read routes: only users who can access the conversation may post to it.
    user_email = (current_user or {}).get("email")
    if not await crud.check_user_can_access_conversation_by_role(db, user_id, conv, user_email=user_email):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    author_id = user_id
    author_name = current_user.get("name") or current_user.get("email") or author_id
    
    # Create message with status=queued and author information
    db_msg = await crud.create_message(
        db,
        conversation_id,
        msg,
        MessageDirection.OUTBOUND,
        author_id=author_id,
        author_name=author_name
    )

    # Handle dict from MongoDB
    msg_id = db_msg.get('id') if isinstance(db_msg, dict) else db_msg.id
    msg_channel = db_msg.get('channel') if isinstance(db_msg, dict) else db_msg.channel
    msg_body = db_msg.get('body') if isinstance(db_msg, dict) else db_msg.body
    msg_status = db_msg.get('status') if isinstance(db_msg, dict) else db_msg.status
    msg_author_id = db_msg.get('author_id') if isinstance(db_msg, dict) else db_msg.author_id
    msg_author_name = db_msg.get('author_name') if isinstance(db_msg, dict) else db_msg.author_name
    msg_created_at = db_msg.get('created_at') if isinstance(db_msg, dict) else db_msg.created_at

    # --- AI processing dispatched to a background Celery task (FF-1: see dispatch.py) ---
    from app.modules.communications import dispatch as _dispatch
    await _dispatch.enqueue_ai_message(str(msg_id), str(conversation_id), msg_body)

    # Create audit log. We wrap with a generous timeout so a sluggish DB does not
    # hang the request, but failures are surfaced at error level — audit gaps are
    # a compliance concern, not a non-critical print statement.
    try:
        await asyncio.wait_for(
            crud.create_audit_log(
                db,
                user=str(user_id),
                action="message_created",
                target_type="message",
                target_id=str(msg_id),
                details={
                    "conversation_id": str(conversation_id),
                    "channel": msg_channel if isinstance(msg_channel, str) else msg_channel.value,
                },
            ),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        logger.exception(
            "Audit log timed out for message_created msg_id=%s conv_id=%s user=%s",
            msg_id, conversation_id, user_id,
        )
    except Exception as e:
        logger.error(
            "Audit log failed for message_created msg_id=%s conv_id=%s user=%s: %s",
            msg_id, conversation_id, user_id, e,
            exc_info=True,
        )
    
    # Publish WebSocket event immediately for real-time updates (with timeout)
    try:
        from app.websocket_manager import manager
        created_at_str = msg_created_at.isoformat() if hasattr(msg_created_at, 'isoformat') else str(msg_created_at)
        event_data = {
            "conversation_id": str(conversation_id),
            "type": "new_message",
            "message": {
                "id": str(msg_id),
                "direction": MessageDirection.OUTBOUND.value,
                "channel": msg_channel if isinstance(msg_channel, str) else msg_channel.value,
                "body": msg_body,
                "status": msg_status if isinstance(msg_status, str) else msg_status.value,
                "author_id": msg_author_id,
                "author_name": msg_author_name,
                "created_at": created_at_str,
                "is_decision": False
            }
        }
        # Add timeout to prevent hanging
        await asyncio.wait_for(manager.publish_event(conversation_id, event_data), timeout=3.0)
    except asyncio.TimeoutError:
        logger.warning("WebSocket publish timed out for conversation %s", conversation_id)
    except Exception as e:
        logger.exception("Error publishing WebSocket event: %s", e)
    
    # Queue outbound delivery (Celery with inline SMTP fallback if broker is down).
    from app.modules.communications.services.message_delivery import schedule_outbound_message

    try:
        schedule_outbound_message(str(msg_id), source_type="conversation")
    except Exception as e:
        logger.error("Failed to schedule outbound message %s: %s", msg_id, e, exc_info=True)
    
    # Map message_metadata to metadata for response
    if isinstance(db_msg, dict):
        if 'message_metadata' in db_msg and 'metadata' not in db_msg:
            db_msg['metadata'] = db_msg.pop('message_metadata')
    elif hasattr(db_msg, 'message_metadata'):
        db_msg.metadata = db_msg.message_metadata

    return db_msg


@router.patch(
    "/conversations/{conversation_id}/messages/{message_id}/decision",
    response_model=schemas.MessageResponse,
)
async def set_message_decision(
    conversation_id: UUID,
    message_id: UUID,
    body: schemas.MessageDecisionUpdate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Pin / unpin a message as a 'decision of record'.

    Replaces the old regex heuristic — a decision is now something a user
    explicitly marks, so the Decisions panel reflects real choices.
    """
    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required")

    conv = await crud.get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_email = (current_user or {}).get("email")
    if not await crud.check_user_can_access_conversation_by_role(db, user_id, conv, user_email=user_email):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    updated = await crud.set_message_decision(db, message_id, body.is_decision)
    if not updated:
        raise HTTPException(status_code=404, detail="Message not found")

    # Broadcast so other viewers' Decisions panels update live. Reuses the
    # existing ai_message_update channel handler shape on the client.
    try:
        from app.websocket_manager import manager
        await asyncio.wait_for(
            manager.publish_event(
                conversation_id,
                {
                    "conversation_id": str(conversation_id),
                    "type": "message_flags_update",
                    "message": {"id": str(message_id), "is_decision": bool(body.is_decision)},
                },
            ),
            timeout=3.0,
        )
    except Exception as e:
        logger.warning("Decision flag WS publish failed for msg %s: %s", message_id, e)

    if isinstance(updated, dict) and 'message_metadata' in updated and 'metadata' not in updated:
        updated['metadata'] = updated.pop('message_metadata')
    return updated


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Multiplexed real-time channel.

    Wire protocol
    -------------
    After the WS handshake, the client may send any number of:
        {"action": "subscribe",   "kind": "conversation" | "thread", "id": "<uuid>"}
        {"action": "unsubscribe", "kind": "conversation" | "thread", "id": "<uuid>"}
        {"action": "ping"}                       (optional — server already heartbeats)

    Backwards-compat for the legacy single-subscribe shape used before Hunt 4
    is supported: `{"action":"subscribe","conversation_id":"<uuid>"}` is
    treated as `kind="conversation"`. Threads previously piggybacked on the
    same `conversation_id` field but were silently rejected by the access
    check (`crud.get_conversation` returned None) — those clients should
    upgrade to send `kind="thread"`.

    Per subscribe, the server:
      1. Authorizes the user against the target resource.
      2. Adds the socket to the manager's `active_connections[<uuid>]`.
      3. Acks with {"status":"subscribed","kind":...,"id":...}.

    On disconnect every channel the socket joined is cleaned up.
    """
    # Authenticate before accepting traffic. Resolution order mirrors the HTTP
    # dispatcher in app/auth.py:
    #   1. Starlette session cookie (set by the SSO callback) — primary in
    #      production hub mode. Browsers send same-origin cookies on the WS
    #      handshake, so this just works once SessionMiddleware is mounted.
    #   2. Bearer token from the ?token=<jwt> query param — used by the legacy
    #      local password flow and by non-browser callers.
    current_user: Optional[dict] = None
    try:
        session_user = (
            websocket.session.get("user") if hasattr(websocket, "session") else None
        )
    except (AssertionError, AttributeError):
        session_user = None
    if session_user and session_user.get("user_id"):
        current_user = session_user
    elif token:
        try:
            current_user = await _resolve_user_from_token(token)
        except HTTPException:
            current_user = None
        except Exception:
            current_user = None
    if not current_user or not current_user.get("user_id"):
        await websocket.close(code=1008, reason="Unauthenticated")
        return

    user_id = current_user.get("user_id")
    user_email = current_user.get("email")

    # Channels this socket has joined — needed so disconnect cleans up every
    # one, not just the (legacy) first subscribe.
    subscribed: set[UUID] = set()

    async def _authorize_and_join(kind: str, channel_id: UUID) -> Optional[str]:
        """Return None if the join was accepted; an error string otherwise."""
        if kind == "conversation":
            conv_doc = await crud.get_conversation(db, channel_id)
            if not conv_doc:
                return "Conversation not found"
            if not await crud.check_user_can_access_conversation_by_role(
                db, user_id, conv_doc, user_email=user_email,
            ):
                return "Forbidden"
        elif kind == "thread":
            thread_doc = await crud.get_thread(db, channel_id)
            if not thread_doc:
                return "Thread not found"
            if not await crud.check_user_can_access_thread(
                db, user_id, thread_doc, user_email=user_email,
            ):
                return "Forbidden"
        else:
            return f"Unknown kind: {kind}"

        await manager.connect(websocket, channel_id)
        subscribed.add(channel_id)
        return None

    try:
        await websocket.accept()
        logger.info("WebSocket connection accepted for user: %s", user_id)

        # Best-effort kick of the Redis listener (won't block if Redis is down).
        # Keep a strong reference so the event loop can't GC the task mid-flight.
        try:
            listener_task = asyncio.create_task(manager.start_listening())
            _background_tasks.add(listener_task)
            listener_task.add_done_callback(_background_tasks.discard)
        except Exception as e:
            logger.warning("Could not start Redis listener: %s. WebSocket will still work.", e)

        # Message loop. We use receive_json with a generous timeout so a
        # truly idle socket eventually closes rather than tying up a worker
        # forever, but any subscribe/unsubscribe/ping resets the timer.
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=120.0)
            except asyncio.TimeoutError:
                # No client traffic for 2 minutes — the heartbeat task should
                # have caught a dead socket by now; bail cleanly.
                try:
                    await websocket.close(code=1000, reason="Idle timeout")
                except Exception:
                    pass
                break
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning("WebSocket receive error: %s", e)
                break

            action = data.get("action") if isinstance(data, dict) else None

            # ── ping ────────────────────────────────────────────────────
            if action == "ping":
                try:
                    await websocket.send_json({"type": "pong"})
                except Exception:
                    break
                continue

            # ── subscribe ──────────────────────────────────────────────
            if action == "subscribe":
                kind = (data.get("kind") or "conversation").lower()
                # Legacy field — keep the old wire-format working.
                raw_id = data.get("id") or data.get("conversation_id")
                if not raw_id:
                    await websocket.send_json({"error": "Missing channel id"})
                    continue
                try:
                    channel_id = UUID(str(raw_id))
                except ValueError:
                    await websocket.send_json({"error": "Invalid id format"})
                    continue
                if channel_id in subscribed:
                    # Idempotent re-subscribe — ack but don't double-join.
                    await websocket.send_json(
                        {"status": "subscribed", "kind": kind, "id": str(channel_id),
                         # legacy alias for old clients
                         "conversation_id": str(channel_id)},
                    )
                    continue

                err = await _authorize_and_join(kind, channel_id)
                if err is not None:
                    await websocket.send_json(
                        {"error": err, "kind": kind, "id": str(channel_id)},
                    )
                    continue
                await websocket.send_json(
                    {"status": "subscribed", "kind": kind, "id": str(channel_id),
                     "conversation_id": str(channel_id)},
                )
                continue

            # ── unsubscribe ────────────────────────────────────────────
            if action == "unsubscribe":
                raw_id = data.get("id") or data.get("conversation_id")
                if not raw_id:
                    continue
                try:
                    channel_id = UUID(str(raw_id))
                except ValueError:
                    continue
                if channel_id in subscribed:
                    try:
                        await manager.disconnect(websocket, channel_id)
                    except Exception:
                        pass
                    subscribed.discard(channel_id)
                    try:
                        await websocket.send_json(
                            {"status": "unsubscribed", "id": str(channel_id)},
                        )
                    except Exception:
                        pass
                continue

            # Unknown action — tell the client and keep going.
            await websocket.send_json({"error": f"Unknown action: {action}"})

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.exception("WebSocket error")
    finally:
        # Clean up every channel this socket joined — the original code only
        # cleaned the (single) first subscribe, which leaked entries in
        # active_connections once the loop accepted N subscribes.
        for channel_id in list(subscribed):
            try:
                await manager.disconnect(websocket, channel_id)
            except Exception:
                pass


# Thread endpoints
@router.post("/threads", response_model=schemas.ThreadResponse)
async def create_thread(
    thread: schemas.ThreadCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Create a new thread with correct visibility semantics."""
    user_email = (current_user or {}).get("email")
    if not user_email:
        raise HTTPException(status_code=403, detail="Authentication required to create threads")

    # CRITICAL: Enforce study_id + site_id requirement for data isolation
    if not thread.related_study_id and not thread.site_id:
        raise HTTPException(
            status_code=400,
            detail="Either related_study_id or site_id is required for thread creation",
        )
    if thread.site_id and not thread.related_study_id:
        raise HTTPException(
            status_code=400,
            detail="related_study_id is required when site_id is provided",
        )

    # Normalize visibility scope
    visibility_scope = (thread.visibility_scope or "private").strip().lower()
    if visibility_scope not in ("private", "site"):
        visibility_scope = "private"

    creator_email = user_email.strip().lower()
    raw_participants = thread.participants_emails or []
    participants_emails = [
        str(e).strip().lower() for e in raw_participants if e and str(e).strip()
    ]

    if visibility_scope == "site":
        # Site-visible threads: no per-user participant list is needed for access control.
        participants_emails = []
    else:
        # Private threads: must contain creator + any selected users.
        if creator_email and creator_email not in participants_emails:
            participants_emails.append(creator_email)
        if not participants_emails:
            raise HTTPException(
                status_code=400,
                detail="participants_emails is required for private threads",
            )

    thread = thread.model_copy(
        update={
            "participants_emails": participants_emails,
            "visibility_scope": visibility_scope,
        }
    )
    db_thread = await crud.create_thread(db, thread)
    # Load with participants (db_thread is now a dict)
    thread_id = db_thread.get('id') if isinstance(db_thread, dict) else db_thread.id
    await best_effort_audit(
        db, user=(current_user or {}).get("user_id"),
        action="thread.create", target_type="thread", target_id=str(thread_id),
        details={"visibility_scope": visibility_scope, "site_id": thread.site_id},
    )
    return await crud.get_thread(db, thread_id)


@router.get("/threads", response_model=List[schemas.ThreadResponse])
async def list_threads(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    participant_id: Optional[str] = Query(None),
    study_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """List threads. NEW: Only returns threads where logged-in user's email is in participants_emails."""
    # Get user email for filtering
    user_email = None
    if current_user:
        user_email = current_user.get("email")
    
    if not user_email:
        # If no user email, return empty list (threads are private)
        return []
    
    threads = await crud.list_threads(
        db, limit, offset, participant_id, 
        study_id=study_id, site_id=site_id, user_email=user_email
    )
    return threads


@router.get("/threads/suggest-combinations", response_model=List[schemas.ThreadCombinationSuggestion])
async def suggest_thread_combinations(
    study_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=50),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    """
    AI-powered endpoint to suggest which threads should be combined.
    Analyzes all threads and returns suggestions with similarity scores.
    """
    logger.debug("suggest-combinations called with study_id=%s, site_id=%s, limit=%s", study_id, site_id, limit)

    # AI is optional here: deterministic matches (same title / conversation /
    # patient) still work without it. Only the LLM fallback pass is skipped when
    # the AI service is unavailable, instead of failing the whole endpoint.
    ai_on = ai_service.is_available()

    try:
        from app.modules.communications.repositories import (
    ThreadRepository,
    ThreadMessageRepository,
)
        
        # Get all threads for the study/site. Pass the caller's email so the
        # candidate pool matches what GET /threads shows them: site-wide threads
        # PLUS private threads they participate in. Without user_email the repo
        # silently restricts to visibility_scope='site', and since threads
        # default to 'private' that left the pool empty -> "No similar threads".
        user_email = (current_user or {}).get("email")
        threads = await ThreadRepository.list(
            limit=limit * 2,  # Get more threads to analyze
            offset=0,
            study_id=study_id,
            site_id=site_id,
            user_email=user_email,
        )

        if len(threads) < 2:
            return []
        
        suggestions = []
        ai_pairs = []  # pairs with no deterministic match → analyzed by AI below

        def _as_uuid(v):
            return v if isinstance(v, UUID) else UUID(str(v))

        # Compare each pair of threads
        for i in range(len(threads)):
            for j in range(i + 1, len(threads)):
                thread1 = threads[i]
                thread2 = threads[j]
                
                # Pre-check for exact matches (same title, same conversation, same patient)
                thread1_title = thread1.get('title', '').strip().lower()
                thread2_title = thread2.get('title', '').strip().lower()
                thread1_conv = thread1.get('conversation_id')
                thread2_conv = thread2.get('conversation_id')
                thread1_patient = thread1.get('related_patient_id')
                thread2_patient = thread2.get('related_patient_id')
                
                # Normalize conversation_id to string for comparison
                if thread1_conv:
                    thread1_conv = str(thread1_conv) if not isinstance(thread1_conv, str) else thread1_conv
                if thread2_conv:
                    thread2_conv = str(thread2_conv) if not isinstance(thread2_conv, str) else thread2_conv
                
                # Debug logging (ids/booleans only — no titles/patient text)
                logger.debug(
                    "Comparing threads: t1_conv=%s t2_conv=%s titles_match=%s convs_match=%s",
                    thread1_conv, thread2_conv,
                    thread1_title == thread2_title, thread1_conv == thread2_conv,
                )
                
                # Check 1: Same title (even without conversation)
                if thread1_title == thread2_title and thread1_title:
                    # Same title - check if same conversation or same patient
                    if thread1_conv and thread2_conv and thread1_conv == thread2_conv:
                        # Exact match: same title and same conversation
                        logger.debug("EXACT MATCH: same title + same conversation")
                        # Ensure IDs are UUIDs
                        thread1_uuid = thread1['id'] if isinstance(thread1['id'], UUID) else UUID(str(thread1['id']))
                        thread2_uuid = thread2['id'] if isinstance(thread2['id'], UUID) else UUID(str(thread2['id']))
                        suggestions.append(schemas.ThreadCombinationSuggestion(
                            thread1_id=thread1_uuid,
                            thread2_id=thread2_uuid,
                            thread1_title=thread1.get('title', 'Untitled'),
                            thread2_title=thread2.get('title', 'Untitled'),
                            should_combine=True,
                            similarity_score=95.0,  # High score for exact matches
                            reasoning=f"Exact match: Both threads have the same title '{thread1.get('title')}' and belong to the same conversation. These should be combined to avoid duplication.",
                            factors=["Same title", "Same conversation", "Exact match"],
                            recommendation="strong"
                        ))
                        continue
                    elif thread1_patient and thread2_patient and thread1_patient == thread2_patient:
                        # Same title and same patient
                        logger.debug("STRONG MATCH: same title + same patient")
                        # Ensure IDs are UUIDs
                        thread1_uuid = thread1['id'] if isinstance(thread1['id'], UUID) else UUID(str(thread1['id']))
                        thread2_uuid = thread2['id'] if isinstance(thread2['id'], UUID) else UUID(str(thread2['id']))
                        suggestions.append(schemas.ThreadCombinationSuggestion(
                            thread1_id=thread1_uuid,
                            thread2_id=thread2_uuid,
                            thread1_title=thread1.get('title', 'Untitled'),
                            thread2_title=thread2.get('title', 'Untitled'),
                            should_combine=True,
                            similarity_score=90.0,
                            reasoning=f"Strong match: Both threads have the same title '{thread1.get('title')}' and are for the same patient '{thread1_patient}'. These should be combined.",
                            factors=["Same title", "Same patient", "Strong match"],
                            recommendation="strong"
                        ))
                        continue
                    else:
                        # Just same title - still suggest combining
                        logger.debug("TITLE MATCH: same title (no conversation/patient match)")
                        # Ensure IDs are UUIDs
                        thread1_uuid = thread1['id'] if isinstance(thread1['id'], UUID) else UUID(str(thread1['id']))
                        thread2_uuid = thread2['id'] if isinstance(thread2['id'], UUID) else UUID(str(thread2['id']))
                        suggestions.append(schemas.ThreadCombinationSuggestion(
                            thread1_id=thread1_uuid,
                            thread2_id=thread2_uuid,
                            thread1_title=thread1.get('title', 'Untitled'),
                            thread2_title=thread2.get('title', 'Untitled'),
                            should_combine=True,
                            similarity_score=85.0,
                            reasoning=f"Title match: Both threads have the same title '{thread1.get('title')}'. These may be duplicates and should be combined.",
                            factors=["Same title", "Possible duplicate"],
                            recommendation="moderate"
                        ))
                        continue
                
                # No deterministic match — queue for AI analysis. We run these
                # concurrently after the loop instead of one blocking call per
                # pair (which made the endpoint O(n²) in wall-clock and time out).
                ai_pairs.append((thread1, thread2))

        # Analyze the non-deterministic pairs with AI, concurrently and bounded.
        if ai_on and ai_pairs:
            MAX_AI_PAIRS = 40
            if len(ai_pairs) > MAX_AI_PAIRS:
                logger.warning(
                    "suggest-combinations: %s candidate pairs exceed cap %s — analyzing first %s only",
                    len(ai_pairs), MAX_AI_PAIRS, MAX_AI_PAIRS,
                )
                ai_pairs = ai_pairs[:MAX_AI_PAIRS]

            # Bound fan-out so we don't open dozens of Gemini calls at once.
            sem = asyncio.Semaphore(5)

            async def _analyze_pair(t1, t2):
                async with sem:
                    m1 = await ThreadMessageRepository.list_by_thread(t1['id'], limit=50, offset=0)
                    m2 = await ThreadMessageRepository.list_by_thread(t2['id'], limit=50, offset=0)
                    return t1, t2, await ai_service.analyze_thread_similarity(t1, t2, m1, m2)

            results = await asyncio.gather(
                *[_analyze_pair(t1, t2) for t1, t2 in ai_pairs],
                return_exceptions=True,
            )
            for res in results:
                # BaseException, not Exception: gather(return_exceptions=True)
                # also hands back CancelledError, which would crash the unpack.
                if isinstance(res, BaseException):
                    logger.warning("thread similarity analysis failed for a pair: %s", res)
                    continue
                t1, t2, analysis = res
                if analysis and analysis.get('should_combine'):
                    suggestions.append(schemas.ThreadCombinationSuggestion(
                        thread1_id=_as_uuid(t1['id']),
                        thread2_id=_as_uuid(t2['id']),
                        thread1_title=t1.get('title', 'Untitled'),
                        thread2_title=t2.get('title', 'Untitled'),
                        should_combine=analysis['should_combine'],
                        similarity_score=analysis['similarity_score'],
                        reasoning=analysis['reasoning'],
                        factors=analysis['factors'],
                        recommendation=analysis['recommendation'],
                    ))

        # Sort by similarity score (highest first)
        suggestions.sort(key=lambda x: x.similarity_score, reverse=True)
        
        # Return top suggestions
        return suggestions[:limit]
        
    except Exception as e:
        logger.exception("Error suggesting thread combinations")
        raise HTTPException(status_code=500, detail=f"Failed to suggest combinations: {str(e)}")


@router.get("/threads/{thread_id}", response_model=schemas.ThreadWithMessages)
async def get_thread(
    thread_id: UUID,
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Get a thread with its messages. NEW: Only accessible if user email is in participants_emails."""
    # Get user email for access check
    user_email = None
    if current_user:
        user_email = current_user.get("email")
    
    if not user_email:
        raise HTTPException(status_code=403, detail="Authentication required to access threads")
    
    thread = await crud.get_thread_with_messages(db, thread_id, limit, offset)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # NEW VISIBILITY LOGIC: Allow access if visibility_scope='site' OR user_email in participants_emails
    visibility_scope = thread.get('visibility_scope', 'private')
    participants_emails = thread.get('participants_emails', [])
    user_email_lower = user_email.lower().strip()
    participant_emails_lower = [str(e).lower().strip() for e in participants_emails if e]
    
    # Check access: site-wide threads OR user is a participant
    has_access = (
        visibility_scope == 'site' or
        user_email_lower in participant_emails_lower
    )
    
    if not has_access:
        # Legacy fallback: check old thread_participants table
        from app.modules.communications.repositories import ThreadParticipantRepository
        participants = await ThreadParticipantRepository.list_by_thread(thread_id)
        participant_emails = [str(p.get("participant_email", "")).lower().strip() for p in participants if p.get("participant_email")]
        if user_email_lower not in participant_emails:
            raise HTTPException(status_code=403, detail="You don't have access to this thread")
    
    return thread


@router.get("/threads/{thread_id}/summary")
async def get_thread_summary(
    thread_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Get AI-generated summary of a thread."""
    # Get thread with messages
    thread = await crud.get_thread_with_messages(db, thread_id, limit=200, offset=0)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # NEW VISIBILITY LOGIC: Allow access if visibility_scope='site' OR user_email in participants_emails
    user_email = (current_user or {}).get("email")
    if not user_email:
        raise HTTPException(status_code=403, detail="Authentication required to access threads")
    
    visibility_scope = thread.get('visibility_scope', 'private')
    allowed_emails = [str(e).lower().strip() for e in (thread.get("participants_emails") or []) if e]
    user_email_lower = user_email.lower().strip()
    
    has_access = (
        visibility_scope == 'site' or
        user_email_lower in allowed_emails
    )
    
    if not has_access:
        # Legacy fallback: check old thread_participants table
        from app.modules.communications.repositories import ThreadParticipantRepository
        participants = await ThreadParticipantRepository.list_by_thread(thread_id)
        participant_emails = [str(p.get("participant_email", "")).lower().strip() for p in participants if p.get("participant_email")]
        if user_email_lower not in participant_emails:
            raise HTTPException(status_code=403, detail="You don't have access to this thread")
    
    # Check if AI service is available
    if not ai_service.is_available():
        api_key_status = "configured" if settings.gemini_api_key else "not configured"
        raise HTTPException(
            status_code=503, 
            detail=f"AI service is not available. GEMINI_API_KEY is {api_key_status}. Please check your .env file."
        )
    
    # Generate summary
    try:
        # Handle dict from MongoDB
        messages = thread.get('messages', []) if isinstance(thread, dict) else thread.messages
        summary = await ai_service.summarize_thread(thread, messages)
        
        if summary is None:
            raise HTTPException(status_code=500, detail="Failed to generate summary. Check backend logs for details.")
        
        return {"summary": summary, "thread_id": str(thread_id)}
    except Exception as e:
        logger.exception("Error in get_thread_summary")
        raise HTTPException(status_code=500, detail=f"Error generating summary: {str(e)}")


@router.post(
    "/threads/{thread_id}/participants",
    response_model=schemas.ThreadParticipantResponse,
    dependencies=[Depends(require_thread_member)],
)
async def add_participant(
    thread_id: UUID,
    participant: schemas.ThreadParticipantCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Add a participant to a thread."""
    # Check if thread exists
    thread = await crud.get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    db_participant = await crud.add_thread_participant(db, thread_id, participant)
    await best_effort_audit(
        db, user=(current_user or {}).get("user_id"),
        action="thread.participant_add", target_type="thread", target_id=str(thread_id),
        details={"participant_id": getattr(participant, "participant_id", None),
                 "email_masked": mask_email(getattr(participant, "participant_email", None))},
    )
    return db_participant


@router.post(
    "/threads/{thread_id}/participants/emails",
    response_model=schemas.ThreadResponse,
    dependencies=[Depends(require_thread_member)],
)
async def add_thread_participant_email(
    thread_id: UUID,
    email: str = Body(..., embed=True, description="Email address to add to participants_emails"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Add an email to thread's participants_emails list. Only thread creator or existing participant can modify."""
    user_email = (current_user or {}).get("email") if current_user else None
    
    try:
        updated_thread = await crud.add_thread_participant_email(
            db=db,
            thread_id=thread_id,
            email=email,
            user_email=user_email
        )
        await best_effort_audit(
            db, user=(current_user or {}).get("user_id"),
            action="thread.participant_add", target_type="thread", target_id=str(thread_id),
            details={"email_masked": mask_email(email)},
        )
        return updated_thread
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to add participant email: {str(e)}")


@router.delete(
    "/threads/{thread_id}/participants/emails/{email}",
    response_model=schemas.ThreadResponse,
    dependencies=[Depends(require_thread_member)],
)
async def remove_thread_participant_email(
    thread_id: UUID,
    email: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Remove an email from thread's participants_emails list. Only thread creator or existing participant can modify."""
    user_email = (current_user or {}).get("email") if current_user else None
    
    try:
        updated_thread = await crud.remove_thread_participant_email(
            db=db,
            thread_id=thread_id,
            email=email,
            user_email=user_email
        )
        await best_effort_audit(
            db, user=(current_user or {}).get("user_id"),
            action="thread.participant_remove", target_type="thread", target_id=str(thread_id),
            details={"email_masked": mask_email(email)},
        )
        return updated_thread
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to remove participant email: {str(e)}")


@router.post("/conversations/{conversation_id}/create-thread", response_model=schemas.ThreadResponse)
async def create_thread_from_conversation(
    conversation_id: UUID,
    request: schemas.CreateThreadFromConversationRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Create a thread from selected messages in a conversation."""
    try:
        thread = await crud.create_thread_from_conversation(
            db=db,
            conversation_id=conversation_id,
            title=request.title,
            description=request.description,
            thread_type=request.thread_type,
            message_ids=request.message_ids,
            created_by=request.created_by,
            creator_email=(current_user or {}).get("email"),
            related_study_id=request.related_study_id,
            visibility_scope=request.visibility_scope,
            participants_emails=request.participants_emails,
        )
        return thread
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create thread: {str(e)}")


@router.post("/threads/{thread_id}/messages", response_model=schemas.ThreadMessageResponse)
async def create_thread_message(
    thread_id: UUID,
    message: schemas.ThreadMessageCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Add a message to a thread (participants only)."""
    # Check if thread exists
    thread = await crud.get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    user_email = (current_user or {}).get("email")
    if not user_email:
        raise HTTPException(status_code=403, detail="Authentication required to post in threads")

    participants_emails = [str(e).lower().strip() for e in (thread.get("participants_emails") or []) if e]
    if user_email.lower() not in participants_emails:
        # Legacy fallback: support old thread_participants rows.
        from app.modules.communications.repositories import ThreadParticipantRepository
        participants = await ThreadParticipantRepository.list_by_thread(thread_id)
        participant_emails = [str(p.get("participant_email", "")).lower().strip() for p in participants if p.get("participant_email")]
        if user_email.lower() not in participant_emails:
            raise HTTPException(status_code=403, detail="You don't have access to this thread")
    
    db_message = await crud.create_thread_message(db, thread_id, message)

    # Reuse unified email worker pipeline for thread messages.
    try:
        from app.modules.communications.repositories import ThreadMessageRepository
        from app.modules.communications.services.message_delivery import schedule_outbound_message

        thread_msg_id = db_message.get("id") if isinstance(db_message, dict) else db_message.id
        mentioned_emails = db_message.get("mentioned_emails", []) if isinstance(db_message, dict) else []
        if mentioned_emails:
            await ThreadMessageRepository.update_fields(
                thread_msg_id,
                {"status": MessageStatus.QUEUED.value},
            )
            schedule_outbound_message(str(thread_msg_id), source_type="thread")
        else:
            await ThreadMessageRepository.update_fields(
                thread_msg_id,
                {
                    "status": MessageStatus.DELIVERED.value,
                    "delivered_at": datetime.now(timezone.utc),
                },
            )
    except Exception as e:
        logger.exception("Thread message email pipeline enqueue failed: %s", e)

    # --- AI tone/delta + thread summary (for threads) ---
    async def _thread_ai_postprocess():
        from app.modules.communications.repositories import (
            ThreadMessageRepository as _TMR,
            ThreadRepository as _TR,
        )
        # Load recent thread messages (latest first)
        history = await _TMR.list_by_thread(thread_id, limit=50, offset=0)
        if history:
            latest = history[0]
            older = history[1:]
            history_text = ai_service._format_thread_messages_for_summary(older[::-1])
            analysis = await ai_service.analyse_new_message(history_text, latest.get('body', ''))
            if analysis:
                await _TMR.update_fields(latest.get('id'), {
                    'ai_tone': analysis.get('tone'),
                    'ai_delta_summary': analysis.get('delta_summary'),
                })
            # Update thread‑level summary as well
            summary = await ai_service.summarize_thread(thread, history[::-1])
            if summary:
                from datetime import datetime, timezone
                await _TR.update(thread_id, {
                    'ai_summary': summary,
                    'ai_summary_updated_at': datetime.now(timezone.utc),
                })

    try:
        if ai_service.is_available():
            # THR-AI-INLINE fix: bound the inline AI work so a slow Gemini call
            # can't hang the send response (parity with the conversation
            # handler's timeouts).
            await asyncio.wait_for(_thread_ai_postprocess(), timeout=_THREAD_AI_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("Thread AI post-processing timed out for thread %s", thread_id)
    except Exception as e:
        logger.exception("AI post-processing failed for thread message: %s", e)

    # Publish to Redis for real-time updates
    try:
        from app.websocket_manager import manager
        msg_id = db_message.get("id") if isinstance(db_message, dict) else db_message.id
        msg_body = db_message.get("body") if isinstance(db_message, dict) else db_message.body
        msg_author_id = db_message.get("author_id") if isinstance(db_message, dict) else db_message.author_id
        msg_author_name = db_message.get("author_name") if isinstance(db_message, dict) else db_message.author_name
        msg_created_at = db_message.get("created_at") if isinstance(db_message, dict) else db_message.created_at
        _thread_event = {
            "type": "new_message",
            "thread_id": str(thread_id),
            "message": {
                "id": str(msg_id),
                "body": msg_body,
                "author_id": msg_author_id,
                "author_name": msg_author_name,
                "created_at": msg_created_at.isoformat() if hasattr(msg_created_at, "isoformat") else str(msg_created_at)
            }
        }
        # dispatch-no-timeout fix: cap the WS publish so a slow/hung Redis
        # publish can't block the send response.
        await asyncio.wait_for(
            manager.publish_thread_update(thread_id, _thread_event), timeout=_THREAD_WS_TIMEOUT
        )
    except asyncio.TimeoutError:
        logger.warning("Thread WS publish timed out for thread %s", thread_id)
    except Exception as e:
        logger.exception("Error publishing thread update: %s", e)

    await best_effort_audit(
        db, user=(current_user or {}).get("user_id"),
        action="thread.message_create", target_type="thread_message",
        target_id=str(db_message.get("id") if isinstance(db_message, dict) else db_message.id),
        details={"thread_id": str(thread_id)},
    )
    return db_message


@router.patch(
    "/threads/{thread_id}/status",
    dependencies=[Depends(require_thread_member)],
)
async def update_thread_status(
    thread_id: UUID,
    status: str = Query(..., pattern="^(open|in_progress|resolved|closed)$"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Update thread status."""
    thread = await crud.update_thread_status(db, thread_id, status)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    await best_effort_audit(
        db, user=(current_user or {}).get("user_id"),
        action="thread.status_change", target_type="thread", target_id=str(thread_id),
        details={"new_status": status},
    )
    return {"status": "updated", "thread_id": str(thread_id), "new_status": status}


@router.post(
    "/threads/{thread_id}/file-in-tmf",
    dependencies=[Depends(require_thread_member)],
)
async def file_thread_in_tmf(
    thread_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Mark a thread for TMF filing.
    This is a placeholder implementation that:
    - Updates the thread with tmf_filed = True
    - Creates a system message in the thread
    - Logs the action

    NOTE (UI removed): the "File in TMF" button was removed from the thread UI
    because this endpoint does NOT perform a real TMF filing — surfacing a
    compliance action it doesn't perform is misleading on a regulated system.
    This route + send_thread_to_tmf are intentionally left intact (dormant) so
    the real TMF integration can wire to them later; re-add the UI control only
    once actual filing is implemented.

    Future implementation will integrate with actual TMF system.
    """
    # Check if thread exists
    thread = await crud.get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    # Check if already filed
    thread_dict = thread if isinstance(thread, dict) else thread.__dict__
    if thread_dict.get('tmf_filed'):
        raise HTTPException(status_code=400, detail="Thread is already marked for TMF filing")
    
    # Call the TMF service
    from app.integrations.tmf_service import send_thread_to_tmf
    success = await send_thread_to_tmf(thread_id)
    
    if not success:
        raise HTTPException(status_code=500, detail="Failed to mark thread for TMF filing")
    
    # Refresh thread to get updated data
    updated_thread = await crud.get_thread(db, thread_id)

    await best_effort_audit(
        db, user=(current_user or {}).get("user_id"),
        action="thread.tmf_file", target_type="thread", target_id=str(thread_id),
    )
    return {
        "status": "success",
        "message": "Thread marked for TMF filing",
        "thread_id": str(thread_id),
        "tmf_filed": True,
        "tmf_filed_at": updated_thread.get('tmf_filed_at') if isinstance(updated_thread, dict) else getattr(updated_thread, 'tmf_filed_at', None)
    }


# Access Control Endpoints
@router.patch(
    "/conversations/{conversation_id}/access",
    response_model=schemas.ConversationResponse,
    dependencies=[Depends(require_conversation_admin)],
)
async def update_conversation_access(
    conversation_id: UUID,
    request: schemas.UpdateConversationAccessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update conversation access settings. All authenticated users can update for now."""
    current_user_id = current_user["user_id"]
    # For now, allow all authenticated users to update access settings
    
    conv = await crud.update_conversation_access(
        db=db,
        conversation_id=conversation_id,
        is_restricted=request.is_restricted,
        is_confidential=request.is_confidential,
        privileged_users=request.privileged_users
    )
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@router.patch("/conversations/{conversation_id}/state", response_model=schemas.ConversationResponse)
async def update_conversation_state_endpoint(
    conversation_id: UUID,
    request: schemas.ConversationStateUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Patch operational state (status / owner / due / priority / snooze).
    Only fields explicitly present in the request body are written; absent
    keys are not touched. Authentication required."""
    # Visibility check — must have access to the conversation to mutate it.
    existing = await crud.get_conversation(db, conversation_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Conversation not found")
    user_email = current_user.get("email")
    if not await crud.check_user_can_access_conversation_by_role(
        db, current_user["user_id"], existing, user_email=user_email
    ):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    patch = request.model_dump(exclude_unset=True)
    try:
        updated = await crud.update_conversation_state(db, conversation_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not updated:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return updated


@router.post(
    "/conversations/{conversation_id}/grant-access",
    response_model=schemas.ConversationAccessResponse,
    dependencies=[Depends(require_conversation_admin)],
)
async def grant_access(
    conversation_id: UUID,
    request: schemas.GrantAccessRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Grant access to a conversation for a user. All authenticated users can grant access for now."""
    current_user_id = current_user["user_id"]
    # For now, allow all authenticated users to grant access
    
    access = schemas.ConversationAccessCreate(
        user_id=request.user_id,
        access_type=request.access_type,
        granted_by=current_user_id
    )
    return await crud.grant_conversation_access(db, conversation_id, access)


@router.delete(
    "/conversations/{conversation_id}/revoke-access/{user_id}",
    dependencies=[Depends(require_conversation_admin)],
)
async def revoke_access(
    conversation_id: UUID,
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Revoke access to a conversation for a user. All authenticated users can revoke access for now."""
    current_user_id = current_user["user_id"]
    # For now, allow all authenticated users to revoke access
    
    success = await crud.revoke_conversation_access(db, conversation_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Access grant not found")
    return {"status": "revoked", "conversation_id": str(conversation_id), "user_id": user_id}


@router.get(
    "/conversations/{conversation_id}/access",
    response_model=List[schemas.ConversationAccessResponse],
    dependencies=[Depends(require_conversation_member)],
)
async def get_access_list(
    conversation_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get list of all users with access to a conversation."""
    # For now, all authenticated users have equal access - no restrictions
    return await crud.get_conversation_access_list(db, conversation_id)


@router.get(
    "/conversations/{conversation_id}/check-access",
    dependencies=[Depends(require_conversation_member)],
)
async def check_access(
    conversation_id: UUID,
    user_id: str = Query(..., description="User ID to check"),
    db: AsyncSession = Depends(get_db)
):
    """Check if a user has access to a conversation."""
    access_type = await crud.check_user_access(db, conversation_id, user_id)
    return {
        "has_access": access_type is not None,
        "access_type": access_type
    }


# Authentication endpoints
@router.post("/conversations/{conversation_id}/attachments", response_model=schemas.AttachmentResponse)
async def upload_conversation_attachment(
    conversation_id: UUID,
    file: UploadFile = File(...),
    message_id: Optional[UUID] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Upload a file attachment to a conversation."""
    # Verify conversation exists
    conv = await crud.get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required to access conversations")
    user_email = (current_user or {}).get("email")
    if not await crud.check_user_can_access_conversation_by_role(db, user_id, conv, user_email=user_email):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    # Reject obviously-bad uploads (extension + declared mime) before disk I/O.
    validate_upload_metadata(file)

    # Create upload directory if it doesn't exist
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename. safe_extension returns the whitelist's own
    # literal (already enforced by validate_upload_metadata above), so no
    # user-controlled bytes reach the path (CWE-22).
    file_ext = safe_extension(file.filename)
    file_id = uuid.uuid4()
    file_name = f"{file_id}{file_ext}"
    file_path = upload_dir / file_name

    # Save file: stream with hard size cap, then sniff magic bytes.
    try:
        file_size = stream_to_disk_safely(file, file_path)
        verify_magic_bytes(file_path, file.content_type or "", file.filename)

        checksum = None
        try:
            async with aiofiles.open(file_path, "rb") as f:
                # Non-cryptographic integrity checksum; md5 kept so values stay
                # comparable with checksums already stored on old attachments.
                file_hash = hashlib.md5(usedforsecurity=False)
                while True:
                    chunk = await f.read(4096)
                    if not chunk:
                        break
                    file_hash.update(chunk)
                checksum = file_hash.hexdigest()
        except Exception:
            pass  # Checksum is optional

        # Create attachment record
        attachment = await crud.create_attachment(
            db=db,
            conversation_id=conversation_id,
            file_path=str(file_path),
            content_type=file.content_type or "application/octet-stream",
            size=file_size,
            message_id=message_id,
            checksum=checksum
        )

        # Add file_name to response
        response_data = schemas.AttachmentResponse.model_validate(attachment)
        response_data.file_name = file.filename
        await best_effort_audit(
            db, user=(current_user or {}).get("user_id"),
            action="attachment.upload", target_type="attachment",
            target_id=str(attachment.get("id") if isinstance(attachment, dict) else getattr(attachment, "id", "")),
            details={"conversation_id": str(conversation_id), "content_type": file.content_type, "size": file_size},
        )
        return response_data

    except HTTPException:
        # Cleanup already handled by stream_to_disk_safely / verify_magic_bytes.
        raise
    except Exception as e:
        # Clean up file if database operation fails
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.post(
    "/threads/{thread_id}/attachments",
    response_model=schemas.ThreadAttachmentResponse,
    dependencies=[Depends(require_thread_member)],
)
async def upload_thread_attachment(
    thread_id: UUID,
    file: UploadFile = File(...),
    thread_message_id: Optional[UUID] = Form(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Upload a file attachment to a thread."""
    # Verify thread exists
    thread = await crud.get_thread(db, thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Reject obviously-bad uploads (extension + declared mime) before disk I/O.
    validate_upload_metadata(file)

    # Create upload directory if it doesn't exist
    upload_dir = Path(settings.upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename. safe_extension returns the whitelist's own
    # literal (already enforced by validate_upload_metadata above), so no
    # user-controlled bytes reach the path (CWE-22).
    file_ext = safe_extension(file.filename)
    file_id = uuid.uuid4()
    file_name = f"{file_id}{file_ext}"
    file_path = upload_dir / file_name

    # Save file: stream with hard size cap, then sniff magic bytes.
    try:
        file_size = stream_to_disk_safely(file, file_path)
        verify_magic_bytes(file_path, file.content_type or "", file.filename)

        checksum = None
        try:
            async with aiofiles.open(file_path, "rb") as f:
                # Non-cryptographic integrity checksum; md5 kept so values stay
                # comparable with checksums already stored on old attachments.
                file_hash = hashlib.md5(usedforsecurity=False)
                while True:
                    chunk = await f.read(4096)
                    if not chunk:
                        break
                    file_hash.update(chunk)
                checksum = file_hash.hexdigest()
        except Exception:
            pass  # Checksum is optional

        # Create attachment record (linked to conversation)
        # crud.get_thread / crud.create_attachment return Mongo dicts — use .get(),
        # not attribute access (the 'dict' object has no attribute footgun).
        thread_conv_id = thread.get('conversation_id') if isinstance(thread, dict) else getattr(thread, 'conversation_id', None)
        attachment = await crud.create_attachment(
            db=db,
            conversation_id=thread_conv_id,
            file_path=str(file_path),
            content_type=file.content_type or "application/octet-stream",
            size=file_size,
            message_id=None,  # Thread attachments are not linked to messages
            checksum=checksum
        )

        # Link attachment to thread
        new_attachment_id = attachment.get('id') if isinstance(attachment, dict) else getattr(attachment, 'id', None)
        thread_attachment = await crud.create_thread_attachment(
            db=db,
            thread_id=thread_id,
            attachment_id=new_attachment_id,
            thread_message_id=thread_message_id
        )
        
        # `thread_attachment` and `attachment` are Mongo dicts (the crud layer is
        # Mongo-backed). Build the response straight from them — do NOT db.refresh
        # or reload via the Postgres `ThreadAttachment` ORM: those rows don't exist
        # in Postgres, and `dict.id` / `db.refresh(dict)` was the
        # 'dict' object has no attribute 'id' crash.
        response_data = schemas.ThreadAttachmentResponse.model_validate(thread_attachment)
        if attachment:
            att_resp = schemas.AttachmentResponse.model_validate(attachment)
            att_resp.file_name = file.filename
            response_data.attachment = att_resp
        await best_effort_audit(
            db, user=(current_user or {}).get("user_id"),
            action="attachment.upload", target_type="attachment",
            target_id=str(new_attachment_id or ""),
            details={"thread_id": str(thread_id), "content_type": file.content_type, "size": file_size},
        )
        return response_data

    except HTTPException:
        # Cleanup already handled by stream_to_disk_safely / verify_magic_bytes.
        raise
    except Exception as e:
        # Clean up file if database operation fails
        if file_path.exists():
            file_path.unlink()
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")


@router.get("/conversations/{conversation_id}/attachments", response_model=List[schemas.AttachmentResponse])
async def list_conversation_attachments(
    conversation_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """List all attachments for a conversation."""
    conv = await crud.get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required to access conversations")
    user_email = (current_user or {}).get("email")
    if not await crud.check_user_can_access_conversation_by_role(db, user_id, conv, user_email=user_email):
        raise HTTPException(status_code=403, detail="You don't have access to this conversation")

    attachments = await crud.list_conversation_attachments(db, conversation_id)
    # Add file_name to each attachment
    result: List[schemas.AttachmentResponse] = []
    for att in attachments:
        # att may be a SQLAlchemy object or a dict from Mongo‑backed CRUD
        att_resp = schemas.AttachmentResponse.model_validate(att)
        file_path = att_resp.file_path
        att_resp.file_name = Path(file_path).name if file_path else None
        result.append(att_resp)
    return result


@router.get(
    "/threads/{thread_id}/attachments",
    response_model=List[schemas.ThreadAttachmentResponse],
    dependencies=[Depends(require_thread_member)],
)
async def list_thread_attachments(
    thread_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """List all attachments for a thread."""
    thread_attachments = await crud.list_thread_attachments(db, thread_id)
    # `thread_attachments` are Mongo dicts. Hydrate each linked attachment via
    # the Mongo crud (crud.get_attachment) — do NOT db.refresh / reload via the
    # Postgres ORM (the rows aren't there; `dict.id` was the crash).
    result = []
    for ta in thread_attachments:
        ta_resp = schemas.ThreadAttachmentResponse.model_validate(ta)
        att_id = ta.get('attachment_id') if isinstance(ta, dict) else getattr(ta, 'attachment_id', None)
        if att_id:
            att = await crud.get_attachment(db, att_id)
            if att:
                att_resp = schemas.AttachmentResponse.model_validate(att)
                file_path = att.get('file_path') if isinstance(att, dict) else getattr(att, 'file_path', None)
                att_resp.file_name = Path(file_path).name if file_path else None
                ta_resp.attachment = att_resp
        result.append(ta_resp)
    return result


@router.post("/threads/combine", response_model=schemas.ThreadResponse)
async def combine_threads(
    request: schemas.CombineThreadsRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Combine two threads into one. Merges participants, messages, and attachments.
    The target_thread_id is the thread that will be kept.
    """
    # Write-guard: the caller must be able to access BOTH threads being merged
    # (ids arrive in the body, so this can't use the path-param guard). Placed
    # before the try/except so the 403/404 isn't rewrapped as a 500.
    guard_user_id = (current_user or {}).get("user_id")
    if not guard_user_id:
        raise HTTPException(status_code=403, detail="Authentication required to combine threads")
    guard_user_email = (current_user or {}).get("email")
    for _tid in (request.thread1_id, request.thread2_id):
        _t = await crud.get_thread(db, _tid)
        if not _t:
            raise HTTPException(status_code=404, detail="Thread not found")
        if not await crud.check_user_can_access_thread(
            db, guard_user_id, _t, user_email=guard_user_email
        ):
            raise HTTPException(status_code=403, detail="You don't have access to this thread")

    try:
        combined_thread = await crud.combine_threads(
            db=db,
            thread1_id=request.thread1_id,
            thread2_id=request.thread2_id,
            target_thread_id=request.target_thread_id
        )
        
        if not combined_thread:
            raise HTTPException(status_code=404, detail="Failed to combine threads")

        await best_effort_audit(
            db, user=(current_user or {}).get("user_id"),
            action="thread.combine", target_type="thread", target_id=str(request.target_thread_id),
            details={"thread1_id": str(request.thread1_id), "thread2_id": str(request.thread2_id)},
        )
        return combined_thread
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Error combining threads")
        raise HTTPException(status_code=500, detail=f"Failed to combine threads: {str(e)}")


@router.get("/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """Download an attachment file."""
    attachment = await crud.get_attachment(db, attachment_id)
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    # crud.get_attachment returns a Mongo dict — use .get(), not attribute access
    # (the 'dict' object has no attribute footgun).
    attachment_conv_id = attachment.get('conversation_id') if isinstance(attachment, dict) else getattr(attachment, 'conversation_id', None)
    attachment_file_path = attachment.get('file_path') if isinstance(attachment, dict) else getattr(attachment, 'file_path', None)

    conv = await crud.get_conversation(db, attachment_conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    user_id = (current_user or {}).get("user_id")
    if not user_id:
        raise HTTPException(status_code=403, detail="Authentication required to access attachments")
    user_email = (current_user or {}).get("email")
    if not await crud.check_user_can_access_conversation_by_role(db, user_id, conv, user_email=user_email):
        raise HTTPException(status_code=403, detail="You don't have access to this attachment")

    file_path = Path(attachment_file_path)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on server")

    # Get original filename if available, otherwise use file path name
    file_name = Path(attachment_file_path).name

    await best_effort_audit(
        db, user=user_id,
        action="attachment.download", target_type="attachment", target_id=str(attachment_id),
        details={"conversation_id": str(attachment_conv_id)},
    )
    attachment_content_type = attachment.get('content_type') if isinstance(attachment, dict) else getattr(attachment, 'content_type', None)
    return FileResponse(
        path=str(file_path),
        filename=file_name,
        media_type=attachment_content_type or "application/octet-stream",
    )


# User Profile Endpoints

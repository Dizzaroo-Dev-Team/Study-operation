from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from typing import Optional, List, Dict, Any, Tuple
from uuid import UUID
from app.models import (
    Conversation,
    Message,
    AuditLog,
    MessageDirection,
    MessageStatus,
    MessageChannel,
    Thread,
    ThreadParticipant,
    ThreadMessage,
    ThreadAttachment,
    User,
    ConversationAccess,
    ConversationAccessLevel,
    UserRole,
    AccessType,
    Attachment,
    RDStudy,
    IISStudy,
    Event,
    UserProfile,
    ChatMessage,
    ChatDocument,
    Study,
    Site,
    SiteStatus,
    SiteStatusHistory,
    PrimarySiteStatus,
    UserRoleAssignment,
    StudySite,
)
from app.schemas import (
    ConversationCreate, MessageCreate, ThreadCreate, ThreadParticipantCreate, ThreadMessageCreate,
    UserCreate, ConversationAccessCreate,
    RDStudyCreate, IISStudyCreate, EventCreate, UserProfileCreate,
    ChatMessageCreate
)
from app.modules.communications.repositories import (
    ConversationRepository,
    MessageRepository,
    AttachmentRepository,
    ThreadRepository,
    ThreadParticipantRepository,
    ThreadMessageRepository,
    ThreadAttachmentRepository,
    ThreadFromConversationRepository,
)
from app.modules.auth_profiles.repositories import (
    ConversationAccessRepository,
    UserRoleAssignmentRepository,
)
from app.modules.sites.repositories import (
    StudyRepository,
    SiteRepository,
)
from datetime import datetime, timezone
import uuid
import shortuuid
import logging

logger = logging.getLogger(__name__)


async def _resolve_one_friendly_id(db: AsyncSession, model, friendly_attr: str, value_in):
    """Resolve one UUID-or-friendly identifier to the friendly external code
    (`model.<friendly_attr>`). Falls back to the input value when no row matches
    or the matched row has no friendly code."""
    if not value_in:
        return value_in
    row = None
    try:
        uid = UUID(str(value_in))
        row = (await db.execute(select(model).where(model.id == uid))).scalar_one_or_none()
    except (ValueError, TypeError):
        row = None
    if row is None:
        row = (
            await db.execute(select(model).where(getattr(model, friendly_attr) == value_in))
        ).scalar_one_or_none()
    friendly = getattr(row, friendly_attr, None) if row is not None else None
    return friendly or value_in


async def _resolve_friendly_ids(
    db: AsyncSession,
    study_id_in: Optional[str],
    site_id_in: Optional[str],
) -> tuple:
    """Resolve UUID-or-friendly study/site identifiers to their friendly
    external codes (``Study.study_id`` / ``Site.site_id``). Used so the email
    alias contains ``studyx-site009`` rather than 32 hex chars of a UUID PK.

    Falls back to the input value if no row matches.
    """
    from app.models import Study as _Study, Site as _Site

    friendly_study = await _resolve_one_friendly_id(db, _Study, "study_id", study_id_in)
    friendly_site = await _resolve_one_friendly_id(db, _Site, "site_id", site_id_in)
    return friendly_study, friendly_site


def _normalize_conv_participant_emails(conv_dict: Dict[str, Any]) -> None:
    """Handle participant_emails: convert participant_email to array if needed."""
    if conv_dict.get('participant_emails'):
        # participant_emails provided - use it
        participant_emails = [email.strip() for email in conv_dict['participant_emails'] if email and email.strip()]
        conv_dict['participant_emails'] = participant_emails
        # Set first email as participant_email for backward compatibility
        if participant_emails and not conv_dict.get('participant_email'):
            conv_dict['participant_email'] = participant_emails[0]
    elif conv_dict.get('participant_email'):
        # Only participant_email provided - convert to participant_emails array
        conv_dict['participant_emails'] = [conv_dict['participant_email']]
    else:
        # Neither provided - set empty array
        conv_dict['participant_emails'] = []


def _normalize_conv_is_pinned(conv_dict: Dict[str, Any]) -> None:
    """CRITICAL: Normalize is_pinned - only Public Notice Board should be pinned.
    Default to 'false' unless explicitly set to True (only for system-created notice boards)."""
    if 'is_pinned' not in conv_dict or conv_dict['is_pinned'] is None:
        conv_dict['is_pinned'] = 'false'
        return
    # Convert boolean/string to proper string value
    is_pinned_val = conv_dict['is_pinned']
    if isinstance(is_pinned_val, bool):
        conv_dict['is_pinned'] = 'true' if is_pinned_val else 'false'
    elif isinstance(is_pinned_val, str):
        conv_dict['is_pinned'] = 'true' if is_pinned_val.lower().strip() == 'true' else 'false'
    else:
        conv_dict['is_pinned'] = 'false'


def _apply_conv_defaults(conv_dict: Dict[str, Any]) -> None:
    """Fill id / tracker_code / flag-string / access_level / conversation_type defaults."""
    # Generate UUID if not provided
    if 'id' not in conv_dict:
        conv_dict['id'] = uuid.uuid4()
    # Generate tracker_code if not provided
    if 'tracker_code' not in conv_dict or not conv_dict.get('tracker_code'):
        conv_dict['tracker_code'] = f"DZ-{shortuuid.uuid()[:8].upper()}"
    _normalize_conv_is_pinned(conv_dict)
    # Convert boolean to string for is_restricted and is_confidential
    if 'is_restricted' in conv_dict and conv_dict['is_restricted'] is not None:
        conv_dict['is_restricted'] = 'true' if conv_dict['is_restricted'] else 'false'
    if 'is_confidential' in conv_dict and conv_dict['is_confidential'] is not None:
        conv_dict['is_confidential'] = 'true' if conv_dict['is_confidential'] else 'false'
    # Set default access_level
    if 'access_level' not in conv_dict:
        conv_dict['access_level'] = 'PUBLIC'
    # Default conversation_type to 'thread' — regular user-created conversations
    # are threads. 'notice_board' is reserved for the system-pinned per-site
    # board (created via `ensure_public_notice_board` →
    # `ConversationRepository.find_or_create_pinned_notice_board`). Defaulting
    # to 'notice_board' here previously caused every user-created conversation
    # to collide with the `notice_board_unique_per_site_study` index after
    # Hunt 4's race-fix landed.
    if 'conversation_type' not in conv_dict or not conv_dict.get('conversation_type'):
        conv_dict['conversation_type'] = 'thread'


async def _assign_conv_alias_fields(db: AsyncSession, conv_dict: Dict[str, Any]) -> None:
    """Resolve friendly study/site identifiers so the outbound email alias
    reads as `studyx-site009-c1` rather than 32-hex of a UUID PK, and assign
    the per-(study,site) sequential conversation number that drives the short,
    human-readable alias suffix `c1`, `c2`, …"""
    friendly_study, friendly_site = await _resolve_friendly_ids(
        db, conv_dict.get("study_id"), conv_dict.get("site_id")
    )
    if friendly_study:
        conv_dict["study_external_id"] = friendly_study
    if friendly_site:
        conv_dict["site_external_id"] = friendly_site

    if friendly_study and friendly_site:
        from app.db.mongo import next_sequence
        from app.utils.email_alias import _norm
        try:
            conv_dict["conversation_number"] = await next_sequence(
                f"conv:{_norm(friendly_study)}:{_norm(friendly_site)}"
            )
        except Exception as e:
            logger.warning("[MONGO] next_sequence failed: %s; alias will fall back to legacy hex form", e)


async def create_conversation(db: AsyncSession, conv: ConversationCreate) -> Dict[str, Any]:
    """Create a conversation in MongoDB. Returns dict for compatibility."""
    conv_dict = conv.dict()
    # PII-safe (LOG-1): log scope + counts, never the raw payload / participant emails.
    logger.debug(
        "[MONGO] Creating conversation study=%s site=%s type=%s participants=%d",
        conv_dict.get("study_id"), conv_dict.get("site_id"),
        conv_dict.get("conversation_type"),
        len(conv_dict.get("participant_emails") or []),
    )

    _normalize_conv_participant_emails(conv_dict)
    _apply_conv_defaults(conv_dict)
    await _assign_conv_alias_fields(db, conv_dict)

    db_conv = await ConversationRepository.create(conv_dict)
    # PII-safe: site/tracker + participant COUNT only (no raw emails / payload).
    logger.debug(
        "[MONGO] Created conversation id=%s site=%s tracker=%s participants=%d",
        db_conv.get("id"), db_conv.get("site_id"), db_conv.get("tracker_code"),
        len(db_conv.get("participant_emails") or []),
    )
    return db_conv


async def get_conversation(db: AsyncSession, conv_id: UUID) -> Optional[Dict[str, Any]]:
    """Get conversation from MongoDB. Returns dict for compatibility."""
    return await ConversationRepository.get_by_id(conv_id)


async def delete_conversation(db: AsyncSession, conv_id: UUID) -> bool:
    """Delete a conversation and its messages/attachments. Notice boards cannot be deleted."""
    conv = await ConversationRepository.get_by_id(conv_id)
    if not conv:
        return False
    if str(conv.get("conversation_type") or "").strip().lower() == "notice_board":
        raise ValueError("Notice board conversations cannot be deleted")

    await AttachmentRepository.delete_by_conversation(conv_id)
    await MessageRepository.delete_by_conversation(conv_id)
    deleted = await ConversationRepository.delete(conv_id)

    # Best-effort cleanup of Postgres access grants for this conversation.
    try:
        result = await db.execute(
            select(ConversationAccess).where(ConversationAccess.conversation_id == conv_id)
        )
        for access in result.scalars().all():
            await db.delete(access)
        await db.commit()
    except Exception:
        await db.rollback()

    return deleted


async def list_conversations(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    study_id: Optional[str] = None,
    site_id: Optional[str] = None,
    channel: Optional[MessageChannel] = None,
    user_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List conversations from MongoDB with optional filters. 
    
    NEW BEHAVIOR: Conversations are PUBLIC - all users with site access can see all conversation messages.
    No filtering by user - conversations act as a public notice board.
    """
    # Get conversations from MongoDB - no user filtering for public notice board
    conversations = await ConversationRepository.list(
        limit=limit,
        offset=offset,
        study_id=study_id,
        site_id=site_id,
        channel=channel,
        user_id=None  # Don't filter by user - conversations are public
    )
    
    return conversations


async def _stats_accessible_conversation_ids(
    db: AsyncSession, conversations: List[Dict[str, Any]], user_id: Optional[str]
) -> list:
    """Filter by access using Postgres ConversationAccess if user_id provided."""
    accessible_conversation_ids = []
    for conv in conversations:
        conv_id = conv.get('id')
        if not conv_id:
            continue

        # Public conversations - already filtered by repository
        if conv.get('is_confidential') != 'true' and (not conv.get('access_level') or conv.get('access_level') == 'PUBLIC' or conv.get('access_level') == 'public'):
            accessible_conversation_ids.append(conv_id)
        elif user_id:
            # Check Postgres for explicit access grants
            access_type = await check_user_access(db, conv_id, user_id)
            if access_type is not None:
                accessible_conversation_ids.append(conv_id)
    return accessible_conversation_ids


async def _message_stats_group_by(messages_collection, conv_id_strs: List[str], field: str) -> dict:
    """MongoDB aggregation: message counts grouped by `field` for the given conversations."""
    pipeline = [
        {"$match": {"conversation_id": {"$in": conv_id_strs}}},
        {"$group": {"_id": f"${field}", "count": {"$sum": 1}}}
    ]
    stats = {}
    async for doc in messages_collection.aggregate(pipeline):
        stats[doc["_id"]] = doc["count"]
    return stats


async def get_conversation_stats(db: AsyncSession, user_id: Optional[str] = None) -> dict:
    """Get conversation statistics filtered by user access. Uses MongoDB aggregation."""
    from app.db.mongo import get_mongo_db

    # Get accessible conversations from MongoDB
    conversations = await ConversationRepository.list(limit=1000, offset=0, user_id=user_id)
    accessible_conversation_ids = await _stats_accessible_conversation_ids(db, conversations, user_id)
    total_conversations = len(accessible_conversation_ids)

    # Use MongoDB aggregation to get message statistics
    mongo_db = await get_mongo_db()
    messages_collection = mongo_db[MessageRepository.COLLECTION_NAME]

    if accessible_conversation_ids:
        # Convert UUIDs to strings for MongoDB query
        conv_id_strs = [str(cid) for cid in accessible_conversation_ids]
        total_messages = await messages_collection.count_documents({"conversation_id": {"$in": conv_id_strs}})
        channel_stats = await _message_stats_group_by(messages_collection, conv_id_strs, "channel")
        status_stats = await _message_stats_group_by(messages_collection, conv_id_strs, "status")
    else:
        total_messages = 0
        channel_stats = {}
        status_stats = {}

    return {
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "by_channel": channel_stats,
        "by_status": status_stats
    }


async def get_conversation_with_messages(
    db: AsyncSession, 
    conv_id: UUID, 
    limit: int = 50, 
    offset: int = 0
) -> Optional[Dict[str, Any]]:
    """Get conversation with messages from MongoDB. Returns dict for compatibility."""
    conv = await ConversationRepository.get_by_id(conv_id)
    if conv:
        # Load messages from MongoDB
        messages = await MessageRepository.list_by_conversation(conv_id, limit, offset)
        # Public Notice Board should be chronological (oldest first).
        if conv.get("conversation_type") == "notice_board":
            messages = sorted(
                messages,
                key=lambda m: m.get("created_at") or datetime.min,
                reverse=False,
            )
        conv['messages'] = messages
    return conv


async def create_message(
    db: AsyncSession, 
    conv_id: UUID, 
    msg: MessageCreate, 
    direction: MessageDirection = MessageDirection.OUTBOUND,
    author_id: Optional[str] = None,
    author_name: Optional[str] = None,
    origin: Optional[str] = "user",
    event_type: Optional[str] = None,
    is_activity_event: Optional[bool] = False
) -> Dict[str, Any]:
    """Create a message in MongoDB. Returns dict for compatibility."""
    # Inbound messages should be DELIVERED, outbound should be QUEUED
    initial_status = MessageStatus.DELIVERED if direction == MessageDirection.INBOUND else MessageStatus.QUEUED

    # Extract mentioned emails from message body
    from app.utils.email_mentions import extract_mention_emails
    mentioned_emails = extract_mention_emails(msg.body)
    
    # Prepare metadata - include origin, event_type, and is_activity_event in metadata for backward compatibility
    message_metadata = msg.metadata or {}
    if origin:
        message_metadata['origin'] = origin
    if event_type:
        message_metadata['event_type'] = event_type
    if is_activity_event:
        message_metadata['is_activity_event'] = is_activity_event
    
    msg_data = {
        'id': uuid.uuid4(),
        'conversation_id': conv_id,
        'direction': direction,
        'channel': msg.channel,
        'body': msg.body,
        'status': initial_status,
        'message_metadata': message_metadata,
        'author_id': author_id,
        'author_name': author_name,
        'mentioned_emails': mentioned_emails,  # Store extracted email mentions
        'origin': origin or "user",  # Store as top-level field for easy access
        'event_type': event_type,  # Store as top-level field for easy access
        'is_activity_event': is_activity_event if is_activity_event is not None else False,  # Store as top-level field
        'is_decision': False  # Pinned-decision flag; toggled later via the decision endpoint
    }
    # Set delivered_at for inbound messages
    if direction == MessageDirection.INBOUND:
        msg_data['delivered_at'] = datetime.now(timezone.utc)
    
    db_msg = await MessageRepository.create(msg_data)
    return db_msg


async def get_message(db: AsyncSession, msg_id: UUID) -> Optional[Dict[str, Any]]:
    """Get message from MongoDB. Returns dict for compatibility."""
    return await MessageRepository.get_by_id(msg_id)


async def set_message_decision(
    db: AsyncSession, msg_id: UUID, is_decision: bool
) -> Optional[Dict[str, Any]]:
    """Pin / unpin a message as a 'decision of record'. Returns the updated dict."""
    return await MessageRepository.update_fields(
        msg_id,
        {"is_decision": bool(is_decision), "updated_at": datetime.now(timezone.utc)},
    )


async def update_message_status(
    db: AsyncSession,
    msg_id: UUID,
    status: MessageStatus,
    provider_message_id: Optional[str] = None,
    sent_at: Optional[datetime] = None,
    delivered_at: Optional[datetime] = None
) -> Optional[Dict[str, Any]]:
    """Update message status in MongoDB. Returns dict for compatibility."""
    return await MessageRepository.update_status(
        msg_id, status, provider_message_id, sent_at, delivered_at
    )


async def create_audit_log(
    db: AsyncSession,
    user: Optional[str],
    action: str,
    target_type: str,
    target_id: str,
    details: Optional[dict] = None
):
    from app.audit_context import apply_provenance

    log = AuditLog(
        user=user,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=apply_provenance(details) or {}
    )
    db.add(log)
    await db.commit()


# Thread CRUD operations
def _conv_field(conv: Any, field: str) -> Any:
    """Read a field from a conversation that may be a MongoDB dict or an ORM object."""
    return conv.get(field) if isinstance(conv, dict) else getattr(conv, field, None)


async def _thread_conversation_context(db: AsyncSession, conversation_id) -> tuple:
    """Verify the linked conversation exists and pull the fields a new thread
    inherits from it. Returns (conv, study_id, site_id, participant_email)."""
    conv = await get_conversation(db, conversation_id)
    if not conv:
        raise ValueError(f"Conversation {conversation_id} not found")

    # Handle dict from MongoDB
    conv_study_id = conv.get('study_id') if isinstance(conv, dict) else conv.study_id
    conv_site_id = _conv_field(conv, 'site_id')
    conv_email = _conv_field(conv, 'participant_email')
    return conv, conv_study_id, conv_site_id, conv_email


def _extract_thread_participants_emails(thread: ThreadCreate) -> List[str]:
    """Extract participants_emails from the thread create request (normalized,
    de-duplicated, merged with emails on the participants list)."""
    participants_emails = []
    if hasattr(thread, 'participants_emails') and thread.participants_emails:
        participants_emails = [email.strip().lower() for email in thread.participants_emails if email and email.strip()]
        participants_emails = list(dict.fromkeys(participants_emails))
    # Also extract from participants list if provided
    if thread.participants:
        for participant in thread.participants:
            if participant.participant_email and participant.participant_email.strip():
                normalized_email = participant.participant_email.strip().lower()
                if normalized_email not in participants_emails:
                    participants_emails.append(normalized_email)
    return participants_emails


async def _assign_thread_alias_fields(db: AsyncSession, thread_data: Dict[str, Any]) -> None:
    """Resolve friendly study/site identifiers + per-(study,site) thread number."""
    friendly_study, friendly_site = await _resolve_friendly_ids(
        db, thread_data.get('related_study_id'), thread_data.get('site_id')
    )
    if friendly_study:
        thread_data['study_external_id'] = friendly_study
    if friendly_site:
        thread_data['site_external_id'] = friendly_site
    if friendly_study and friendly_site:
        from app.db.mongo import next_sequence
        from app.utils.email_alias import _norm
        try:
            thread_data['thread_number'] = await next_sequence(
                f"thread:{_norm(friendly_study)}:{_norm(friendly_site)}"
            )
        except Exception as e:
            logger.warning("[MONGO] next_sequence(thread) failed: %s; alias will fall back to legacy hex form", e)


async def _add_initial_thread_participants(thread: ThreadCreate, thread_id, conv, conv_email) -> None:
    """Create ThreadParticipant rows for a new thread: the explicit participants
    if provided, otherwise the linked conversation's participant as default."""
    if thread.participants:
        for participant in thread.participants:
            participant_data = {
                'id': uuid.uuid4(),
                'thread_id': thread_id,
                'participant_id': participant.participant_id,
                'participant_name': participant.participant_name,
                'participant_email': participant.participant_email,
                'role': participant.role
            }
            await ThreadParticipantRepository.create(participant_data)
    elif conv_email:
        # If no participants specified and thread is linked to conversation, add conversation participant as default
        default_participant_data = {
            'id': uuid.uuid4(),
            'thread_id': thread_id,
            'participant_id': conv_email,
            'participant_name': None,
            'participant_email': conv_email,
            'role': 'participant'
        }
        await ThreadParticipantRepository.create(default_participant_data)


async def create_thread(db: AsyncSession, thread: ThreadCreate) -> Dict[str, Any]:
    """Create a thread in MongoDB. Threads can be created independently or linked to a conversation."""
    conv = None
    conv_study_id = None
    conv_site_id = None
    conv_email = None

    # Only verify conversation if provided
    if thread.conversation_id:
        conv, conv_study_id, conv_site_id, conv_email = await _thread_conversation_context(
            db, thread.conversation_id
        )

    participants_emails = _extract_thread_participants_emails(thread)

    # Validate visibility_scope
    visibility_scope = getattr(thread, 'visibility_scope', 'private')
    if visibility_scope not in ['private', 'site']:
        visibility_scope = 'private'  # Default to private if invalid

    thread_data = {
        'id': uuid.uuid4(),
        'conversation_id': thread.conversation_id,  # Can be None
        'title': thread.title,
        'description': thread.description,
        'thread_type': thread.thread_type,
        'related_patient_id': thread.related_patient_id,
        'related_study_id': thread.related_study_id or conv_study_id,
        'site_id': thread.site_id or conv_site_id,
        'priority': thread.priority,
        'created_by': thread.created_by,
        'status': 'open',
        'participants_emails': participants_emails,  # Store participant emails for access control
        'visibility_scope': visibility_scope,  # 'private' or 'site'
        'tmf_filed': False,
        'tmf_filed_at': None,
        'conversation_address': None,
        'agreement_type': thread.agreement_type if hasattr(thread, 'agreement_type') else None
    }

    await _assign_thread_alias_fields(db, thread_data)

    db_thread = await ThreadRepository.create(thread_data)

    # Create ThreadFromConversation link only if conversation_id is provided
    if thread.conversation_id:
        link_data: Dict[str, Any] = {
            'id': uuid.uuid4(),
            'thread_id': db_thread.get('id'),
            'conversation_id': thread.conversation_id,
            'source_message_ids': [],  # Empty for threads created independently
            'created_by': thread.created_by
        }
        await ThreadFromConversationRepository.create(link_data)

    # Add participants
    await _add_initial_thread_participants(thread, db_thread.get('id'), conv, conv_email)

    # Load participants for response
    participants = await ThreadParticipantRepository.list_by_thread(db_thread.get('id'))
    db_thread['participants'] = participants

    return db_thread


def _thread_merge_hidden(thread: Optional[Dict[str, Any]]) -> bool:
    """A thread mid-merge ('in_progress') or after a failed merge ('failed') is
    hidden from normal list/read/access paths so a half-merge is never visible
    as a normal thread. Gated by COMMS_COMBINE_SAFE; legacy threads never carry
    the merge_state field, so this is a no-op when the flag is OFF or on old data.
    """
    if not thread:
        return False
    return str(thread.get('merge_state') or '').strip().lower() in ('in_progress', 'failed')


async def get_thread(db: AsyncSession, thread_id: UUID) -> Optional[Dict[str, Any]]:
    """Get thread from MongoDB. Returns dict for compatibility."""
    thread = await ThreadRepository.get_by_id(thread_id)
    if _thread_merge_hidden(thread):
        return None
    if thread:
        # Load participants
        participants = await ThreadParticipantRepository.list_by_thread(thread_id)
        thread['participants'] = participants
    return thread


async def get_thread_with_messages(
    db: AsyncSession,
    thread_id: UUID,
    limit: int = 50,
    offset: int = 0
) -> Optional[Dict[str, Any]]:
    """Get thread with messages from MongoDB. Returns dict for compatibility."""
    thread = await ThreadRepository.get_by_id(thread_id)
    if _thread_merge_hidden(thread):
        return None
    if thread:
        # Load participants
        participants = await ThreadParticipantRepository.list_by_thread(thread_id)
        thread['participants'] = participants
        
        # Load messages
        messages = await ThreadMessageRepository.list_by_thread(thread_id, limit, offset)
        thread['messages'] = messages
    return thread


def _thread_visible_in_list(thread: Dict[str, Any], normalized_user_email: str) -> bool:
    """Visibility rule for one thread in the list endpoint.

    - A thread mid-merge / failed-merge is never listed as a normal thread.
    - Site-visible threads: allow all users for the selected study/site.
    - Private or unknown scope: only if user is an explicit participant.
    """
    if _thread_merge_hidden(thread):
        return False
    visibility_scope = str(thread.get("visibility_scope", "private") or "").strip().lower()
    if visibility_scope == "site":
        return True
    participants_emails = [
        str(e).lower().strip() for e in (thread.get("participants_emails") or []) if e
    ]
    return normalized_user_email in participants_emails


async def list_threads(
    db: AsyncSession,
    limit: int = 50,
    offset: int = 0,
    participant_id: Optional[str] = None,
    study_id: Optional[str] = None,
    site_id: Optional[str] = None,
    user_email: Optional[str] = None
) -> List[Dict[str, Any]]:
    """List threads from MongoDB with optional filters. 
    
    VISIBILITY RULES (aligned with product requirements):
    - Private threads: only visible if user's email is in participants_emails.
    - Site-visible threads: visible to any authenticated user for the selected study/site.
    """
    normalized_user_email = user_email.lower().strip() if user_email else None
    if not normalized_user_email:
        return []

    # 1) Threads where repository already applies user_email-based filtering
    user_threads = await ThreadRepository.list(
        limit=limit,
        offset=offset,
        participant_id=participant_id,
        study_id=study_id,
        site_id=site_id,
        user_email=normalized_user_email,
    )

    # 2) Additional threads for this study/site (used to pick up site-visible threads)
    all_threads_for_site = await ThreadRepository.list(
        limit=limit * 2,
        offset=0,
        participant_id=participant_id,
        study_id=study_id,
        site_id=site_id,
        user_email=None,
    )

    # Merge, de-duplicate by id
    threads_by_id: Dict[Any, Dict[str, Any]] = {}
    for t in user_threads + all_threads_for_site:
        tid = t.get("id")
        if tid is not None:
            threads_by_id[tid] = t

    visible_threads: List[Dict[str, Any]] = [
        thread for thread in threads_by_id.values()
        if _thread_visible_in_list(thread, normalized_user_email)
    ]

    # Load participants for each visible thread
    for thread in visible_threads:
        thread_id = thread.get('id')
        if thread_id:
            participants = await ThreadParticipantRepository.list_by_thread(thread_id)
            thread['participants'] = participants

    return visible_threads


async def add_thread_participant(
    db: AsyncSession,
    thread_id: UUID,
    participant: ThreadParticipantCreate
) -> Dict[str, Any]:
    """Add thread participant in MongoDB. Returns dict for compatibility."""
    participant_data = {
        'id': uuid.uuid4(),
        'thread_id': thread_id,
        'participant_id': participant.participant_id,
        'participant_name': participant.participant_name,
        'participant_email': participant.participant_email,
        'role': participant.role
    }
    return await ThreadParticipantRepository.create(participant_data)


async def create_thread_message(
    db: AsyncSession,
    thread_id: UUID,
    message: ThreadMessageCreate
) -> Dict[str, Any]:
    """Create thread message in MongoDB. Returns dict for compatibility."""
    # Extract mentioned emails from message body
    from app.utils.email_mentions import extract_mention_emails
    mentioned_emails = extract_mention_emails(message.body)
    
    message_data = {
        'id': uuid.uuid4(),
        'thread_id': thread_id,
        'message_id': message.message_id,
        'body': message.body,
        'author_id': message.author_id,
        'author_name': message.author_name,
        'mentioned_emails': mentioned_emails,  # Store extracted email mentions
        'message_type': message.message_type if hasattr(message, 'message_type') else None
    }
    db_message = await ThreadMessageRepository.create(message_data)
    
    # Update thread updated_at
    await ThreadRepository.update(thread_id, {'updated_at': datetime.now(timezone.utc)})
    
    return db_message


async def update_thread_status(
    db: AsyncSession,
    thread_id: UUID,
    status: str
) -> Optional[Dict[str, Any]]:
    """Update thread status in MongoDB. Returns dict for compatibility."""
    return await ThreadRepository.update(thread_id, {
        'status': status,
        'updated_at': datetime.now(timezone.utc)
    })


async def add_thread_participant_email(
    db: AsyncSession,
    thread_id: UUID,
    email: str,
    user_email: Optional[str] = None
) -> Dict[str, Any]:
    """Add an email to thread's participants_emails list. Only thread creator or existing participant can modify."""
    # Get thread
    thread = await ThreadRepository.get_by_id(thread_id)
    if not thread:
        raise ValueError(f"Thread {thread_id} not found")
    
    # Check authorization: only thread creator OR existing participant can modify
    if user_email:
        user_email_lower = user_email.lower().strip()
        created_by = thread.get('created_by', '').lower().strip()
        participants_emails = [str(e).lower().strip() for e in (thread.get('participants_emails') or []) if e]
        
        if user_email_lower != created_by and user_email_lower not in participants_emails:
            raise ValueError("Only thread creator or existing participants can modify participant list")
    
    # Normalize email
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("Email cannot be empty")
    
    # Get current participants_emails
    participants_emails = thread.get('participants_emails', []) or []
    participants_emails = [str(e).lower().strip() for e in participants_emails if e]
    
    # Add if not already present (prevent duplicates)
    if normalized_email not in participants_emails:
        participants_emails.append(normalized_email)
        
        # Update thread
        updated = await ThreadRepository.update(thread_id, {
            'participants_emails': participants_emails,
            'updated_at': datetime.now(timezone.utc)
        })
        
        return updated or thread
    else:
        # Already exists, return thread as-is
        return thread


async def remove_thread_participant_email(
    db: AsyncSession,
    thread_id: UUID,
    email: str,
    user_email: Optional[str] = None
) -> Dict[str, Any]:
    """Remove an email from thread's participants_emails list. Only thread creator or existing participant can modify."""
    # Get thread
    thread = await ThreadRepository.get_by_id(thread_id)
    if not thread:
        raise ValueError(f"Thread {thread_id} not found")
    
    # Check authorization: only thread creator OR existing participant can modify
    if user_email:
        user_email_lower = user_email.lower().strip()
        created_by = thread.get('created_by', '').lower().strip()
        participants_emails = [str(e).lower().strip() for e in (thread.get('participants_emails') or []) if e]
        
        if user_email_lower != created_by and user_email_lower not in participants_emails:
            raise ValueError("Only thread creator or existing participants can modify participant list")
    
    # Normalize email
    normalized_email = email.strip().lower()
    
    # Get current participants_emails
    participants_emails = thread.get('participants_emails', []) or []
    participants_emails = [str(e).lower().strip() for e in participants_emails if e]
    
    # Remove if present
    if normalized_email in participants_emails:
        participants_emails.remove(normalized_email)
        
        # Update thread
        updated = await ThreadRepository.update(thread_id, {
            'participants_emails': participants_emails,
            'updated_at': datetime.now(timezone.utc)
        })
        
        return updated or thread
    else:
        # Not found, return thread as-is
        return thread


async def _collect_selected_conversation_messages(conversation_id: UUID, message_ids: List[UUID]) -> List[Dict[str, Any]]:
    """Get the selected messages from MongoDB, ensuring all belong to the conversation."""
    all_messages = []
    for msg_id in message_ids:
        msg = await MessageRepository.get_by_id(msg_id)
        if msg and msg.get('conversation_id') == conversation_id:
            all_messages.append(msg)

    if len(all_messages) != len(message_ids):
        raise ValueError("Some message IDs not found in conversation")
    return all_messages


def _merged_private_participant_emails(
    participants_emails: Optional[List[str]],
    conv_email,
    creator_email: Optional[str],
) -> List[str]:
    """Build participants_emails list for private threads.
    - Start from any explicit participants_emails passed in the request
    - Optionally include conversation participant email (if any)
    - Always include creator email (if any)
    Keeps order while de-duplicating."""
    merged_emails: List[str] = []
    for e in (participants_emails or []):
        if e and str(e).strip():
            merged_emails.append(str(e).strip().lower())
    if conv_email and str(conv_email).strip():
        merged_emails.append(str(conv_email).strip().lower())
    if creator_email and str(creator_email).strip():
        merged_emails.append(str(creator_email).strip().lower())
    return list(dict.fromkeys(merged_emails))


async def _add_conversation_default_participant(thread_id, conv, conv_email) -> None:
    """Add the conversation's participant as a thread participant (if the
    conversation carries an email or phone)."""
    conv_phone = _conv_field(conv, 'participant_phone')
    if conv_email or conv_phone:
        participant_data = {
            'id': uuid.uuid4(),
            'thread_id': thread_id,
            'participant_id': conv_email or conv_phone,
            'participant_name': None,
            'participant_email': conv_email,
            'role': 'participant'
        }
        await ThreadParticipantRepository.create(participant_data)


async def _copy_conversation_messages_to_thread(thread_id, all_messages: List[Dict[str, Any]]) -> None:
    """Create thread messages from conversation messages (preserve links).
    Sorted by created_at (oldest first for thread)."""
    sorted_messages = sorted(all_messages, key=lambda m: m.get('created_at', datetime.min), reverse=False)
    for msg in sorted_messages:
        thread_msg_data = {
            'id': uuid.uuid4(),
            'thread_id': thread_id,
            'message_id': msg.get('id'),  # Link to original message
            'body': msg.get('body'),
            'author_id': msg.get('author_id') or msg.get('direction', 'unknown'),
            'author_name': msg.get('author_name')
        }
        await ThreadMessageRepository.create(thread_msg_data)


async def create_thread_from_conversation(
    db: AsyncSession,
    conversation_id: UUID,
    title: str,
    description: Optional[str],
    thread_type: str,
    message_ids: List[UUID],
    created_by: Optional[str] = None,
    creator_email: Optional[str] = None,
    related_study_id: Optional[str] = None,
    visibility_scope: Optional[str] = None,
    participants_emails: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Create a thread from selected messages in a conversation. Uses MongoDB."""
    # Verify conversation exists
    conv = await get_conversation(db, conversation_id)
    if not conv:
        raise ValueError(f"Conversation {conversation_id} not found")

    all_messages = await _collect_selected_conversation_messages(conversation_id, message_ids)

    # Handle dict from MongoDB
    conv_study_id = conv.get('study_id') if isinstance(conv, dict) else conv.study_id
    effective_study_id = conv_study_id or related_study_id
    conv_site_id = _conv_field(conv, 'site_id')
    conv_email = _conv_field(conv, 'participant_email')

    # Normalize visibility scope; default to private
    scope = (visibility_scope or "private").strip().lower()
    if scope not in ("private", "site"):
        scope = "private"

    participants_emails_final = (
        _merged_private_participant_emails(participants_emails, conv_email, creator_email)
        if scope == "private" else []
    )
    
    # Create the thread in MongoDB
    thread_data = {
        'id': uuid.uuid4(),
        'conversation_id': conversation_id,
        'title': title,
        'description': description,
        'thread_type': thread_type,
        'related_patient_id': None,  # Explicitly set to None
        'related_study_id': effective_study_id,
        'site_id': conv_site_id,
        'participants_emails': participants_emails_final,
        'visibility_scope': scope,
        'created_by': created_by,
        'status': 'open',
        'priority': 'medium',
        'tmf_filed': False,
        'tmf_filed_at': None,
        'conversation_address': None,
        'agreement_type': None
    }
    thread = await ThreadRepository.create(thread_data)
    thread_id = thread.get('id')

    # Create ThreadFromConversation link (required for all threads)
    link_data = {
        'id': uuid.uuid4(),
        'thread_id': thread_id,
        'conversation_id': conversation_id,
        'source_message_ids': [str(msg_id) for msg_id in message_ids],
        'created_by': created_by
    }
    await ThreadFromConversationRepository.create(link_data)

    # Add conversation participant as thread participant
    await _add_conversation_default_participant(thread_id, conv, conv_email)

    # Create thread messages from conversation messages (preserve links)
    await _copy_conversation_messages_to_thread(thread_id, all_messages)

    # Link conversation attachments to the thread
    await link_conversation_attachments_to_thread(db, thread_id, conversation_id, message_ids)
    
    # Load participants for response
    participants = await ThreadParticipantRepository.list_by_thread(thread_id)
    thread['participants'] = participants
    
    return thread


# Access Control CRUD Functions
async def create_user(db: AsyncSession, user: UserCreate, password_hash: Optional[str] = None) -> User:
    """Create a new user."""
    user_dict = user.dict(exclude={'password'})  # Exclude password from dict
    user_dict['is_privileged'] = 'true' if user_dict.get('is_privileged', False) else 'false'
    if 'role' in user_dict:
        try:
            user_dict['role'] = UserRole(user_dict['role'])
        except ValueError:
            user_dict['role'] = UserRole.PARTICIPANT
    
    if password_hash:
        user_dict['password_hash'] = password_hash
    
    db_user = User(**user_dict)
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user


async def get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    """Get user by email."""
    result = await db.execute(select(User).where(User.email == email))
    return result.scalar_one_or_none()


async def authenticate_user(db: AsyncSession, email: str, password: str) -> Optional[User]:
    """Authenticate a user by email and password."""
    from app.auth import verify_password
    
    user = await get_user_by_email(db, email)
    if not user:
        return None
    if not user.password_hash:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_user(db: AsyncSession, user_id: str) -> Optional[User]:
    """Get user by user_id."""
    result = await db.execute(select(User).where(User.user_id == user_id))
    return result.scalar_one_or_none()


async def list_users(db: AsyncSession, limit: int = 100, offset: int = 0) -> List[User]:
    """List all users."""
    result = await db.execute(
        select(User)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def ensure_postgres_user_for_iam_mirror(
    db: AsyncSession,
    *,
    user_id: str,
    email: Optional[str],
    display_name: Optional[str],
) -> Optional[User]:
    """
    Ensure Postgres `users` contains a row for this IAM hub id (`users.user_id`).

    Kafka consumers dual-write Mongo `local_users` + Postgres; listing users from
    Mongo alone still needs matching FK targets (`sites.principal_investigator_id`).
    Uses the same default-password hash policy as `kafka.events.user_event`.
    """
    from sqlalchemy.exc import IntegrityError
    import logging as _logging

    _log = _logging.getLogger(__name__)

    if not user_id:
        return None

    existing = (await db.execute(select(User).where(User.user_id == user_id))).scalar_one_or_none()
    if existing is not None:
        return existing

    # Deferred import — pulls bcrypt-derived DEFAULT_PASSWORD_HASH from the user-sync handler.
    from app.integrations.kafka.events.user_event import _DEFAULT_PASSWORD_HASH

    try:
        async with db.begin_nested():
            db.add(
                User(
                    user_id=user_id,
                    email=(email or None),
                    name=(display_name or None),
                    role=UserRole.PARTICIPANT,
                    password_hash=_DEFAULT_PASSWORD_HASH,
                )
            )
            await db.flush()
    except IntegrityError:
        _log.warning(
            "[crm] IAM mirror insert skipped (duplicate?): user_id=%r email=%r",
            user_id,
            email,
        )

    row = (await db.execute(select(User).where(User.user_id == user_id))).scalar_one_or_none()
    if row is not None:
        return row
    if email:
        return await get_user_by_email(db, email)
    return None


async def is_user_privileged(db: AsyncSession, user_id: str) -> bool:
    """Check if a user has privileged access."""
    user = await get_user(db, user_id)
    if not user:
        return False
    return user.is_privileged == 'true'


VALID_CONV_STATUSES = {"open", "awaiting_reply", "awaiting_us", "snoozed", "resolved", "closed"}
VALID_CONV_PRIORITIES = {"low", "medium", "high", "urgent"}


async def update_conversation_state(
    db: AsyncSession,
    conversation_id: UUID,
    patch: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Patch the operational state of a conversation.

    `patch` is the request body filtered via ``model_dump(exclude_unset=True)``
    so it only contains keys the caller explicitly sent. Keys set to ``None``
    clear that field; keys absent are not touched.

    Allowed keys: ``status``, ``owner_user_id``, ``due_at``, ``priority``,
    ``snooze_until``. Anything else is ignored.
    """
    conv = await get_conversation(db, conversation_id)
    if not conv:
        return None

    updates: Dict[str, Any] = {}
    _apply_validated_state_patch(patch, updates, "status", VALID_CONV_STATUSES)
    await _apply_owner_state_patch(db, patch, updates)
    _apply_validated_state_patch(patch, updates, "priority", VALID_CONV_PRIORITIES)
    _apply_datetime_state_patch(patch, updates, "due_at")
    _apply_datetime_state_patch(patch, updates, "snooze_until")

    if not updates:
        return conv
    return await ConversationRepository.update(conversation_id, updates)


def _apply_validated_state_patch(patch: Dict[str, Any], updates: Dict[str, Any], key: str, valid_values: set) -> None:
    """Copy `key` from patch into updates, validating non-None values against `valid_values`."""
    if key not in patch:
        return
    value = patch[key]
    if value is not None and value not in valid_values:
        raise ValueError(f"Invalid {key} '{value}'")
    updates[key] = value


async def _apply_owner_state_patch(db: AsyncSession, patch: Dict[str, Any], updates: Dict[str, Any]) -> None:
    """Copy owner_user_id (+derived owner_name) from patch into updates."""
    if "owner_user_id" not in patch:
        return
    owner = patch["owner_user_id"]
    if not owner:
        updates["owner_user_id"] = None
        updates["owner_name"] = None
        return
    user = await get_user(db, owner)
    if not user:
        raise ValueError("Owner is not a known user")
    updates["owner_user_id"] = owner
    updates["owner_name"] = (
        getattr(user, "name", None) or getattr(user, "email", None) or owner
    )


def _apply_datetime_state_patch(patch: Dict[str, Any], updates: Dict[str, Any], key: str) -> None:
    """Copy a datetime-or-string field from patch into updates as ISO string."""
    if key not in patch:
        return
    value = patch[key]
    updates[key] = value.isoformat() if isinstance(value, datetime) else value


async def update_conversation_access(
    db: AsyncSession,
    conversation_id: UUID,
    is_restricted: Optional[bool] = None,
    is_confidential: Optional[bool] = None,
    privileged_users: Optional[List[str]] = None
) -> Optional[Dict[str, Any]]:
    """Update conversation access settings in MongoDB. Returns dict for compatibility."""
    conv = await get_conversation(db, conversation_id)
    if not conv:
        return None
    
    updates = {}
    if is_restricted is not None:
        updates['is_restricted'] = 'true' if is_restricted else 'false'

    if is_confidential is not None:
        updates['is_confidential'] = 'true' if is_confidential else 'false'

    if privileged_users is not None:
        updates['privileged_users'] = privileged_users

    updates['access_level'] = _recomputed_access_level(conv, is_restricted, is_confidential)

    if updates:
        return await ConversationRepository.update(conversation_id, updates)
    return conv


def _flag_truthy(v) -> bool:
    return str(v or '').strip().lower() in ('true', '1', 'yes', 't')


def _recomputed_access_level(conv, is_restricted: Optional[bool], is_confidential: Optional[bool]) -> str:
    """Recompute access_level symmetrically from the EFFECTIVE flag values
    (incoming change OR existing value for a flag not passed) so it can return
    to PUBLIC when both flags are cleared."""
    eff_conf = is_confidential if is_confidential is not None else _flag_truthy(_conv_field(conv, 'is_confidential'))
    eff_restr = is_restricted if is_restricted is not None else _flag_truthy(_conv_field(conv, 'is_restricted'))
    if eff_conf:
        return 'CONFIDENTIAL'
    if eff_restr:
        return 'RESTRICTED'
    return 'PUBLIC'


async def grant_conversation_access(
    db: AsyncSession,
    conversation_id: UUID,
    access: ConversationAccessCreate
) -> ConversationAccess:
    """Grant access to a conversation for a user."""
    # Check if access already exists
    result = await db.execute(
        select(ConversationAccess)
        .where(ConversationAccess.conversation_id == conversation_id)
        .where(ConversationAccess.user_id == access.user_id)
    )
    existing = result.scalar_one_or_none()
    
    if existing:
        # Update existing access
        existing.access_type = AccessType(access.access_type)
        existing.granted_by = access.granted_by
        await db.commit()
        await db.refresh(existing)
        return existing
    
    # Create new access
    access_dict = access.dict()
    access_dict['conversation_id'] = conversation_id
    access_dict['access_type'] = AccessType(access_dict['access_type'])
    
    db_access = ConversationAccess(**access_dict)
    db.add(db_access)
    await db.commit()
    await db.refresh(db_access)
    return db_access


async def revoke_conversation_access(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: str
) -> bool:
    """Revoke access to a conversation for a user."""
    result = await db.execute(
        select(ConversationAccess)
        .where(ConversationAccess.conversation_id == conversation_id)
        .where(ConversationAccess.user_id == user_id)
    )
    access = result.scalar_one_or_none()
    
    if access:
        await db.delete(access)
        await db.flush()
        await db.commit()
        return True
    return False


async def get_conversation_access_list(
    db: AsyncSession,
    conversation_id: UUID
) -> List[ConversationAccess]:
    """Get list of all users with access to a conversation."""
    result = await db.execute(
        select(ConversationAccess)
        .where(ConversationAccess.conversation_id == conversation_id)
    )
    return list(result.scalars().all())


def _conv_flags_public(is_confidential, is_restricted, access_level) -> bool:
    """Public = not confidential, not restricted, and PUBLIC (or unset) access_level."""
    if is_confidential == 'true' or is_restricted == 'true':
        return False
    return not access_level or access_level == 'PUBLIC' or access_level == 'public'


async def check_user_access(
    db: AsyncSession,
    conversation_id: UUID,
    user_id: str
) -> Optional[str]:
    """Check if user has access to conversation. Returns access_type or None."""
    conv = await get_conversation(db, conversation_id)
    if not conv:
        return None
    
    # Handle dict from MongoDB
    is_confidential = conv.get('is_confidential') if isinstance(conv, dict) else conv.is_confidential
    is_restricted = conv.get('is_restricted') if isinstance(conv, dict) else conv.is_restricted
    access_level = conv.get('access_level') if isinstance(conv, dict) else conv.access_level
    privileged_users = conv.get('privileged_users') if isinstance(conv, dict) else conv.privileged_users
    created_by = conv.get('created_by') if isinstance(conv, dict) else conv.created_by

    # Public conversations (not confidential, not restricted) - everyone has access
    if _conv_flags_public(is_confidential, is_restricted, access_level):
        return 'read'

    # For confidential or restricted conversations, check explicit access
    # Check explicit access grants first (from Postgres)
    result = await db.execute(
        select(ConversationAccess)
        .where(ConversationAccess.conversation_id == conversation_id)
        .where(ConversationAccess.user_id == user_id)
    )
    access = result.scalar_one_or_none()
    if access:
        return access.access_type.value
    
    # Check if user is in privileged_users list
    if privileged_users and user_id in privileged_users:
        return 'read'
    
    # Check if user created the conversation (creator always has access)
    if created_by and created_by == user_id:
        return 'admin'
    
    # No access for confidential/restricted conversations without explicit grant
    return None


# Role-Based Access Control Functions
async def check_user_has_site_access(
    db: AsyncSession,
    user_id: str,
    site_id: UUID
) -> bool:
    """
    Check if user has access to a site based on their role assignments.
    
    Rules:
    - CRA: Has access if assigned to this specific site
    - Study Manager: Has access if assigned to this site (site-level access)
    - Medical Monitor: Has access if assigned to this specific site
    """
    assignments = await UserRoleAssignmentRepository.list_by_user(db, user_id)
    
    for assignment in assignments:
        if assignment.role in [UserRole.CRA, UserRole.STUDY_MANAGER, UserRole.MEDICAL_MONITOR]:
            # If assigned to this specific site
            if assignment.site_id == site_id:
                return True
    
    return False


async def check_user_has_study_access(
    db: AsyncSession,
    user_id: str,
    study_id: UUID
) -> bool:
    """
    Check if user has access to a study based on their role assignments.
    
    Rules:
    - CRA: Has access if assigned to this specific study
    - Study Manager: Has access if assigned to any site that belongs to this study
    - Medical Monitor: Has access if assigned to this specific study
    """
    assignments = await UserRoleAssignmentRepository.list_by_user(db, user_id)
    
    for assignment in assignments:
        if assignment.role == UserRole.CRA or assignment.role == UserRole.MEDICAL_MONITOR:
            # CRA and Medical Monitor: direct study assignment
            if assignment.study_id == study_id:
                return True
        
        elif assignment.role == UserRole.STUDY_MANAGER:
            # Study Manager: site-level access - check if site belongs to study via StudySite mapping
            if assignment.site_id:
                study_site_result = await db.execute(
                    select(StudySite).where(
                        StudySite.site_id == assignment.site_id,
                        StudySite.study_id == study_id,
                    )
                )
                study_site = study_site_result.scalar_one_or_none()
                if study_site:
                    return True
    
    return False


async def get_user_accessible_sites(
    db: AsyncSession,
    user_id: str
) -> List[Site]:
    """
    Get all sites that a user has access to based on their role assignments.
    
    Returns list of Site objects the user can access.
    """
    assignments = await UserRoleAssignmentRepository.list_by_user(db, user_id)
    accessible_site_ids = set()
    
    for assignment in assignments:
        if assignment.role in [UserRole.CRA, UserRole.STUDY_MANAGER, UserRole.MEDICAL_MONITOR]:
            if assignment.site_id:
                accessible_site_ids.add(assignment.site_id)
    
    if not accessible_site_ids:
        return []
    
    # Fetch all accessible sites
    sites = []
    for site_id in accessible_site_ids:
        result = await db.execute(select(Site).where(Site.id == site_id))
        site = result.scalar_one_or_none()
        if site:
            sites.append(site)
    
    return sites


async def get_user_accessible_studies(
    db: AsyncSession,
    user_id: str
) -> List[Study]:
    """
    Get all studies that a user has access to based on their role assignments.
    
    Rules:
    - CRA/Medical Monitor: Studies directly assigned
    - Study Manager: All studies in sites they have access to
    """
    assignments = await UserRoleAssignmentRepository.list_by_user(db, user_id)
    accessible_study_ids, accessible_site_ids = _assignment_study_site_scopes(assignments)

    # For sites, get their associated studies
    if accessible_site_ids:
        # Resolve studies via StudySite mappings instead of deprecated sites.study_id
        result = await db.execute(
            select(StudySite.study_id).where(StudySite.site_id.in_(accessible_site_ids))
        )
        for row in result.all():
            study_id = row[0]
            if study_id:
                accessible_study_ids.add(study_id)

    if not accessible_study_ids:
        return []

    # Fetch all accessible studies
    studies = []
    for study_id in accessible_study_ids:
        result = await db.execute(select(Study).where(Study.id == study_id))
        study = result.scalar_one_or_none()
        if study:
            studies.append(study)

    return studies


def _assignment_study_site_scopes(assignments) -> Tuple[set, set]:
    """Collect direct study ids (CRA / Medical Monitor) and site ids
    (CRA / Medical Monitor / Study Manager) from role assignments."""
    accessible_study_ids = set()
    accessible_site_ids = set()

    for assignment in assignments:
        if assignment.role == UserRole.CRA or assignment.role == UserRole.MEDICAL_MONITOR:
            # Direct study assignment
            if assignment.study_id:
                accessible_study_ids.add(assignment.study_id)
            # Direct site assignment (for site-level access)
            if assignment.site_id:
                accessible_site_ids.add(assignment.site_id)

        elif assignment.role == UserRole.STUDY_MANAGER:
            # Site-level access - get all studies in these sites
            if assignment.site_id:
                accessible_site_ids.add(assignment.site_id)

    return accessible_study_ids, accessible_site_ids


async def check_user_can_access_thread(
    db: AsyncSession,
    user_id: str,
    thread: Dict[str, Any],
    user_email: Optional[str] = None,
) -> bool:
    """Access rule for threads — mirrors the conversation rule.

    1. Thread creator (`created_by == user_id`) always has access.
    2. A user whose email is on the participants list has access.
    3. A user listed in the participants by user_id has access.
    4. Otherwise: no access.

    Used today by the multi-subscribe WebSocket endpoint to authorize a
    socket before it joins a thread channel. Kept narrow on purpose — the
    REST list/detail endpoints already enforce their own access semantics
    and aren't supposed to share a single function with the realtime path.
    """
    if not user_id:
        return False

    # A thread mid-merge / failed-merge is hidden from access (COMMS_COMBINE_SAFE).
    if _thread_merge_hidden(thread):
        return False

    created_by = str(thread.get('created_by') or '').strip()
    if created_by and created_by == str(user_id):
        return True

    if await _thread_site_visible_to_user(user_id, thread):
        return True

    email_lc = (str(user_email).strip().lower() if user_email else "")
    participants = thread.get('participants') or []
    if not isinstance(participants, (list, tuple)):
        return False

    for p in participants:
        if _thread_participant_matches_user(p, user_id, email_lc):
            return True

    return False


async def _thread_site_visible_to_user(user_id: str, thread: Dict[str, Any]) -> bool:
    """Site-visible threads: a study member may access them (flag-gated). When
    COMMS_ENFORCE_MEMBERSHIP is OFF this check is skipped entirely, preserving
    the legacy participation-only behavior byte-for-byte. Only threads
    explicitly marked `visibility_scope == 'site'` use this shortcut — a
    'private' thread (or one with no study) always falls through to the
    participation rules in the caller, so private threads are never broadened.
    `related_study_id` is a local_resources._id (spike verdict: MATCH)."""
    visibility = str(thread.get('visibility_scope') or '').strip().lower()
    if visibility != 'site':
        return False
    related_study = str(thread.get('related_study_id') or '').strip()
    if not related_study:
        return False
    from app.integrations.iam.membership import user_can_access_study
    return await user_can_access_study(str(user_id), related_study)


def _thread_participant_matches_user(p: Any, user_id: str, email_lc: str) -> bool:
    """One participant row matches by user_id or by email (case-insensitive)."""
    if not isinstance(p, dict):
        return False
    # user_id match
    pid = p.get('user_id') or p.get('participant_id')
    if pid and str(pid) == str(user_id):
        return True
    # email match (case-insensitive)
    if email_lc:
        pe = p.get('email') or p.get('participant_email')
        if pe and str(pe).strip().lower() == email_lc:
            return True
    return False


async def bulk_check_conversation_access(
    db: AsyncSession,
    conversation_ids: List[Any],
    user_id: str,
) -> set:
    """
    Return the set of conversation_ids (as strings) for which the given user
    has an explicit `ConversationAccess` grant in Postgres.

    Used by `list_conversations` to replace the per-row access check that
    previously fired one SELECT per conversation. One query for the batch.

    The set uses **string** keys so callers can compare against whatever shape
    the conversation id arrives in (UUID, str, etc.) — the route holds dicts
    from MongoDB where `id` is sometimes a string.
    """
    if not conversation_ids or not user_id:
        return set()

    # Normalize ids: keep both UUID and str variants in the IN list. Postgres
    # treats them the same once cast, but the .scalars() result will come back
    # as whatever the column type is (UUID). We stringify on the way out so
    # the caller does not have to care.
    try:
        result = await db.execute(
            select(ConversationAccess.conversation_id)
            .where(ConversationAccess.conversation_id.in_(conversation_ids))
            .where(ConversationAccess.user_id == user_id)
        )
        return {str(row) for row in result.scalars().all()}
    except Exception:
        # Mirrors the swallowed exception behavior of the single-row check
        # below: if the access table or DB is unhappy, fall back to "no
        # explicit grants" rather than 500-ing the whole list endpoint.
        return set()


async def check_user_can_access_conversation_by_role(
    db: AsyncSession,
    user_id: str,
    conversation: Dict[str, Any],
    user_email: Optional[str] = None,
    access_set: Optional[set] = None,
) -> bool:
    """
    Access rule (creator + email-participants model):

    1. System-owned public notice boards stay visible to everyone in the site
       (`conversation_type == 'notice_board'`, or `is_pinned` & `created_by == 'system'`,
       or `access_level == 'PUBLIC'` & `created_by == 'system'`).
    2. PUBLIC conversations scoped to a (study, site) are visible to every user
       who can reach that study+site. The list route already filters the Mongo
       query by `study_id` + `site_id` taken from the request, so any conv that
       lands here is in the requester's chosen scope. RESTRICTED / CONFIDENTIAL
       remain gated on the creator/participant/grant rules below.
    3. The conversation's creator (`created_by == user_id`) always has access.
    4. A user whose email is listed on the conversation (`participant_email` or
       anything in `participant_emails`) has access.
    5. An explicit Postgres `ConversationAccess` grant or membership in
       `privileged_users` also grants access.
    6. Otherwise: NO access.

    `access_set`: optional set of stringified conversation_ids the user has
    explicit Postgres grants for, pre-fetched by `bulk_check_conversation_access`.
    When provided, step 5 uses set membership instead of a per-call SELECT,
    eliminating the N+1 that `list_conversations` used to incur.
    """
    created_by = str(conversation.get('created_by') or '').strip()
    access_level = str(conversation.get('access_level') or '').strip().upper()

    # 1. System-owned public boards stay public.
    if _is_system_public_board(conversation, created_by.lower(), access_level):
        return True

    # 2. PUBLIC conversations scoped to a (study, site) are visible to every
    # user in that study+site (LEAK-1: members of the conv's study only). A
    # non-member does NOT short-circuit — fall through to the participation
    # rules below.
    if await _public_conv_study_member_access(user_id, conversation, access_level):
        return True

    # 3. Creator always has access.
    if created_by and user_id and created_by == str(user_id):
        return True

    # 4. Email participants have access.
    if _conv_email_participant_match(conversation, user_email):
        return True

    # 5. Explicit grants or privileged_users list.
    if await _conv_has_explicit_grant(db, conversation, user_id, access_set):
        return True

    # 6. Default deny.
    return False


def _is_system_public_board(conversation: Dict[str, Any], created_by_lc: str, access_level: str) -> bool:
    """System-owned public notice boards stay visible to everyone in the site:
    `conversation_type == 'notice_board'`, or `is_pinned` & `created_by == 'system'`,
    or `access_level == 'PUBLIC'` & `created_by == 'system'`."""
    conv_type = str(conversation.get('conversation_type') or '').strip().lower()
    if conv_type == 'notice_board':
        return True
    pinned_raw = conversation.get('is_pinned')
    pinned = (
        pinned_raw is True
        or str(pinned_raw or '').strip().lower() in ('true', '1', 'yes', 't')
    )
    if pinned and created_by_lc == 'system':
        return True
    return access_level == 'PUBLIC' and created_by_lc == 'system'


async def _public_conv_study_member_access(user_id: str, conversation: Dict[str, Any], access_level: str) -> bool:
    """PUBLIC conversations scoped to a (study, site) are visible to every
    user in that study+site. The list route filters the Mongo query by the
    caller's study_id + site_id, so any conv reaching this check that has
    both a study_id and site_id is already in the requester's chosen scope.
    This is what users mean by "conversations on a site should be shared"
    — without it, user B never sees user A's thread on the same site even
    though both picked the same study+site in the UI.

    Privacy gate: a conversation explicitly flagged confidential or restricted
    is never treated as PUBLIC here, even if a legacy one-way access_level
    update left access_level == 'PUBLIC'.

    LEAK-1 fix: a PUBLIC conversation is visible only to members of its
    study. `conv_study` is a local_resources._id, the exact id IAM
    resource_access uses. A non-member does NOT short-circuit here —
    the caller falls through to the participation rules so the creator /
    named participants / explicitly-granted users still get in. A
    study-less PUBLIC conv never reaches the membership check (guarded by
    `conv_study and conv_site`) and so also falls through to
    participation-only."""
    if access_level != 'PUBLIC':
        return False
    if _flag_truthy(conversation.get('is_confidential')) or _flag_truthy(conversation.get('is_restricted')):
        return False
    conv_study = str(conversation.get('study_id') or '').strip()
    conv_site = str(conversation.get('site_id') or '').strip()
    if not (conv_study and conv_site):
        return False
    from app.integrations.iam.membership import user_can_access_study
    return await user_can_access_study(user_id, conv_study)


def _conv_email_participant_match(conversation: Dict[str, Any], user_email: Optional[str]) -> bool:
    """A user whose email is listed on the conversation (`participant_email` or
    anything in `participant_emails`) has access."""
    if not user_email:
        return False
    email_lc = str(user_email).strip().lower()
    if not email_lc:
        return False
    participant_email = conversation.get('participant_email')
    if participant_email and str(participant_email).strip().lower() == email_lc:
        return True
    participant_emails = conversation.get('participant_emails') or []
    if isinstance(participant_emails, (list, tuple)):
        for pe in participant_emails:
            if pe and str(pe).strip().lower() == email_lc:
                return True
    return False


async def _conv_has_explicit_grant(
    db: AsyncSession, conversation: Dict[str, Any], user_id: str, access_set: Optional[set]
) -> bool:
    """Explicit Postgres `ConversationAccess` grant or membership in `privileged_users`."""
    privileged_users = conversation.get('privileged_users') or []
    if isinstance(privileged_users, (list, tuple)) and user_id in privileged_users:
        return True
    conv_id = conversation.get('id')
    if not (conv_id and user_id):
        return False
    # Fast path: caller batched the access lookup for the whole page.
    if access_set is not None:
        return str(conv_id) in access_set
    # Legacy single-row path. Kept for callers (e.g.
    # `get_conversation_with_messages`) that only look at one conv.
    try:
        result = await db.execute(
            select(ConversationAccess)
            .where(ConversationAccess.conversation_id == conv_id)
            .where(ConversationAccess.user_id == user_id)
        )
        return result.scalar_one_or_none() is not None
    except Exception:
        return False


# Attachment CRUD Functions
async def create_attachment(
    db: AsyncSession,
    conversation_id: UUID,
    file_path: str,
    content_type: str,
    size: int,
    message_id: Optional[UUID] = None,
    checksum: Optional[str] = None
) -> Dict[str, Any]:
    """Create a new attachment record in MongoDB. Returns dict for compatibility."""
    att_data = {
        'id': uuid.uuid4(),
        'conversation_id': conversation_id,
        'message_id': message_id,
        'file_path': file_path,
        'content_type': content_type,
        'size': size,
        'checksum': checksum
    }
    return await AttachmentRepository.create(att_data)


async def get_attachment(db: AsyncSession, attachment_id: UUID) -> Optional[Dict[str, Any]]:
    """Get an attachment by ID from MongoDB. Returns dict for compatibility."""
    return await AttachmentRepository.get_by_id(attachment_id)


async def list_conversation_attachments(
    db: AsyncSession,
    conversation_id: UUID
) -> List[Dict[str, Any]]:
    """List all attachments for a conversation from MongoDB. Returns list of dicts for compatibility."""
    return await AttachmentRepository.list_by_conversation(conversation_id)


async def list_thread_attachments(
    db: AsyncSession,
    thread_id: UUID
) -> List[Dict[str, Any]]:
    """List all attachments for a thread from MongoDB. Returns list of dicts for compatibility."""
    return await ThreadAttachmentRepository.list_by_thread(thread_id)


async def create_thread_attachment(
    db: AsyncSession,
    thread_id: UUID,
    attachment_id: UUID,
    thread_message_id: Optional[UUID] = None
) -> Dict[str, Any]:
    """Link an attachment to a thread in MongoDB. Returns dict for compatibility."""
    att_data = {
        'id': uuid.uuid4(),
        'thread_id': thread_id,
        'attachment_id': attachment_id,
        'thread_message_id': thread_message_id
    }
    return await ThreadAttachmentRepository.create(att_data)


async def link_conversation_attachments_to_thread(
    db: AsyncSession,
    thread_id: UUID,
    conversation_id: UUID,
    message_ids: List[UUID]
) -> List[Dict[str, Any]]:
    """Link conversation attachments to a thread when creating thread from conversation. Uses MongoDB."""
    # Get attachments from MongoDB
    all_attachments = await AttachmentRepository.list_by_conversation(conversation_id)
    
    # Filter attachments that belong to the selected messages or are conversation-level
    filtered_attachments = []
    message_id_strs = {str(mid) for mid in message_ids}
    for att in all_attachments:
        att_msg_id = att.get('message_id')
        if att_msg_id and str(att_msg_id) in message_id_strs:
            filtered_attachments.append(att)
        elif not att_msg_id:  # Conversation-level attachment
            filtered_attachments.append(att)
    
    # Create thread attachment links in MongoDB
    thread_attachments = []
    seen_attachment_ids = set()
    for attachment in filtered_attachments:
        att_id = attachment.get('id')
        if att_id and att_id not in seen_attachment_ids:
            att_data = {
                'id': uuid.uuid4(),
                'thread_id': thread_id,
                'attachment_id': att_id,
                'thread_message_id': None  # Can be linked later if needed
            }
            thread_att = await ThreadAttachmentRepository.create(att_data)
            thread_attachments.append(thread_att)
            seen_attachment_ids.add(att_id)
    
    return thread_attachments


# User Profile CRUD Functions
async def create_rd_study(db: AsyncSession, user_id: str, study: RDStudyCreate) -> RDStudy:
    """Create a new R&D study for a user."""
    study_dict = study.dict()
    study_dict['user_id'] = user_id
    db_study = RDStudy(**study_dict)
    db.add(db_study)
    await db.commit()
    await db.refresh(db_study)
    return db_study


async def get_rd_studies(db: AsyncSession, user_id: str) -> List[RDStudy]:
    """Get all R&D studies for a user."""
    result = await db.execute(
        select(RDStudy)
        .where(RDStudy.user_id == user_id)
        .order_by(RDStudy.created_at.desc())
    )
    return list(result.scalars().all())


async def update_rd_study(db: AsyncSession, study_id: UUID, user_id: str, study: RDStudyCreate) -> Optional[RDStudy]:
    """Update an R&D study."""
    result = await db.execute(
        select(RDStudy)
        .where(RDStudy.id == study_id)
        .where(RDStudy.user_id == user_id)
    )
    db_study = result.scalar_one_or_none()
    if not db_study:
        return None
    
    study_dict = study.dict(exclude_unset=True)
    for key, value in study_dict.items():
        setattr(db_study, key, value)
    
    await db.commit()
    await db.refresh(db_study)
    return db_study


async def delete_rd_study(db: AsyncSession, study_id: UUID, user_id: str) -> bool:
    """Delete an R&D study."""
    result = await db.execute(
        select(RDStudy)
        .where(RDStudy.id == study_id)
        .where(RDStudy.user_id == user_id)
    )
    db_study = result.scalar_one_or_none()
    if not db_study:
        return False
    
    await db.delete(db_study)
    await db.commit()
    return True


async def create_iis_study(db: AsyncSession, user_id: str, study: IISStudyCreate) -> IISStudy:
    """Create a new IIS study for a user."""
    study_dict = study.dict()
    study_dict['user_id'] = user_id
    db_study = IISStudy(**study_dict)
    db.add(db_study)
    await db.commit()
    await db.refresh(db_study)
    return db_study


async def get_iis_studies(db: AsyncSession, user_id: str) -> List[IISStudy]:
    """Get all IIS studies for a user."""
    result = await db.execute(
        select(IISStudy)
        .where(IISStudy.user_id == user_id)
        .order_by(IISStudy.created_at.desc())
    )
    return list(result.scalars().all())


async def update_iis_study(db: AsyncSession, study_id: UUID, user_id: str, study: IISStudyCreate) -> Optional[IISStudy]:
    """Update an IIS study."""
    result = await db.execute(
        select(IISStudy)
        .where(IISStudy.id == study_id)
        .where(IISStudy.user_id == user_id)
    )
    db_study = result.scalar_one_or_none()
    if not db_study:
        return None
    
    study_dict = study.dict(exclude_unset=True)
    for key, value in study_dict.items():
        setattr(db_study, key, value)
    
    await db.commit()
    await db.refresh(db_study)
    return db_study


async def delete_iis_study(db: AsyncSession, study_id: UUID, user_id: str) -> bool:
    """Delete an IIS study."""
    result = await db.execute(
        select(IISStudy)
        .where(IISStudy.id == study_id)
        .where(IISStudy.user_id == user_id)
    )
    db_study = result.scalar_one_or_none()
    if not db_study:
        return False
    
    await db.delete(db_study)
    await db.commit()
    return True


async def create_event(db: AsyncSession, user_id: str, event: EventCreate) -> Event:
    """Create a new event for a user."""
    event_dict = event.dict()
    event_dict['user_id'] = user_id
    db_event = Event(**event_dict)
    db.add(db_event)
    await db.commit()
    await db.refresh(db_event)
    return db_event


async def get_events(db: AsyncSession, user_id: str) -> List[Event]:
    """Get all events for a user."""
    result = await db.execute(
        select(Event)
        .where(Event.user_id == user_id)
        .order_by(Event.date_of_event.desc().nullslast(), Event.created_at.desc())
    )
    return list(result.scalars().all())


async def update_event(db: AsyncSession, event_id: UUID, user_id: str, event: EventCreate) -> Optional[Event]:
    """Update an event."""
    result = await db.execute(
        select(Event)
        .where(Event.id == event_id)
        .where(Event.user_id == user_id)
    )
    db_event = result.scalar_one_or_none()
    if not db_event:
        return None
    
    event_dict = event.dict(exclude_unset=True)
    for key, value in event_dict.items():
        setattr(db_event, key, value)
    
    await db.commit()
    await db.refresh(db_event)
    return db_event


async def delete_event(db: AsyncSession, event_id: UUID, user_id: str) -> bool:
    """Delete an event."""
    result = await db.execute(
        select(Event)
        .where(Event.id == event_id)
        .where(Event.user_id == user_id)
    )
    db_event = result.scalar_one_or_none()
    if not db_event:
        return False
    
    await db.delete(db_event)
    await db.commit()
    return True


async def get_user_profile(db: AsyncSession, user_id: str) -> Optional[UserProfile]:
    """Get user profile."""
    result = await db.execute(
        select(UserProfile)
        .where(UserProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def create_or_update_user_profile(db: AsyncSession, user_id: str, profile: UserProfileCreate) -> UserProfile:
    """Create or update user profile."""
    existing = await get_user_profile(db, user_id)
    
    if existing:
        profile_dict = profile.dict(exclude_unset=True)
        for key, value in profile_dict.items():
            setattr(existing, key, value)
        await db.commit()
        await db.refresh(existing)
        return existing
    else:
        profile_dict = profile.dict()
        profile_dict['user_id'] = user_id
        db_profile = UserProfile(**profile_dict)
        db.add(db_profile)
        await db.commit()
        await db.refresh(db_profile)
        return db_profile


# Chat CRUD Functions
async def create_chat_message(db: AsyncSession, user_id: str, message: ChatMessageCreate) -> ChatMessage:
    """Create a new chat message for a user."""
    message_dict = message.dict()
    message_dict['user_id'] = user_id
    db_message = ChatMessage(**message_dict)
    db.add(db_message)
    await db.commit()
    await db.refresh(db_message)
    return db_message


async def get_chat_messages(db: AsyncSession, user_id: str, limit: int = 100, offset: int = 0) -> List[ChatMessage]:
    """Get chat messages for a user."""
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.user_id == user_id)
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.scalars().all())


async def create_chat_document(db: AsyncSession, user_id: str, file_path: str, filename: str, content_type: str, size: int) -> ChatDocument:
    """Create a new chat document for a user."""
    db_document = ChatDocument(
        user_id=user_id,
        file_path=file_path,
        filename=filename,
        content_type=content_type,
        size=size
    )
    db.add(db_document)
    await db.commit()
    await db.refresh(db_document)
    return db_document


async def get_chat_document(db: AsyncSession, document_id: UUID, user_id: str) -> Optional[ChatDocument]:
    """Get a chat document by ID, ensuring it belongs to the user."""
    result = await db.execute(
        select(ChatDocument)
        .where(ChatDocument.id == document_id)
        .where(ChatDocument.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_chat_documents(db: AsyncSession, user_id: str) -> List[ChatDocument]:
    """Get all chat documents for a user."""
    result = await db.execute(
        select(ChatDocument)
        .where(ChatDocument.user_id == user_id)
        .order_by(ChatDocument.uploaded_at.desc())
    )
    return list(result.scalars().all())


async def delete_chat_document(db: AsyncSession, document_id: UUID, user_id: str) -> bool:
    """Delete a chat document, ensuring it belongs to the user."""
    result = await db.execute(
        select(ChatDocument)
        .where(ChatDocument.id == document_id)
        .where(ChatDocument.user_id == user_id)
    )
    db_document = result.scalar_one_or_none()
    if not db_document:
        return False
    
    # Delete the file from disk
    try:
        import os
        if os.path.exists(db_document.file_path):
            os.remove(db_document.file_path)
    except Exception as e:
        logger.exception("Error deleting file: %s", e)
    
    await db.delete(db_document)
    await db.commit()
    return True


async def combine_threads(
    db: AsyncSession,
    thread1_id: UUID,
    thread2_id: UUID,
    target_thread_id: UUID
) -> Optional[Dict[str, Any]]:
    """
    Combine two threads into one. Merges participants, messages, and attachments.
    The target_thread_id is the thread that will be kept (the other will be deleted).
    Returns the combined thread.
    """
    # Integrity rebuild via the compensating-transaction pattern (Mongo here may
    # be standalone, so there is no multi-doc transaction to lean on).
    return await _combine_threads_safe(db, thread1_id, thread2_id, target_thread_id)


def _merge_participants_emails(original_target_emails: List[Any], source_emails) -> List[str]:
    """Merge source emails into the target list (dedup case-insensitively,
    order-preserving) — THR-COMBINE-EMAILS."""
    merged_emails = [str(e).strip() for e in original_target_emails if e]
    seen_lc = {e.lower() for e in merged_emails}
    for e in (source_emails or []):
        es = str(e).strip()
        if es and es.lower() not in seen_lc:
            merged_emails.append(es)
            seen_lc.add(es.lower())
    return merged_emails


async def _copy_missing_thread_participants(
    source_thread_id: UUID, target_thread_id: UUID, created_participant_ids: List[Any]
) -> None:
    """Create on the target any participant rows only the source has. Appends the
    ids of rows it creates into `created_participant_ids` IN PLACE so the caller's
    compensation block can undo partial progress on failure."""
    target_parts = await ThreadParticipantRepository.list_by_thread(target_thread_id)
    source_parts = await ThreadParticipantRepository.list_by_thread(source_thread_id)
    existing_pids = {p.get('participant_id') for p in target_parts}
    for p in source_parts:
        pid = p.get('participant_id')
        if pid and pid not in existing_pids:
            created = await ThreadParticipantRepository.create({
                'id': uuid.uuid4(),
                'thread_id': target_thread_id,
                'participant_id': pid,
                'participant_name': p.get('participant_name'),
                'participant_email': p.get('participant_email'),
                'role': p.get('role', 'participant'),
            })
            created_participant_ids.append(created.get('id'))
            existing_pids.add(pid)


def _thread_merge_meta_updates(target_thread: Dict[str, Any], source_thread: Dict[str, Any]) -> Dict[str, Any]:
    """Merged title/description/priority updates for the target thread — same rules as legacy."""
    meta_updates: Dict[str, Any] = {}
    if target_thread.get('title') != source_thread.get('title'):
        meta_updates['title'] = f"{target_thread.get('title')} / {source_thread.get('title')}"
    t_desc = target_thread.get('description')
    s_desc = source_thread.get('description')
    if t_desc and s_desc and t_desc != s_desc:
        meta_updates['description'] = f"{t_desc}\n\n--- Merged from: {source_thread.get('title')} ---\n{s_desc}"
    elif s_desc and not t_desc:
        meta_updates['description'] = s_desc
    priorities = ['urgent', 'high', 'medium', 'low']
    t_pri = target_thread.get('priority', 'medium')
    s_pri = source_thread.get('priority', 'medium')
    try:
        if priorities.index(s_pri) < priorities.index(t_pri):
            meta_updates['priority'] = s_pri
    except ValueError:
        pass
    return meta_updates


async def _compensate_thread_merge(
    source_thread_id: UUID,
    target_thread_id: UUID,
    created_participant_ids: List[Any],
    original_target_emails: List[Any],
) -> None:
    """Compensate the reversible phase of a failed thread merge."""
    try:
        await ThreadAttachmentRepository.restore_from_merge(source_thread_id, target_thread_id)
        await ThreadMessageRepository.restore_from_merge(source_thread_id, target_thread_id)
        for pid in created_participant_ids:
            await ThreadParticipantRepository.delete_by_id(pid)
        await ThreadRepository.update(target_thread_id, {'participants_emails': original_target_emails})
    finally:
        # Leave the source present-but-hidden + marked 'failed' so nothing
        # half-merged is visible and a re-run is safe. Source NOT deleted.
        await ThreadRepository.update(source_thread_id, {'merge_state': 'failed'})


async def _combine_threads_safe(
    db: AsyncSession,
    thread1_id: UUID,
    thread2_id: UUID,
    target_thread_id: UUID,
) -> Optional[Dict[str, Any]]:
    """Compensating (atomicity-by-rollback) thread combine — COMMS_COMBINE_SAFE.

    Mongo here may be standalone (no multi-doc transactions), so instead of a
    real transaction we:
      1. mark the source 'in_progress' (hidden from list/read/access paths),
      2. perform reversible moves (emails, participant rows, messages,
         attachments, metadata),
      3. only then run the destructive finalize (delete orphan rows + source).
    Any failure in the reversible phase rolls everything back and leaves the
    source present-but-marked 'failed' (still hidden), so nothing half-merged is
    ever visible and a re-run is safe. The source is never deleted on failure.
    """
    thread1 = await ThreadRepository.get_by_id(thread1_id)
    thread2 = await ThreadRepository.get_by_id(thread2_id)
    if not thread1 or not thread2:
        raise ValueError("One or both threads not found")
    if target_thread_id not in [thread1_id, thread2_id]:
        raise ValueError("target_thread_id must be either thread1_id or thread2_id")

    source_thread_id = thread2_id if target_thread_id == thread1_id else thread1_id
    target_thread = thread1 if target_thread_id == thread1_id else thread2
    source_thread = thread2 if target_thread_id == thread1_id else thread1

    original_target_emails = [e for e in (target_thread.get('participants_emails') or [])]

    # 1. Mark source in_progress → hidden from list/read/access paths.
    await ThreadRepository.update(source_thread_id, {
        'merge_state': 'in_progress',
        'merge_target_id': str(target_thread_id),
    })

    created_participant_ids: List[Any] = []
    try:
        # 2. Merge participants_emails into target (dedup, order-preserving) — THR-COMBINE-EMAILS.
        merged_emails = _merge_participants_emails(original_target_emails, source_thread.get('participants_emails'))
        if merged_emails != original_target_emails:
            await ThreadRepository.update(target_thread_id, {'participants_emails': merged_emails})

        # 3. Merge ThreadParticipant dict-rows (create missing on target).
        # NOTE: appends into created_participant_ids in place so a mid-loop
        # failure still leaves the already-created ids visible to the
        # compensation block below.
        await _copy_missing_thread_participants(source_thread_id, target_thread_id, created_participant_ids)

        # 4. Move ALL messages (single update_many, no cap) — THR-COMBINE-1000.
        await ThreadMessageRepository.move_all_to_thread(source_thread_id, target_thread_id)

        # 5. Move ALL attachments.
        await ThreadAttachmentRepository.move_all_to_thread(source_thread_id, target_thread_id)

        # 6. Merge target metadata (title/description/priority) — same rules as legacy.
        meta_updates = _thread_merge_meta_updates(target_thread, source_thread)
        if meta_updates:
            await ThreadRepository.update(target_thread_id, meta_updates)
    except Exception:
        await _compensate_thread_merge(
            source_thread_id, target_thread_id, created_participant_ids, original_target_emails
        )
        raise

    # ---- destructive finalize (only after the reversible phase fully succeeded) ----
    await ThreadParticipantRepository.delete_by_thread(source_thread_id)        # THR-COMBINE-ORPHAN
    await ThreadFromConversationRepository.delete_by_thread(source_thread_id)   # THR-COMBINE-ORPHAN
    await ThreadRepository.delete(source_thread_id)

    return await ThreadRepository.get_by_id(target_thread_id)


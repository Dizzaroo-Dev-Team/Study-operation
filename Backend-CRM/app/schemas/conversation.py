"""Conversation and message Pydantic schemas."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field

from app.models import MessageChannel, MessageDirection, MessageStatus


class ConversationCreate(BaseModel):
    participant_phone: Optional[str] = None
    participant_email: Optional[str] = None  # Legacy: single email (will be converted to participant_emails)
    participant_emails: Optional[List[str]] = None  # Array of email addresses for multiple recipients
    subject: Optional[str] = None
    title: Optional[str] = None
    study_id: Optional[str] = None
    site_id: Optional[str] = None
    is_pinned: Optional[bool] = False
    is_restricted: Optional[bool] = False
    is_confidential: Optional[bool] = False
    created_by: Optional[str] = None
    sponsor_id: Optional[str] = None
    # 'notice_board' is reserved for the system-pinned per-(study, site)
    # board. Regular user-created conversations are 'thread'. Defaulting to
    # 'notice_board' here used to collide with the unique partial-filter
    # index on (site_id, study_id, conversation_type='notice_board').
    conversation_type: str = "thread"  # notice_board | thread


class ConversationResponse(BaseModel):
    id: UUID
    participant_phone: Optional[str] = None
    participant_email: Optional[str] = None  # Primary/legacy email for backward compatibility
    participant_emails: Optional[List[str]] = None  # Array of email addresses for multiple recipients
    subject: Optional[str] = None
    title: Optional[str] = None
    study_id: Optional[str] = None
    site_id: Optional[str] = None
    is_pinned: Optional[str] = 'false'
    is_restricted: Optional[str] = 'false'
    is_confidential: Optional[str] = 'false'
    created_by: Optional[str] = None
    sponsor_id: Optional[str] = None
    conversation_type: str = "notice_board"  # notice_board | thread
    access_level: Optional[str] = 'public'
    privileged_users: Optional[List[str]] = []
    tracker_code: Optional[str] = None
    # AI auto-classification fields (stored on conversation docs in MongoDB)
    ai_category: Optional[str] = None  # ops | admission | sales | support | other
    ai_priority: Optional[str] = None  # low | medium | high | urgent
    ai_sentiment: Optional[str] = None  # negative | neutral | positive
    ai_next_best_action: Optional[str] = None
    # Persisted AI summary (conversation-level)
    ai_summary: Optional[str] = None
    ai_summary_updated_at: Optional[datetime] = None
    # Phase-2: operational state. Inferred lazily on read for legacy docs that
    # never had these set; written explicitly via PATCH /state for new ones.
    status: Optional[str] = None        # 'open' | 'awaiting_reply' | 'awaiting_us' | 'snoozed' | 'resolved' | 'closed'
    owner_user_id: Optional[str] = None # user_id of the CRM user owning the conversation
    owner_name: Optional[str] = None    # cached display name
    due_at: Optional[datetime] = None   # ISO due timestamp
    priority: Optional[str] = None      # 'low' | 'medium' | 'high' | 'urgent'
    snooze_until: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ConversationStateUpdate(BaseModel):
    """Patch the persisted operational state of a conversation. All fields
    optional - only those present are written. Pass ``null`` explicitly to clear."""
    status: Optional[str] = None
    owner_user_id: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: Optional[str] = None
    snooze_until: Optional[datetime] = None


class MessageCreate(BaseModel):
    channel: MessageChannel
    # Cap body length to keep payloads bounded and avoid runaway storage / AI cost.
    # 64 KiB of plain text is far more than any legitimate human-typed message.
    body: str = Field(..., min_length=1, max_length=65536)
    metadata: Optional[Dict[str, Any]] = None


class MessageDecisionUpdate(BaseModel):
    """Toggle a message's 'pinned decision' flag."""
    is_decision: bool


class MessageResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    direction: MessageDirection
    channel: MessageChannel
    body: str
    status: MessageStatus
    provider_message_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    mentioned_emails: Optional[List[str]] = []  # Email addresses mentioned via @email pattern
    is_decision: Optional[bool] = False  # Pinned as a decision/agreement of record
    origin: Optional[str] = "user"  # "user" or "system" - indicates message origin
    event_type: Optional[str] = None  # Event type for system messages (e.g., "cda_sent", "cda_signed")
    is_activity_event: Optional[bool] = False  # True for system activity events, False for user messages
    # AI per-message analysis
    ai_tone: Optional[str] = None
    ai_delta_summary: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None

    class Config:
        from_attributes = True
        json_encoders = {
            UUID: str,
            datetime: lambda v: v.isoformat() if v else None
        }

    @staticmethod
    def _map_message(obj):
        """Map message_metadata field to metadata for response"""
        if hasattr(obj, '__dict__'):
            data = dict(obj.__dict__)
            if 'message_metadata' in data:
                data['metadata'] = data.pop('message_metadata')
            # Remove SQLAlchemy internal attributes
            data = {k: v for k, v in data.items() if not k.startswith('_')}
            return data
        return obj


class ConversationWithMessages(BaseModel):
    id: UUID
    participant_phone: Optional[str] = None
    participant_email: Optional[str] = None
    participant_emails: Optional[List[str]] = None
    subject: Optional[str] = None
    title: Optional[str] = None
    study_id: Optional[str] = None
    site_id: Optional[str] = None
    is_pinned: Optional[str] = 'false'
    is_restricted: Optional[str] = 'false'
    is_confidential: Optional[str] = 'false'
    conversation_type: str = "notice_board"  # notice_board | thread
    tracker_code: Optional[str] = None
    # Same AI fields as ConversationResponse for detail view
    ai_category: Optional[str] = None
    ai_priority: Optional[str] = None
    ai_sentiment: Optional[str] = None
    ai_next_best_action: Optional[str] = None
    ai_summary: Optional[str] = None
    ai_summary_updated_at: Optional[datetime] = None
    # Phase-2 operational state (see ConversationResponse for full docs).
    status: Optional[str] = None
    owner_user_id: Optional[str] = None
    owner_name: Optional[str] = None
    due_at: Optional[datetime] = None
    priority: Optional[str] = None
    snooze_until: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    messages: List[MessageResponse]

    class Config:
        from_attributes = True


class WebhookPayload(BaseModel):
    event_type: str  # "delivery" or "inbound"
    provider_message_id: Optional[str] = None
    conversation_id: Optional[UUID] = None
    channel: Optional[MessageChannel] = None
    body: Optional[str] = None
    from_number: Optional[str] = None
    from_email: Optional[str] = None
    to_number: Optional[str] = None
    to_email: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class WebSocketMessage(BaseModel):
    action: str
    conversation_id: Optional[UUID] = None


class WebSocketEvent(BaseModel):
    conversation_id: UUID
    type: str
    message: Optional[Dict[str, Any]] = None

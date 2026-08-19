"""Conversation, message, attachment, and conversation-level access models."""
import enum
import uuid

from sqlalchemy import JSON, Column, DateTime, Enum as SQLEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class MessageDirection(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"


class MessageChannel(str, enum.Enum):
    SMS = "sms"
    WHATSAPP = "whatsapp"
    EMAIL = "email"


class MessageStatus(str, enum.Enum):
    QUEUED = "queued"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"


class ConversationAccessLevel(str, enum.Enum):
    PUBLIC = "public"
    RESTRICTED = "restricted"
    CONFIDENTIAL = "confidential"


class AccessType(str, enum.Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    participant_phone = Column(String(50), nullable=True)
    participant_email = Column(String(255), nullable=True)  # Primary/legacy email for backward compatibility
    participant_emails = Column(JSON, nullable=True, default=list)  # Array of email addresses for multiple recipients
    subject = Column(String(500), nullable=True)
    title = Column(String(500), nullable=True)
    study_id = Column(String(100), nullable=True)
    site_id = Column(String(100), nullable=True)  # Site ID for site-centric filtering
    conversation_type = Column(String(50), nullable=True, default="notice_board")
    is_pinned = Column(String(10), nullable=False, default='false')
    # Access control fields
    is_restricted = Column(String(10), nullable=False, default='false')  # 'true' or 'false' as string for simplicity
    is_confidential = Column(String(10), nullable=False, default='false')
    created_by = Column(String(255), nullable=True)  # User who created the conversation
    sponsor_id = Column(String(255), nullable=True)  # Sponsor who initiated (if applicable)
    access_level = Column(String(50), nullable=False, default='PUBLIC')  # Use String instead of Enum to avoid case issues
    privileged_users = Column(JSON, nullable=True, default=list)  # List of user IDs with privileged access
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="conversation", cascade="all, delete-orphan")
    access_grants = relationship("ConversationAccess", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    direction = Column(SQLEnum(MessageDirection), nullable=False)
    channel = Column(SQLEnum(MessageChannel), nullable=False)
    body = Column(Text, nullable=False)
    status = Column(SQLEnum(MessageStatus), nullable=False, default=MessageStatus.QUEUED)
    provider_message_id = Column(String(255), nullable=True)
    message_metadata = Column(JSON, nullable=True, default=dict)
    mentioned_emails = Column(JSON, nullable=True, default=list)
    author_id = Column(String(255), nullable=True)  # User who sent the message (user_id)
    author_name = Column(String(255), nullable=True)  # Display name of the sender
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)

    conversation = relationship("Conversation", back_populates="messages")
    attachments = relationship("Attachment", back_populates="message", cascade="all, delete-orphan")


class Attachment(Base):
    __tablename__ = "attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    file_path = Column(String(500), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    checksum = Column(String(64), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    message = relationship("Message", back_populates="attachments")
    conversation = relationship("Conversation", back_populates="attachments")


class ConversationAccess(Base):
    __tablename__ = "conversation_access"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    user_id = Column(String(255), nullable=False)  # Reference to User.user_id
    access_type = Column(SQLEnum(AccessType), nullable=False, default=AccessType.READ)
    granted_by = Column(String(255), nullable=True)  # User who granted access
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    conversation = relationship("Conversation", back_populates="access_grants")
    user = relationship(
        "User",
        back_populates="access_grants",
        primaryjoin="foreign(ConversationAccess.user_id) == User.user_id",
    )


class ThreadFromConversation(Base):
    __tablename__ = "thread_from_conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    source_message_ids = Column(JSON, nullable=False)  # List of message IDs that were used to create thread
    created_by = Column(String(255), nullable=True)  # User who created the thread from conversation
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    thread = relationship("Thread", foreign_keys=[thread_id])
    conversation = relationship("Conversation", foreign_keys=[conversation_id])

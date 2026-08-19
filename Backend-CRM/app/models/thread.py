"""Thread, thread participant, thread message, and thread attachment models."""
import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class Thread(Base):
    __tablename__ = "threads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=True)
    title = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    thread_type = Column(String(50), nullable=False)  # 'issue', 'patient', 'general'
    related_patient_id = Column(String(255), nullable=True)  # Reference to patient/participant
    related_study_id = Column(String(100), nullable=True)  # Reference to study
    site_id = Column(String(100), nullable=True)  # Site ID for site-centric filtering
    status = Column(String(50), nullable=False, default='open')  # 'open', 'in_progress', 'resolved', 'closed'
    priority = Column(String(20), nullable=False, default='medium')  # 'low', 'medium', 'high', 'urgent'
    participants_emails = Column(JSON, nullable=True, default=list)
    visibility_scope = Column(String(50), nullable=False, default='private')  # 'private' or 'site'
    created_by = Column(String(255), nullable=True)  # User who created the thread
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    conversation = relationship("Conversation", foreign_keys=[conversation_id])
    participants = relationship("ThreadParticipant", back_populates="thread", cascade="all, delete-orphan")
    messages = relationship("ThreadMessage", back_populates="thread", cascade="all, delete-orphan")
    attachments = relationship("ThreadAttachment", back_populates="thread", foreign_keys="ThreadAttachment.thread_id", cascade="all, delete-orphan")


class ThreadParticipant(Base):
    __tablename__ = "thread_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    participant_id = Column(String(255), nullable=False)  # User/participant identifier
    participant_name = Column(String(255), nullable=True)  # Display name
    participant_email = Column(String(255), nullable=True)
    role = Column(String(50), nullable=False, default='participant')  # 'creator', 'participant', 'assignee'
    joined_at = Column(DateTime(timezone=True), server_default=func.now())

    thread = relationship("Thread", back_populates="participants")


class ThreadMessage(Base):
    __tablename__ = "thread_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)  # Link to existing message if applicable
    body = Column(Text, nullable=False)
    author_id = Column(String(255), nullable=False)  # User who wrote the message
    author_name = Column(String(255), nullable=True)
    mentioned_emails = Column(JSON, nullable=True, default=list)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    thread = relationship("Thread", back_populates="messages")
    message = relationship("Message", foreign_keys=[message_id])
    attachments = relationship("ThreadAttachment", back_populates="thread_message", cascade="all, delete-orphan")


class ThreadAttachment(Base):
    __tablename__ = "thread_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    thread_id = Column(UUID(as_uuid=True), ForeignKey("threads.id"), nullable=False)
    thread_message_id = Column(UUID(as_uuid=True), ForeignKey("thread_messages.id"), nullable=True)  # Optional: link to specific message
    attachment_id = Column(UUID(as_uuid=True), ForeignKey("attachments.id"), nullable=False)  # Link to the actual attachment
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    thread = relationship("Thread", foreign_keys=[thread_id])
    thread_message = relationship("ThreadMessage", back_populates="attachments")
    attachment = relationship("Attachment", foreign_keys=[attachment_id])

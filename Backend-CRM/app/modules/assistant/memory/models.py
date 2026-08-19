"""Persistence for Orbit derived memory.

Two tables, deliberately separate because they have opposite lifecycles:

  ``assistant_turn``
      RAW buffer of recent assistant turns (one row per user message and per
      final assistant reply). Short rolling TTL — pruned by the nightly job.
      This is the distiller's *food* and the source of the "last time you…"
      recap. Because raw turn text can mention record content, this table lives
      in the guarded/user-scoped world, is user-deletable, and cascades on
      conversation delete — it is NOT a permanent transcript.

  ``assistant_memory``
      DERIVED items — concise, PHI-stripped facts (``preference`` / ``pattern``
      / ``context``). Hard per-user cap enforced on write (evict least-salient).
      This is what loads compactly into Orbit's prompt at session open.

Both inherit the shared ``app.db`` Base so they register on the same metadata as
every other model (``init_db``'s create_all sees them; a parity SQL migration
lives at ``migrations/add_assistant_memory_tables.sql``).
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Derived-memory item kinds (mirrors the auto-memory taxonomy):
#   preference — how the user likes Orbit to behave ("prefers concise answers")
#   pattern    — a recurring working habit ("often asks for task summaries")
#   context    — non-sensitive working context, e.g. a study reference
#                ("usually works in MK-6482") — re-validated against entitlements
#                at load, never a raw record.
MEMORY_TYPES = ("preference", "pattern", "context")


class AssistantTurn(Base):
    """One buffered turn (raw). Rolling TTL; distiller input only."""

    __tablename__ = "assistant_turn"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        # The distiller and the "last session" recap both read by (user, time).
        Index("ix_assistant_turn_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The acting user (users.user_id string, e.g. email) — matches how the
    # session key + audit attribute the actor.
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # 'user' | 'assistant'
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional link to a CRM conversation so deletion can cascade its derived
    # memory (design: delete-conversation removes memory derived from it). Most
    # Orbit turns are not tied to a conversation, so this is nullable.
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AssistantMemory(Base):
    """One derived memory item. Capped per user; PHI-free by construction."""

    __tablename__ = "assistant_memory"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        Index("ix_assistant_memory_user_salience", "user_id", "salience"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    # preference | pattern | context
    type: Mapped[str] = mapped_column(String(16), nullable=False)
    # The concise derived fact. Short by contract (the distiller + PHI filter
    # keep it a single phrase, never a transcript).
    text: Mapped[str] = mapped_column(String(500), nullable=False)
    # Higher = more salient / recently reinforced. Drives eviction order and the
    # load ordering. Bumped on re-observation (merge/de-dup).
    salience: Mapped[float] = mapped_column(Float, default=1.0)
    # How many times this fact was reinforced across distillation runs.
    hits: Mapped[int] = mapped_column(Integer, default=1)
    # For type='context' study references: the entity id to re-validate against
    # the user's current entitlements at load (never surface a lost-access study).
    ref_study_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Provenance: the turn/conversation this was distilled from (cascade delete).
    source_turn_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    source_conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    # User opt-out: an excluded item is never surfaced and never re-derived.
    excluded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

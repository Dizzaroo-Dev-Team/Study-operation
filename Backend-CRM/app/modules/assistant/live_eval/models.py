"""Append-only store for live eval scores (ALCOA+: attributable, timestamped,
original). Code performs INSERTs only — no update or delete path exists in the
application; corrections are new rows. Parity SQL migration:
``migrations/add_live_eval_scores.sql``.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class LiveEvalScore(Base):
    """One scored turn. ``metrics`` holds the per-metric verdicts verbatim:
    [{name, score, passed, reason, applicable}]. Previews are PHI-SCRUBBED
    before storage (this table feeds a dashboard, not the audit trail)."""

    __tablename__ = "live_eval_scores"
    __mapper_args__ = {"eager_defaults": True}
    __table_args__ = (
        Index("ix_live_eval_scores_created", "created_at"),
        Index("ix_live_eval_scores_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # The acting user (same attribution string as the session key / audit rows).
    user_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    session_id: Mapped[str] = mapped_column(String(255), nullable=False)
    # Scrubbed, truncated previews for the dashboard (never raw text).
    message_preview: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    answer_preview: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    # "deterministic_only" | "with_judge"
    scored_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    judge_model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    overall_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    # [{name, score, passed, reason, applicable}]
    metrics: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

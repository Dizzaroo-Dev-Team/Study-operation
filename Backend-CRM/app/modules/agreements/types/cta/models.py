"""CTA-specific SQLAlchemy models.

Retained for back-compat during the workflow rewrite transition:
  - AgreementNegotiationRound: kept so existing imports keep working until the
    old negotiation routes are removed. The underlying DB table is NOT dropped
    by this migration — a follow-up migration handles that once the old routes
    are retired.

New models (CTA workflow rewrite):
  - CTAAssignment: captures who is the internal reviewer and who is the sponsor
    head for a given CTA agreement, plus the PI and designated signer details
    collected at agreement creation time.
  - CTAPlaceholderMapping: one row per detected placeholder token in the
    uploaded DOCX, tracking auto-filled, AI-suggested, and manually confirmed
    values.

Back-compat: ``app.models.agreement`` re-imports AgreementNegotiationRound from
here, and ``app.models.__init__`` re-exports CTAAssignment and
CTAPlaceholderMapping, so callers using ``from app.models import ...`` keep
working.
"""
from __future__ import annotations

import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class AgreementNegotiationRound(Base):
    """One back-and-forth round between sponsor and site during CTA negotiation.

    DEPRECATED — kept only so existing code that imports this class doesn't
    break while the old CTA routes are being phased out. The table will be
    dropped in a follow-up migration once the old routes are retired.
    """

    __tablename__ = "agreement_negotiation_rounds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(UUID(as_uuid=True), ForeignKey("agreements.id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    initiated_by = Column(String(20), nullable=False)  # 'sponsor' | 'site'
    review_document_id = Column(UUID(as_uuid=True), ForeignKey("agreement_review_documents.id"), nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(20), nullable=False, default="in_progress")  # in_progress | submitted | cancelled
    notes = Column(Text, nullable=True)

    agreement = relationship("Agreement", back_populates="negotiation_rounds", foreign_keys=[agreement_id])
    review_document = relationship("AgreementReviewDocument", foreign_keys=[review_document_id])

    __table_args__ = (
        UniqueConstraint("agreement_id", "round_number", name="uq_agreement_negotiation_rounds_agreement_round"),
        {"comment": "DEPRECATED — per-CTA-agreement negotiation rounds (to be dropped after route migration)"},
    )


class CTAAssignment(Base):
    """Per-agreement assignment row for the new CTA workflow.

    Created when the creating user uploads the CTA template and selects:
      - internal_reviewer_user_id: the user who reviews and approves the filled
        document in OnlyOffice before it is sent for external signature.
      - sponsor_head_user_id: the user who provides the final in-app sponsor
        signature after both external signers have completed.
      - pi_name / pi_email: Principal Investigator who signs externally.
      - designated_signer_name / designated_signer_email: the site's designated
        person who also signs externally (in parallel with the PI).

    Exactly one row per agreement (UNIQUE on agreement_id).
    """

    __tablename__ = "cta_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agreements.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    internal_reviewer_user_id = Column(UUID(as_uuid=True), nullable=False)
    sponsor_head_user_id = Column(UUID(as_uuid=True), nullable=False)
    pi_name = Column(String(255), nullable=False)
    pi_email = Column(String(255), nullable=False)
    designated_signer_name = Column(String(255), nullable=False)
    designated_signer_email = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    agreement = relationship(
        "Agreement",
        foreign_keys=[agreement_id],
        backref="cta_assignment",
    )

    __table_args__ = (
        {"comment": "Per-CTA-agreement reviewer/signer assignment (new workflow)"},
    )


class CTAPlaceholderMapping(Base):
    """One row per detected placeholder token in a CTA DOCX.

    Tracks every ``{{token}}`` found in the uploaded template, the source of
    the resolved value (profile auto-fill, AI suggestion, or manual reviewer
    entry), and whether the reviewer has confirmed the mapping before fill.

    Columns:
      - placeholder_token: the raw token string e.g. ``{{pi_name}}``.
      - source: 'profile' | 'ai' | 'manual' — how the resolved value was
        obtained.
      - resolved_value: the final value to substitute into the DOCX. NULL until
        filled or confirmed.
      - ai_suggestion_field: for AI-detected tokens, the field the AI proposed
        mapping to (e.g. ``site_profiles.authorized_signatory_name``).
      - ai_confidence: Gemini confidence score (0.000–1.000). NULL for
        profile-sourced and manually-entered mappings.
      - confirmed_by_reviewer: set True when the reviewer clicks Confirm in
        the placeholder review table (required before fill can proceed).

    UNIQUE on (agreement_id, placeholder_token) — one mapping row per token
    per agreement.
    """

    __tablename__ = "cta_placeholder_mappings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    agreement_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agreements.id", ondelete="CASCADE"),
        nullable=False,
    )
    placeholder_token = Column(String(255), nullable=False)
    source = Column(String(20), nullable=False)  # 'profile' | 'ai' | 'manual'
    resolved_value = Column(Text, nullable=True)
    ai_suggestion_field = Column(String(255), nullable=True)
    ai_confidence = Column(Numeric(4, 3), nullable=True)
    confirmed_by_reviewer = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    agreement = relationship(
        "Agreement",
        foreign_keys=[agreement_id],
        backref="cta_placeholder_mappings",
    )

    __table_args__ = (
        UniqueConstraint(
            "agreement_id",
            "placeholder_token",
            name="uq_cta_placeholder_mappings_agreement_token",
        ),
        Index("ix_cta_placeholder_mappings_agreement_id", "agreement_id"),
        {"comment": "Per-token placeholder mapping rows for CTA DOCX fill workflow"},
    )


__all__ = [
    "AgreementNegotiationRound",
    "CTAAssignment",
    "CTAPlaceholderMapping",
]

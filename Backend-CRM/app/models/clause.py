"""Clause Library models: Clause, ClauseVersion, TemplateClause.

New models that power the clause-composed template builder.  Designed to slot
cleanly next to the existing StudyTemplate / AgreementDocument world:

  Clause           → identity row; one per reusable contract clause
  ClauseVersion    → IMMUTABLE append-only content rows; never UPDATE, only INSERT
  TemplateClause   → ordered composition join between a StudyTemplate (in
                     CLAUSE_COMPOSED mode) and its selected Clause rows

Circular FK between Clause.current_version_id ↔ ClauseVersion.clause_id is
resolved by DEFERRABLE INITIALLY DEFERRED on the clause_versions side (see
migration).  SQLAlchemy uses use_alter=True on the Clause side.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import JSON

from app.db import Base
from app.models._types import EnumValueType


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class LockPolicy(str, enum.Enum):
    """Governs how a clause may be modified inside a template or agreement."""
    STANDARD_LOCKED = "STANDARD_LOCKED"  # Legal text – never editable by users
    EDITABLE        = "EDITABLE"          # Users may customise per-template
    ALTERNATE       = "ALTERNATE"         # Swap-in fallback clause


class ClauseVersionStatus(str, enum.Enum):
    DRAFT    = "DRAFT"    # Being authored; not yet usable in templates
    APPROVED = "APPROVED" # Cleared by legal; can be pinned in templates
    RETIRED  = "RETIRED"  # Superseded; no new pins; existing pins frozen


# ---------------------------------------------------------------------------
# Clause  (identity + metadata)
# ---------------------------------------------------------------------------

class Clause(Base):
    """One reusable contract clause.  Content lives in ClauseVersion rows."""

    __tablename__ = "clauses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title       = Column(String(255), nullable=False)
    category    = Column(String(100), nullable=False)   # e.g. CONFIDENTIALITY, PAYMENT
    description = Column(Text, nullable=True)
    lock_policy = Column(
        EnumValueType(LockPolicy, "clause_lock_policy", 50),
        nullable=False,
        default=LockPolicy.STANDARD_LOCKED,
    )
    # Points to the latest published ClauseVersion.  Set by publish_clause_version().
    # use_alter so SQLAlchemy emits the FK via ALTER TABLE after both tables exist.
    current_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clause_versions.id", use_alter=True, name="fk_clause_current_version"),
        nullable=True,
    )
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # All versions (read-only list; append via service)
    versions = relationship(
        "ClauseVersion",
        foreign_keys="ClauseVersion.clause_id",
        back_populates="clause",
        order_by="ClauseVersion.version_number",
    )
    # Quick access to the latest version object
    current_version = relationship(
        "ClauseVersion",
        foreign_keys=[current_version_id],
    )
    template_clauses = relationship("TemplateClause", back_populates="clause")

    __table_args__ = (
        {"comment": "Reusable contract clause identity rows"},
    )


# ---------------------------------------------------------------------------
# ClauseVersion  (immutable content rows)
# ---------------------------------------------------------------------------

class ClauseVersion(Base):
    """One content snapshot for a Clause.

    NEVER update a published row — only append new versions.  Existing
    TemplateClause.pinned_clause_version_id and generated AgreementDocument
    rows must remain on their pinned version forever.
    """

    __tablename__ = "clause_versions"

    id             = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    clause_id      = Column(UUID(as_uuid=True), ForeignKey("clauses.id"), nullable=False)
    version_number = Column(Integer, nullable=False)
    # Full Tiptap JSON doc: {"type": "doc", "content": [...block nodes...]}
    content_json   = Column(JSON, nullable=False)
    status         = Column(
        EnumValueType(ClauseVersionStatus, "clause_version_status", 20),
        nullable=False,
        default=ClauseVersionStatus.DRAFT,
    )
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    clause = relationship(
        "Clause",
        back_populates="versions",
        foreign_keys=[clause_id],
    )

    __table_args__ = (
        UniqueConstraint("clause_id", "version_number", name="uq_clause_version"),
        {"comment": "Immutable append-only clause content versions"},
    )


# ---------------------------------------------------------------------------
# TemplateClause  (ordered composition join)
# ---------------------------------------------------------------------------

class TemplateClause(Base):
    """Ordered link between a CLAUSE_COMPOSED StudyTemplate and a Clause.

    sort_order determines the visual / generated order.
    pinned_clause_version_id freezes the exact content used; if NULL the
    materializer falls back to clause.current_version_id.
    override_content_json stores per-template edits for EDITABLE clauses
    without creating a new ClauseVersion (changes are template-local only).
    """

    __tablename__ = "template_clauses"

    id                      = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id             = Column(UUID(as_uuid=True), ForeignKey("study_templates.id"), nullable=False)
    clause_id               = Column(UUID(as_uuid=True), ForeignKey("clauses.id"), nullable=False)
    pinned_clause_version_id = Column(
        UUID(as_uuid=True),
        ForeignKey("clause_versions.id"),
        nullable=True,
    )
    sort_order              = Column(Integer, nullable=False, default=0)
    # String booleans follow the repo convention used in AgreementDocument etc.
    is_locked               = Column(String(10), nullable=False, default="true")
    is_editable             = Column(String(10), nullable=False, default="false")
    # Local content override for EDITABLE clauses; NULL means use pinned version
    override_content_json   = Column(JSON, nullable=True)

    clause         = relationship("Clause", back_populates="template_clauses")
    pinned_version = relationship("ClauseVersion", foreign_keys=[pinned_clause_version_id])

    __table_args__ = (
        UniqueConstraint("template_id", "clause_id", name="uq_template_clause"),
        {"comment": "Ordered clause composition for CLAUSE_COMPOSED study templates"},
    )

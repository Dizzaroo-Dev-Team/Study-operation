from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UUID,
)
from sqlalchemy.orm import relationship

from app.db import Base


class SitePackage(Base):
    """
    SQLAlchemy representation of the SitePackage mongoose schema.

    This is intentionally shaped to produce the same JSON response structure
    as the Fastify/Mongoose version.
    """

    __tablename__ = "site_packages"

    # Use UUID in Postgres and serialize as `_id` in API responses.
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # References
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id"), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)
    # IRB.id is an Integer primary key in `irbs`
    irb_id = Column(Integer, nullable=True)

    # Core fields
    ethicsBoard = Column(String(500), nullable=False)
    packageName = Column(String(500), nullable=True)
    description = Column(Text, nullable=True)
    priority = Column(String(20), nullable=False, default="Medium")
    expectedSubmissionDate = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    contactPerson = Column(JSON, nullable=True)  # {name,email,phone,role}
    documents = Column(JSON, nullable=False, default=list)  # list of document info dicts
    auditTrail = Column(JSON, nullable=False, default=list)  # list of audit entries dicts

    createdBy = Column(String(255), nullable=True)  # User.user_id (string)
    lastUpdated = Column(DateTime(timezone=True), nullable=True)

    status = Column(String(50), nullable=False, default="Draft")
    isDeleted = Column(Boolean, nullable=False, default=False)

    # SQLAlchemy "timestamps"
    createdAt = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updatedAt = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Optional relationships (used for joins/population; not required for JSON)
    # Stored as strings because the existing schema uses UUIDs stored as UUID types;
    # SQLAlchemy will coerce appropriately.
    study = relationship("Study", foreign_keys=[study_id], lazy="joined", innerjoin=False)
    site = relationship("Site", foreign_keys=[site_id], lazy="joined", innerjoin=False)


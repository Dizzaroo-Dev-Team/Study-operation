"""Site status / status-history / site-profile models."""
import enum
import uuid

from sqlalchemy import JSON, Column, DateTime, Enum as SQLEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class PrimarySiteStatus(str, enum.Enum):
    """
    Primary site status enum – source of truth for site lifecycle.

    NOTE: Backed by the Postgres type `site_primary_status` created by
    `create_site_status_tables.py`.
    """

    UNDER_EVALUATION = "UNDER_EVALUATION"
    STARTUP = "STARTUP"
    INITIATING = "INITIATING"
    INITIATED_NOT_RECRUITING = "INITIATED_NOT_RECRUITING"
    RECRUITING = "RECRUITING"
    ACTIVE_NOT_RECRUITING = "ACTIVE_NOT_RECRUITING"
    COMPLETED = "COMPLETED"
    SUSPENDED = "SUSPENDED"
    TERMINATED = "TERMINATED"
    WITHDRAWN = "WITHDRAWN"
    CLOSED = "CLOSED"


class SiteStatus(Base):
    """
    Current primary status per site.

    - Exactly one row per site (DB unique constraint on site_id)
    - Secondary statuses and milestone metadata are stored in `metadata`
    """

    __tablename__ = "site_statuses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False, unique=True)
    current_status = Column(SQLEnum(PrimarySiteStatus, name="site_primary_status"), nullable=False)
    previous_status = Column(SQLEnum(PrimarySiteStatus, name="site_primary_status"), nullable=True)
    # NOTE: attribute name cannot be `metadata` in SQLAlchemy declarative models
    # so we map to a column named "metadata" while using a different attribute.
    status_metadata = Column("metadata", JSON, nullable=True, default=dict)
    effective_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SiteStatusHistory(Base):
    """Immutable audit trail of all site status transitions."""

    __tablename__ = "site_status_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    status = Column(SQLEnum(PrimarySiteStatus, name="site_primary_status"), nullable=False)
    previous_status = Column(SQLEnum(PrimarySiteStatus, name="site_primary_status"), nullable=True)
    status_metadata = Column("metadata", JSON, nullable=True, default=dict)
    triggering_event = Column(String(100), nullable=True)
    reason = Column(Text, nullable=True)
    changed_at = Column(DateTime(timezone=True), server_default=func.now())


class SiteProfile(Base):
    """
    Site Profile model - stores detailed site information.
    One-to-one relationship with Site.
    """

    __tablename__ = "site_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False, unique=True)
    site_name = Column(String(500), nullable=True)
    hospital_name = Column(String(500), nullable=True)
    pi_name = Column(String(255), nullable=True)
    pi_email = Column(String(255), nullable=True)
    pi_phone = Column(String(50), nullable=True)
    pi_designation = Column(String(255), nullable=True)
    pi_department = Column(String(255), nullable=True)
    primary_contracting_entity = Column(String(500), nullable=True)
    authorized_signatory_name = Column(String(255), nullable=True)
    authorized_signatory_email = Column(String(255), nullable=True)
    authorized_signatory_title = Column(String(255), nullable=True)
    address_line_1 = Column(String(500), nullable=True)
    city = Column(String(255), nullable=True)
    state = Column(String(255), nullable=True)
    country = Column(String(255), nullable=True)
    postal_code = Column(String(50), nullable=True)
    site_coordinator_name = Column(String(255), nullable=True)
    site_coordinator_email = Column(String(255), nullable=True)
    site_coordinator_phone = Column(String(50), nullable=True)
    site_head_name = Column(String(255), nullable=True)
    site_head_email = Column(String(255), nullable=True)
    site_head_phone = Column(String(50), nullable=True)
    sub_investigator_name = Column(String(255), nullable=True)
    sub_investigator_email = Column(String(255), nullable=True)
    sub_investigator_phone = Column(String(50), nullable=True)
    sub_investigator_designation = Column(String(255), nullable=True)
    sub_investigator_department = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    site = relationship("Site", backref="profile")

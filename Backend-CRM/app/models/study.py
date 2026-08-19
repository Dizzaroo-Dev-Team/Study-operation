"""Study and study-to-site association models."""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class Study(Base):
    __tablename__ = "studies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id = Column(String(100), unique=True, nullable=False)  # External study identifier
    name = Column(String(500), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), nullable=True)  # 'active', 'completed', 'on_hold', etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class StudySite(Base):
    """
    Mapping table to link studies and sites.
    Allows a single site to participate in multiple studies.
    Used for study-specific workflow steps.
    """
    __tablename__ = "study_sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id"), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    study = relationship("Study", foreign_keys=[study_id])
    site = relationship("Site", foreign_keys=[site_id])

    __table_args__ = (
        UniqueConstraint('study_id', 'site_id', name='uq_study_site'),
        {"comment": "Maps studies to sites, enabling many-to-many relationship for study-specific workflow steps"},
    )

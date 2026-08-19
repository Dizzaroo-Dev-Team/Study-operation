"""HCP / user-profile sub-entities: research studies, events, etc. attached to a user."""
import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db import Base


class RDStudy(Base):
    __tablename__ = "rd_studies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    study_title = Column(String(500), nullable=False)
    nct_number = Column(String(50), nullable=True)
    asset = Column(String(255), nullable=True)
    indication = Column(String(255), nullable=True)
    enrollment = Column(Integer, nullable=True)
    phases = Column(String(50), nullable=True)  # PHASE1, PHASE2, PHASE3, etc.
    start_date = Column(DateTime(timezone=True), nullable=True)
    completion_date = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class IISStudy(Base):
    __tablename__ = "iis_studies"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    study_title = Column(String(500), nullable=False)
    asset = Column(String(255), nullable=True)
    indication = Column(String(255), nullable=True)
    phases = Column(String(50), nullable=True)
    enrollment = Column(Integer, nullable=True)
    enrollment_start_date = Column(DateTime(timezone=True), nullable=True)
    completion_date = Column(DateTime(timezone=True), nullable=True)
    other_associated_hcp_ids = Column(JSON, nullable=True, default=list)  # List of HCP IDs
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Event(Base):
    __tablename__ = "events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    event_name = Column(String(500), nullable=False)
    internal_external = Column(String(20), nullable=False)  # 'Internal' or 'External'
    event_type = Column(String(100), nullable=True)  # 'Adboard', 'Conference', etc.
    date_of_event = Column(DateTime(timezone=True), nullable=True)
    event_description = Column(Text, nullable=True)
    event_report = Column(Text, nullable=True)
    relevant_internal_stakeholders = Column(JSON, nullable=True, default=list)  # List of stakeholder names/IDs
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

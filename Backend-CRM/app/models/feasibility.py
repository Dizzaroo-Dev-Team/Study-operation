"""Feasibility questionnaire models (Postgres side; MongoDB data lives elsewhere)."""
import enum
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class FeasibilityRequestStatus(str, enum.Enum):
    """Status of a feasibility request."""
    SENT = "sent"
    COMPLETED = "completed"


class ProjectFeasibilityCustomQuestion(Base):
    """
    Custom feasibility questions added by users in CRM.
    These are stored in CRM DB only (not in external MongoDB).
    Linked to study/project and workflow step.
    """
    __tablename__ = "project_feasibility_custom_questions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id"), nullable=False)  # Links to Study
    workflow_step = Column(String(50), nullable=False, default="feasibility")

    # Question fields
    question_text = Column(Text, nullable=False)
    section = Column(String(255), nullable=True)  # Optional section grouping
    expected_response_type = Column(String(50), nullable=True)  # e.g., "text", "number", "yes_no"
    display_order = Column(Integer, nullable=False, default=0)  # For ordering questions

    # Metadata
    created_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    study = relationship("Study", foreign_keys=[study_id])


class FeasibilityRequest(Base):
    """
    Feasibility request sent to external users.
    Contains a secure token for accessing the public form.
    """
    __tablename__ = "feasibility_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_site_id = Column(UUID(as_uuid=True), ForeignKey("study_sites.id"), nullable=False)
    email = Column(String(255), nullable=False)
    token = Column(String(255), unique=True, nullable=False, index=True)  # Secure token for form access
    status = Column(String(50), nullable=False, default=FeasibilityRequestStatus.SENT.value)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    study_site = relationship("StudySite", foreign_keys=[study_site_id])
    responses = relationship("FeasibilityResponse", back_populates="request", cascade="all, delete-orphan")


class FeasibilityResponse(Base):
    """
    Response to a feasibility request.
    Stores answers to feasibility questions.
    """
    __tablename__ = "feasibility_responses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id = Column(UUID(as_uuid=True), ForeignKey("feasibility_requests.id"), nullable=False)
    question_text = Column(Text, nullable=False)  # Store question text for reference
    question_id = Column(UUID(as_uuid=True), nullable=True)  # Reference to custom question if applicable
    answer = Column(Text, nullable=False)  # Store answer as text (can be JSON for complex answers)
    section = Column(String(255), nullable=True)  # Section grouping
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    request = relationship("FeasibilityRequest", back_populates="responses")


class FeasibilityAttachment(Base):
    """
    Protocol Synopsis attachment for feasibility requests.
    Scoped to a (study_id + site_id) combination via study_site_id.
    """
    __tablename__ = "feasibility_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    study_site_id = Column(UUID(as_uuid=True), ForeignKey("study_sites.id"), nullable=False, unique=True)  # One attachment per study_site
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    uploaded_by = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    study_site = relationship("StudySite", foreign_keys=[study_site_id])

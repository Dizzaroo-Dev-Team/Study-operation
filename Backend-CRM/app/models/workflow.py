"""Site workflow step models and the document-category enums shared with site_document.py."""
import enum
import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base
from app.models._types import EnumValueType


class WorkflowStepName(str, enum.Enum):
    """Workflow step names for Under Consideration stage."""
    SITE_IDENTIFICATION = "site_identification"
    CDA_EXECUTION = "cda_execution"
    FEASIBILITY = "feasibility"
    SITE_SELECTION_OUTCOME = "site_selection_outcome"


class StepStatus(str, enum.Enum):
    """Status of a workflow step."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    LOCKED = "locked"


class DocumentCategory(str, enum.Enum):
    """Categories for site documents."""
    INVESTIGATOR_CV = "investigator_cv"
    SIGNED_CDA = "signed_cda"
    CTA = "cta"
    IRB_PACKAGE = "irb_package"
    FEASIBILITY_QUESTIONNAIRE = "feasibility_questionnaire"
    FEASIBILITY_RESPONSE = "feasibility_response"
    ONSITE_VISIT_REPORT = "onsite_visit_report"
    SITE_VISIBILITY_REPORT = "site_visibility_report"
    OTHER = "other"


class DocumentType(str, enum.Enum):
    """Type of document: sponsor-provided or site-uploaded."""
    SPONSOR = "sponsor"
    SITE = "site"


class ReviewStatus(str, enum.Enum):
    """Review status for site-uploaded documents."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class SiteWorkflowStep(Base):
    """
    Workflow step state per site for sequential action-based workflows.

    For study-specific steps (Site Identification, CDA, Feasibility, Site Visit),
    this uses study_site_id to scope steps to a (study + site) combination.
    For other steps, site_id is used directly.
    """
    __tablename__ = "site_workflow_steps"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)  # Nullable for study-specific steps
    study_site_id = Column(UUID(as_uuid=True), ForeignKey("study_sites.id"), nullable=True)  # For study-specific steps
    step_name = Column(EnumValueType(WorkflowStepName, "workflow_step_name", 50), nullable=False)
    status = Column(EnumValueType(StepStatus, "step_status", 50), nullable=False, default=StepStatus.NOT_STARTED)
    step_data = Column(JSON, nullable=True, default=dict)  # Flexible JSON storage for step-specific data
    completed_at = Column(DateTime(timezone=True), nullable=True)
    completed_by = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    site = relationship("Site", foreign_keys=[site_id])
    study_site = relationship("StudySite", foreign_keys=[study_site_id])

    __table_args__ = (
        {"comment": "Workflow steps. Study-specific steps (site_identification, cda_execution, feasibility) use study_site_id. Others use site_id."}
    )

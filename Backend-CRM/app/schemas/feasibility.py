"""Feasibility questionnaire, request, and response schemas."""
from datetime import datetime
from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field


class FeasibilityQuestion(BaseModel):
    """Single question in a feasibility questionnaire."""
    text: str = Field(..., description="Question text")
    section: Optional[str] = Field(None, description="Section name for grouping")
    type: str = Field(..., description="Expected response type (e.g., 'text', 'number', 'yes_no')")
    source: str = Field(..., description="Source: 'external' (from MongoDB) or 'custom' (CRM-added)")
    criterion_reference: Optional[str] = Field(None, description="Reference to criterion/source document")
    display_order: Optional[int] = Field(0, description="Display order for sorting")
    id: Optional[UUID] = Field(None, description="Question ID (only for custom questions)")


class FeasibilityQuestionnaireResponse(BaseModel):
    """Response containing merged external and custom questions."""
    project_id: str = Field(..., description="Project/Study ID")
    questions: List[FeasibilityQuestion] = Field(default_factory=list, description="Merged list of questions")


class CustomQuestionCreate(BaseModel):
    """Schema for creating a custom feasibility question."""
    study_id: Union[UUID, str]  # Accept UUID or study_id/name string
    question_text: str
    section: Optional[str] = None
    expected_response_type: Optional[str] = "text"
    display_order: Optional[int] = 0


class CustomQuestionUpdate(BaseModel):
    """Schema for updating a custom feasibility question."""
    question_text: Optional[str] = None
    section: Optional[str] = None
    expected_response_type: Optional[str] = None
    display_order: Optional[int] = None


class CustomQuestionResponse(BaseModel):
    """Response schema for custom question."""
    id: UUID
    study_id: UUID
    workflow_step: str
    question_text: str
    section: Optional[str] = None
    expected_response_type: Optional[str] = None
    display_order: int
    created_by: Optional[str] = None


class FeasibilityRequestCreate(BaseModel):
    """Schema for creating a feasibility request."""
    study_site_id: UUID
    email: Optional[str] = Field(None, description="Email address to send the form link to. If not provided, uses FEASIBILITY_DEFAULT_EMAIL from environment.")
    expires_in_days: Optional[int] = Field(30, description="Number of days until token expires")


class FeasibilityRequestResponse(BaseModel):
    """Response schema for feasibility request."""
    id: UUID
    study_site_id: UUID
    email: str
    token: str
    status: str
    expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class FeasibilityFormQuestion(BaseModel):
    """Question schema for the public form."""
    text: str
    section: Optional[str] = None
    type: str
    id: Optional[UUID] = None
    display_order: Optional[int] = 0


class FeasibilityAttachmentResponse(BaseModel):
    """Schema for feasibility attachment."""
    id: UUID
    study_site_id: UUID
    file_name: str
    file_path: str
    content_type: str
    size: int
    uploaded_by: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class FeasibilityFormResponse(BaseModel):
    """Response schema for the public form (questions + study/site info)."""
    request_id: UUID
    study_name: str
    site_name: str
    questions: List[FeasibilityFormQuestion]
    protocol_synopsis: Optional[FeasibilityAttachmentResponse] = None


class FeasibilityAnswerSubmit(BaseModel):
    """Schema for submitting a single answer."""
    question_text: str
    question_id: Optional[UUID] = None
    answer: str
    section: Optional[str] = None


class FeasibilityFormSubmit(BaseModel):
    """Schema for submitting the complete form."""
    token: str
    answers: List[FeasibilityAnswerSubmit]


class FeasibilityResponseDisplay(BaseModel):
    """Schema for displaying a response."""
    id: UUID
    question_text: str
    answer: str
    section: Optional[str] = None
    created_at: datetime


class FeasibilityResponsesDisplay(BaseModel):
    """Schema for displaying all responses for a study_site."""
    study_site_id: UUID
    request_id: UUID
    email: str
    status: str
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None
    responses: List[FeasibilityResponseDisplay]

    class Config:
        from_attributes = True

"""Thread, thread participant/message/attachment, and thread similarity schemas."""
from datetime import datetime
from typing import List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.attachment import AttachmentResponse


class ThreadParticipantCreate(BaseModel):
    participant_id: str
    participant_name: Optional[str] = None
    participant_email: Optional[str] = None
    role: str = "participant"


class ThreadParticipantResponse(BaseModel):
    id: UUID
    thread_id: UUID
    participant_id: str
    participant_name: Optional[str] = None
    participant_email: Optional[str] = None
    role: str
    joined_at: datetime

    class Config:
        from_attributes = True


class ThreadMessageCreate(BaseModel):
    body: str
    author_id: str
    author_name: Optional[str] = None
    message_id: Optional[UUID] = None  # Link to existing message if applicable
    message_type: Optional[str] = None  # 'system' or None (regular message)


class ThreadMessageResponse(BaseModel):
    id: UUID
    thread_id: UUID
    message_id: Optional[UUID] = None
    body: str
    author_id: str
    author_name: Optional[str] = None
    mentioned_emails: Optional[List[str]] = []  # Email addresses mentioned via @email pattern
    created_at: datetime
    message_type: Optional[str] = None  # 'system' or None (regular message)

    class Config:
        from_attributes = True


class CreateThreadFromConversationRequest(BaseModel):
    title: str
    description: Optional[str] = None
    thread_type: str = Field(..., pattern="^(issue|patient|general)$")
    message_ids: List[UUID]
    created_by: Optional[str] = None
    related_study_id: Optional[str] = None
    # NEW: Thread visibility and participants for private threads
    visibility_scope: Optional[str] = Field(
        default="private",
        description="Thread visibility scope: 'private' or 'site'"
    )
    participants_emails: Optional[List[str]] = Field(
        default=None,
        description="Email-based participants to include in the thread"
    )


class ThreadCreate(BaseModel):
    conversation_id: Optional[UUID] = None  # Optional: threads can be created independently
    title: str
    description: Optional[str] = None
    thread_type: str = "general"  # 'issue', 'patient', 'general', 'agreement'
    related_patient_id: Optional[str] = None
    related_study_id: Optional[str] = None
    site_id: Optional[str] = None
    priority: str = "medium"  # 'low', 'medium', 'high', 'urgent'
    created_by: Optional[str] = None
    participants: Optional[List[ThreadParticipantCreate]] = []
    participants_emails: Optional[List[str]] = []  # List of participant email addresses for access control
    visibility_scope: Optional[str] = "private"  # 'private' or 'site' - controls thread visibility
    agreement_type: Optional[str] = None  # 'CDA', 'CTA', etc.


class ThreadResponse(BaseModel):
    id: UUID
    conversation_id: Union[UUID, None] = None  # Optional: threads can be independent
    title: str
    description: Optional[str] = None
    thread_type: str
    related_patient_id: Optional[str] = None
    related_study_id: Optional[str] = None
    site_id: Optional[str] = None
    status: str
    priority: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    participants: List[ThreadParticipantResponse] = []
    participants_emails: Optional[List[str]] = []  # List of participant email addresses for access control
    visibility_scope: Optional[str] = "private"  # 'private' or 'site' - controls thread visibility
    tmf_filed: Optional[bool] = False
    tmf_filed_at: Optional[datetime] = None
    conversation_address: Optional[str] = None
    agreement_type: Optional[str] = None  # 'CDA', 'CTA', etc.

    class Config:
        from_attributes = True


class ThreadWithMessages(BaseModel):
    id: UUID
    conversation_id: Union[UUID, None] = None  # Optional: threads can be independent
    title: str
    description: Optional[str] = None
    thread_type: str
    related_patient_id: Optional[str] = None
    related_study_id: Optional[str] = None
    status: str
    priority: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    participants: List[ThreadParticipantResponse] = []
    participants_emails: Optional[List[str]] = []  # List of participant email addresses for access control
    messages: List[ThreadMessageResponse] = []
    tmf_filed: Optional[bool] = False
    tmf_filed_at: Optional[datetime] = None
    conversation_address: Optional[str] = None
    agreement_type: Optional[str] = None  # 'CDA', 'CTA', etc.

    class Config:
        from_attributes = True


class ThreadAttachmentResponse(BaseModel):
    id: UUID
    thread_id: UUID
    thread_message_id: Optional[UUID] = None
    attachment_id: UUID
    created_at: datetime
    attachment: Optional[AttachmentResponse] = None  # Include full attachment details

    class Config:
        from_attributes = True


class ThreadSimilarityAnalysis(BaseModel):
    thread1_id: UUID
    thread2_id: UUID
    should_combine: bool
    similarity_score: float
    reasoning: str
    factors: List[str]
    recommendation: str  # "strong", "moderate", "weak", "no"


class ThreadCombinationSuggestion(BaseModel):
    thread1_id: UUID
    thread2_id: UUID
    thread1_title: str
    thread2_title: str
    should_combine: bool
    similarity_score: float
    reasoning: str
    factors: List[str]
    recommendation: str


class CombineThreadsRequest(BaseModel):
    thread1_id: UUID
    thread2_id: UUID
    target_thread_id: UUID  # Which thread to keep (merge the other into this one)

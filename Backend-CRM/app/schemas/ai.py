"""AI-related Pydantic request/response schemas."""
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class AIComposeReplyRequest(BaseModel):
    """Request body for /api/ai/compose-reply."""
    conversation_id: Optional[UUID] = None
    thread_id: Optional[UUID] = None
    latest_draft: Optional[str] = None


class AIComposeReplyDrafts(BaseModel):
    professional: str
    short: str
    detailed: str


class AIComposeReplyResponse(BaseModel):
    drafts: AIComposeReplyDrafts
    summary: str
    facts: List[str]


class AICheckMessageIssue(BaseModel):
    type: str
    message: str


class AICheckMessageRequest(BaseModel):
    """Request body for /api/ai/check-message."""
    conversation_id: Optional[UUID] = None
    thread_id: Optional[UUID] = None
    draft_body: str
    attachments: List[str] = []


class AICheckMessageResponse(BaseModel):
    issues: List[AICheckMessageIssue]
    okToSend: bool


class ResearchPaperSummary(BaseModel):
    title: str
    link: str
    snippet: str
    source: Optional[str] = None

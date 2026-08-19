"""Private AI chat schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ChatMessageCreate(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str
    mode: str = "general"  # 'general' or 'document'
    document_id: Optional[UUID] = None


class ChatMessageResponse(BaseModel):
    id: UUID
    user_id: str
    role: str
    content: str
    mode: str
    document_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ChatDocumentResponse(BaseModel):
    id: UUID
    user_id: str
    filename: str
    content_type: str
    size: int
    uploaded_at: datetime

    class Config:
        from_attributes = True

"""Attachment schemas."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class AttachmentResponse(BaseModel):
    id: UUID
    message_id: Optional[UUID] = None
    conversation_id: UUID
    file_path: str
    content_type: str
    size: int
    checksum: Optional[str] = None
    uploaded_at: datetime
    file_name: Optional[str] = None  # Extracted from file_path

    class Config:
        from_attributes = True

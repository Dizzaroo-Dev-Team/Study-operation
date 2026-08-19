"""Site document schemas."""
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel


class SiteDocumentResponse(BaseModel):
    id: UUID
    site_id: str
    category: str
    file_name: str
    content_type: str
    size: int
    uploaded_by: Optional[str] = None
    uploaded_at: datetime
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = {}
    document_type: Optional[str] = None  # "sponsor" | "site"
    review_status: Optional[str] = None  # "pending" | "approved" | "rejected"
    tmf_filed: Optional[str] = "false"  # "true" | "false"

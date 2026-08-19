"""Site document storage (Site Master File)."""
import uuid

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from app.db import Base
from app.models._types import EnumValueType
from app.models.workflow import DocumentCategory, DocumentType, ReviewStatus


class SiteDocument(Base):
    """
    Document storage per site - acts as Site Master File.
    Documents persist regardless of site status changes.
    """
    __tablename__ = "site_documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    category = Column(EnumValueType(DocumentCategory, "document_category", 50), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_name = Column(String(255), nullable=False)
    content_type = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    uploaded_by = Column(String(255), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())
    description = Column(Text, nullable=True)
    # NOTE: attribute name cannot be `metadata` in SQLAlchemy declarative models
    # so we map to a column named "metadata" while using a different attribute.
    document_metadata = Column("metadata", JSON, nullable=True, default=dict)
    # New fields for sponsor/site document workflow
    document_type = Column(EnumValueType(DocumentType, "document_type", 20), nullable=True, default=DocumentType.SITE)
    review_status = Column(EnumValueType(ReviewStatus, "review_status", 20), nullable=True, default=ReviewStatus.PENDING)
    tmf_filed = Column(String(10), nullable=False, default='false')  # 'true' or 'false' as string

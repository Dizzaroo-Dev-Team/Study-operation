"""Agreement workflow schemas: templates, agreements, comments, documents, signing."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class StudyTemplateCreate(BaseModel):
    """Schema for creating a study template."""
    study_id: UUID
    template_name: str
    template_type: str  # TemplateType enum value
    template_content: dict  # TipTap JSON content


class StudyTemplateResponse(BaseModel):
    """Schema for study template response."""
    id: UUID
    study_id: UUID
    template_name: str
    template_type: str
    template_content: Optional[dict] = None  # TipTap JSON content (legacy, nullable for DOCX-only templates)
    template_file_path: Optional[str] = None  # Blob name (Azure) or local path
    template_file_url: Optional[str] = None  # Azure Blob Storage URL
    placeholder_config: Optional[Dict[str, Dict[str, bool]]] = None  # Placeholder editability config
    field_mappings: Optional[Dict[str, str]] = None  # Dynamic field mappings: {"PLACEHOLDER_NAME": "data_source.field_name"}
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_active: str  # 'true' or 'false'
    composition_mode: Optional[str] = None  # 'DOCX_UPLOAD' or 'CLAUSE_COMPOSED'
    clause_insertions: Optional[List[Dict[str, Any]]] = None  # Clause Builder anchor list

    class Config:
        from_attributes = True


class PlaceholderConfigUpdate(BaseModel):
    """Schema for updating placeholder configuration."""
    placeholder_config: Dict[str, Dict[str, bool]]  # {"PLACEHOLDER_NAME": {"editable": true/false}}


class FieldMappingsUpdate(BaseModel):
    """Schema for updating field mappings."""
    field_mappings: Dict[str, str]  # {"PLACEHOLDER_NAME": "data_source.field_name"}


class AgreementDocumentResponse(BaseModel):
    """Schema for agreement document response."""
    id: UUID
    agreement_id: UUID
    version_number: int
    document_content: Optional[dict] = None  # TipTap JSON content (legacy, nullable for DOCX-only documents)
    document_file_path: Optional[str] = None  # Blob name (Azure) or local path
    document_file_url: Optional[str] = None  # Azure Blob Storage URL
    created_from_template_id: Optional[UUID] = None
    created_by: Optional[str] = None
    created_at: datetime
    is_signed_version: str  # 'true' or 'false'

    class Config:
        from_attributes = True


class AgreementCommentResponse(BaseModel):
    """Schema for agreement comment response."""
    id: UUID
    agreement_id: UUID
    version_id: Optional[UUID] = None
    comment_type: str  # CommentType enum value
    content: str
    created_by: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class AgreementSignedDocumentResponse(BaseModel):
    """Schema for signed document response."""
    id: UUID
    agreement_id: UUID
    file_path: Optional[str] = None
    signed_at: Optional[datetime] = None
    downloaded_from_zoho_at: Optional[datetime] = None
    zoho_request_id: Optional[str] = None

    class Config:
        from_attributes = True


class AgreementCreate(BaseModel):
    """Schema for creating a new agreement."""
    title: str
    status: str  # AgreementStatus enum value
    template_id: Optional[UUID] = None  # Required for new agreements


class AgreementStatusUpdate(BaseModel):
    """Schema for updating agreement status."""
    status: str  # AgreementStatus enum value


class AgreementCommentCreate(BaseModel):
    """Schema for creating an agreement comment."""
    comment_type: str  # CommentType enum value (INTERNAL, EXTERNAL)
    content: str
    version_id: Optional[UUID] = None  # Optional: attach to specific version


class DocumentSaveRequest(BaseModel):
    """Schema for saving document content."""
    document_content: dict  # TipTap JSON content


class AgreementOtpSendRequest(BaseModel):
    agreement_id: UUID
    token: str


class AgreementOtpSignRequest(BaseModel):
    agreement_id: UUID
    token: str
    otp: str = Field(..., min_length=6, max_length=6)
    # Signer's typed name. Renders into the visible signature image and into
    # the "Name:" / "Title:" labels of the signature block. Optional only for
    # backward compatibility with older callers — new UI requires it.
    signer_name: Optional[str] = Field(default=None, max_length=255)
    signer_title: Optional[str] = Field(default=None, max_length=255)
    message: Optional[str] = None


class AgreementSigningLinkSendRequest(BaseModel):
    recipient_email: str
    message: Optional[str] = None


class AgreementResponse(BaseModel):
    """Schema for agreement response."""
    id: UUID
    site_id: UUID
    title: str
    agreement_type: Optional[str] = None  # CDA, CTA, BUDGET, OTHER
    status: str  # AgreementStatus enum value
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    is_legacy: str  # 'true' or 'false'
    documents: List[AgreementDocumentResponse] = []
    comments: List[AgreementCommentResponse] = []
    can_upload_new_version: bool = False
    can_edit: bool = False
    can_comment: bool = False
    can_save: bool = False
    can_move_status: bool = False
    is_locked: bool = False
    current_document_version_number: Optional[int] = None
    zoho_request_id: Optional[str] = None
    signature_status: Optional[str] = None
    signature_source: Optional[str] = None
    signing_stage: Optional[str] = None
    signing_progress: dict = {}
    signed_documents: List[AgreementSignedDocumentResponse] = []

    class Config:
        from_attributes = True

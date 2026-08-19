from pydantic import BaseModel, Field, HttpUrl
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from bson import ObjectId
from ..utils.common import PyObjectId


class DocumentType(str, Enum):
    PROTOCOL = "PROTOCOL"
    INVESTIGATOR_BROCHURE = "INVESTIGATOR_BROCHURE"
    INFORMED_CONSENT = "INFORMED_CONSENT"
    REGULATORY_DOCUMENT = "REGULATORY_DOCUMENT"
    CLINICAL_REPORT = "CLINICAL_REPORT"
    SAFETY_REPORT = "SAFETY_REPORT"
    QUALITY_DOCUMENT = "QUALITY_DOCUMENT"
    TRAINING_DOCUMENT = "TRAINING_DOCUMENT"
    OTHER = "OTHER"


class DocumentStatus(str, Enum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    IN_QC = "IN_QC"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ARCHIVED = "ARCHIVED"
    EXPIRED = "EXPIRED"
    RETIRED = "RETIRED"


class QualityControlStatus(str, Enum):
    PENDING = "PENDING"
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_REQUIRED = "NOT_REQUIRED"


class CompletenessStatus(str, Enum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    PENDING_REVIEW = "PENDING_REVIEW"


class ArchivalStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    PENDING_ARCHIVAL = "PENDING_ARCHIVAL"


class AccessLevel(str, Enum):
    PUBLIC = "PUBLIC"
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"


class RelationshipType(str, Enum):
    PARENT = "PARENT"
    CHILD = "CHILD"
    PREDECESSOR = "PREDECESSOR"
    SUCCESSOR = "SUCCESSOR"
    REFERENCE = "REFERENCE"


class RegulatoryAuthority(str, Enum):
    FDA = "FDA"
    EMA = "EMA"
    OTHER = "OTHER"


class GCPComplianceStatus(str, Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    PENDING_REVIEW = "PENDING_REVIEW"


class LegibilityClear(str, Enum):
    CLEAR = "CLEAR"
    UNCLEAR = "UNCLEAR"


# Embedded Models
class Approver(BaseModel):
    user: PyObjectId
    approved_at: Optional[datetime] = None
    signature: Optional[str] = None
    comments: Optional[str] = None


class RelatedDocument(BaseModel):
    document_id: PyObjectId
    relationship_type: RelationshipType


class SecuritySettings(BaseModel):
    access_level: AccessLevel = AccessLevel.RESTRICTED
    allowed_roles: List[str] = []


class RetentionRequirements(BaseModel):
    duration: Optional[int] = None  # in years
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None


class PreviousVersion(BaseModel):
    version: int
    file_url: str
    uploaded_at: datetime
    uploaded_by: PyObjectId
    change_summary: Optional[str] = None


class WorkflowSummary(BaseModel):
    lifecycle_state: str
    review_overall_status: str
    approval_overall_status: str
    metrics: Dict[str, Any] = {}
    last_transition_at: Optional[datetime] = None


class AuditTrail(BaseModel):
    action: str
    timestamp: datetime
    user: str
    details: Optional[Dict[str, Any]] = None
    ip_address: Optional[str] = None


class MetadataSanitization(BaseModel):
    actions: List[str] = []
    warnings: List[str] = []
    detected_mime_type: Optional[str] = None
    declared_mime_type: Optional[str] = None
    sanitized_at: Optional[datetime] = None
    original_size: Optional[int] = None
    sanitized_size: Optional[int] = None


# Main Models
class ISFDocumentBase(BaseModel):
    document_id: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    document_type: DocumentType
    tmf_reference: str = Field(..., min_length=1)
    version: int = 1
    study: Optional[str] = None
    country: Optional[str] = None
    site: Optional[str] = None
    file_url: str = Field(..., min_length=1)
    file_size: int = Field(..., gt=0)
    mime_type: Optional[str] = None
    file_hash: Optional[str] = None
    file_hash_algorithm: str = "SHA-256"
    metadata_sanitization: Optional[MetadataSanitization] = None
    page_count: Optional[int] = None
    legibility_clear: Optional[LegibilityClear] = None
    ingestion_type: str = "Manual"
    language: str = "en"
    document_date: datetime
    creation_date: datetime = Field(default_factory=datetime.utcnow)
    modification_date: datetime = Field(default_factory=datetime.utcnow)
    import_date: datetime = Field(default_factory=datetime.utcnow)
    approval_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    author: Optional[PyObjectId] = None
    contributors: List[PyObjectId] = []
    approvers: List[Approver] = []
    uploaded_by: Optional[PyObjectId] = None
    status: DocumentStatus = DocumentStatus.DRAFT
    quality_control_status: QualityControlStatus = QualityControlStatus.PENDING
    completeness_status: CompletenessStatus = CompletenessStatus.PENDING_REVIEW
    archival_status: ArchivalStatus = ArchivalStatus.ACTIVE
    security_settings: SecuritySettings = Field(default_factory=SecuritySettings)
    related_documents: List[RelatedDocument] = []
    regulatory_authority: Optional[RegulatoryAuthority] = None
    gcp_compliance_status: GCPComplianceStatus = GCPComplianceStatus.PENDING_REVIEW
    retention_requirements: Optional[RetentionRequirements] = None
    previous_versions: List[PreviousVersion] = []
    workflow_ref: Optional[PyObjectId] = None
    workflow_summary: Optional[WorkflowSummary] = None
    audit_trail: List[AuditTrail] = []
    tags: List[str] = []
    custom_metadata: Dict[str, Any] = {}
    zone: Optional[PyObjectId] = None
    section: Optional[PyObjectId] = None
    artifact: Optional[PyObjectId] = None
    sub_artifact: Optional[PyObjectId] = None
    created_by: PyObjectId
    last_modified_by: Optional[PyObjectId] = None


class ISFDocumentCreate(ISFDocumentBase):
    pass


class ISFDocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    document_type: Optional[DocumentType] = None
    tmf_reference: Optional[str] = Field(None, min_length=1)
    study: Optional[str] = None
    country: Optional[str] = None
    site: Optional[str] = None
    file_url: Optional[str] = Field(None, min_length=1)
    file_size: Optional[int] = Field(None, gt=0)
    mime_type: Optional[str] = None
    page_count: Optional[int] = None
    legibility_clear: Optional[LegibilityClear] = None
    language: Optional[str] = None
    document_date: Optional[datetime] = None
    approval_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    author: Optional[PyObjectId] = None
    contributors: Optional[List[PyObjectId]] = None
    approvers: Optional[List[Approver]] = None
    status: Optional[DocumentStatus] = None
    quality_control_status: Optional[QualityControlStatus] = None
    completeness_status: Optional[CompletenessStatus] = None
    archival_status: Optional[ArchivalStatus] = None
    security_settings: Optional[SecuritySettings] = None
    related_documents: Optional[List[RelatedDocument]] = None
    regulatory_authority: Optional[RegulatoryAuthority] = None
    gcp_compliance_status: Optional[GCPComplianceStatus] = None
    retention_requirements: Optional[RetentionRequirements] = None
    tags: Optional[List[str]] = None
    custom_metadata: Optional[Dict[str, Any]] = None
    zone: Optional[PyObjectId] = None
    section: Optional[PyObjectId] = None
    artifact: Optional[PyObjectId] = None
    sub_artifact: Optional[PyObjectId] = None
    last_modified_by: Optional[PyObjectId] = None


class ISFDocumentInDB(ISFDocumentBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    
    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str
        }


class ISFDocumentResponse(BaseModel):
    id: str
    document_id: str
    title: str
    description: Optional[str] = None
    document_type: DocumentType
    tmf_reference: str
    version: int
    study: Optional[str] = None
    country: Optional[str] = None
    site: Optional[str] = None
    file_url: str
    file_size: int
    mime_type: Optional[str] = None
    file_hash: Optional[str] = None
    page_count: Optional[int] = None
    legibility_clear: Optional[LegibilityClear] = None
    ingestion_type: str
    language: str
    document_date: datetime
    creation_date: datetime
    modification_date: datetime
    import_date: datetime
    approval_date: Optional[datetime] = None
    expiration_date: Optional[datetime] = None
    author: Optional[str] = None
    contributors: List[str] = []
    approvers: List[Approver] = []
    uploaded_by: Optional[str] = None
    status: DocumentStatus
    quality_control_status: QualityControlStatus
    completeness_status: CompletenessStatus
    archival_status: ArchivalStatus
    security_settings: SecuritySettings
    related_documents: List[RelatedDocument] = []
    regulatory_authority: Optional[RegulatoryAuthority] = None
    gcp_compliance_status: GCPComplianceStatus
    retention_requirements: Optional[RetentionRequirements] = None
    previous_versions: List[PreviousVersion] = []
    workflow_summary: Optional[WorkflowSummary] = None
    audit_trail: List[AuditTrail] = []
    tags: List[str] = []
    custom_metadata: Dict[str, Any] = {}
    zone: Optional[str] = None
    section: Optional[str] = None
    artifact: Optional[str] = None
    sub_artifact: Optional[str] = None
    created_by: str
    last_modified_by: Optional[str] = None
    
    class Config:
        json_encoders = {
            ObjectId: str
        }

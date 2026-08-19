from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ContactPerson(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    role: Optional[str] = None


class DocumentInfo(BaseModel):
    name: str
    fileUrl: str
    fileSize: int
    mimeType: str
    uploadedAt: Optional[datetime] = None
    uploadedBy: Optional[str] = None
    tmfDocumentId: Optional[str] = None
    source: Optional[str] = None


class AuditTrailItem(BaseModel):
    action: str
    user: Optional[str] = None
    timestamp: Optional[datetime] = None
    details: Optional[Any] = None


class SitePackageCreateRequest(BaseModel):
    study: str
    # Required: packages are always scoped to a site + study (workspace context).
    site: str
    # Backward-compatible: frontend now derives Ethics Board from IRB automatically
    # and sends `irb_id`; we still tolerate the old `ethicsBoard` payload.
    ethicsBoard: Optional[str] = None
    irb_id: Optional[int] = None
    packageName: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = "Medium"
    submissionType: Optional[str] = None
    expectedSubmissionDate: Optional[datetime] = None
    contactPerson: Optional[ContactPerson] = Field(default_factory=dict)
    notes: Optional[str] = None
    documents: Optional[List[Dict[str, Any]]] = Field(default_factory=list)
    createdBy: Optional[str] = None  # tolerated for dev parity


class SitePackageUpdateRequest(BaseModel):
    ethicsBoard: Optional[str] = None
    irb_id: Optional[int] = None
    packageName: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    submissionType: Optional[str] = None
    expectedSubmissionDate: Optional[datetime] = None
    contactPerson: Optional[ContactPerson] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    documents: Optional[List[Dict[str, Any]]] = None


class SitePackageListResponsePagination(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class SitePackageListQuery(BaseModel):
    page: int = 1
    limit: int = 20
    study: Optional[str] = None
    site: Optional[str] = None
    status: Optional[str] = None


class StandardErrorResponse(BaseModel):
    success: bool = False
    error: str


class SitePackageCreateResponse(BaseModel):
    success: bool = True
    data: Dict[str, Any]
    message: str


class SitePackageSingleResponse(BaseModel):
    success: bool
    data: Dict[str, Any]


class SitePackageListResponse(BaseModel):
    success: bool
    data: List[Dict[str, Any]]
    pagination: SitePackageListResponsePagination


class UploadDocumentResponseData(BaseModel):
    name: str
    fileUrl: str
    fileSize: int
    mimeType: str


class UploadDocumentResponse(BaseModel):
    success: bool
    data: UploadDocumentResponseData


class UploadSitePackageDocumentResponse(BaseModel):
    success: bool
    data: Dict[str, Any]  # { document, package }
    message: str


class PresignRequest(BaseModel):
    fileUrl: str


class PresignResponse(BaseModel):
    success: bool
    presignedUrl: str


class ProtocolMetadataExtractRequest(BaseModel):
    fileUrl: str
    maxPages: Optional[int] = 5


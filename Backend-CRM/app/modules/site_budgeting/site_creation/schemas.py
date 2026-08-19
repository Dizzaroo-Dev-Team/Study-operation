"""
Pydantic schemas for site creation module.
Mirrors the validation defined in the Node.js Fastify route schemas exactly.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Facility schemas ─────────────────────────────────────────────────────────

class FacilityAddress(BaseModel):
    street: str
    addressLine2: Optional[str] = None
    city: str
    state: Optional[str] = None
    country: str
    postalCode: str


class FacilityDepartment(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None


class FacilityCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    facilityType: str  # HOSPITAL | CLINIC | RESEARCH_CENTER | PHYSICIAN_OFFICE | OTHER
    facilityId: Optional[str] = None
    campusName: Optional[str] = None
    address: FacilityAddress
    department: Optional[FacilityDepartment] = None
    status: str = "ACTIVE"  # ACTIVE | INACTIVE | ARCHIVED


class FacilityUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=2, max_length=100)
    facilityType: Optional[str] = None
    campusName: Optional[str] = None
    address: Optional[FacilityAddress] = None
    department: Optional[FacilityDepartment] = None
    status: Optional[str] = None


# ─── Site schemas ─────────────────────────────────────────────────────────────

class SitePersonnelItem(BaseModel):
    user: str
    role: str


class RegulatoryApprovalItem(BaseModel):
    type: str  # IRB | EC | FDA | EMA | OTHER
    approvalNumber: Optional[str] = None
    approvalDate: Optional[str] = None
    expiryDate: Optional[str] = None
    status: str = "PENDING"  # PENDING | APPROVED | EXPIRED | SUSPENDED


class MonitoringData(BaseModel):
    visitFrequency: Optional[str] = "MONTHLY"
    monitor: Optional[str] = None


class QualityMetrics(BaseModel):
    protocolCompliance: Optional[float] = None
    dataQuality: Optional[float] = None
    subjectRetention: Optional[float] = None


class SiteCreate(BaseModel):
    siteCode: Optional[str] = None
    study: str  # ObjectId string or studyId string
    facility: str  # ObjectId string (24-char hex)
    principalInvestigator: str  # ObjectId string
    status: str = "PENDING"  # ACTIVE | PENDING | COMPLETED | SUSPENDED | TERMINATED
    sitePersonnel: Optional[List[SitePersonnelItem]] = []
    regulatoryApprovals: Optional[List[RegulatoryApprovalItem]] = []
    monitoring: Optional[MonitoringData] = None
    qualityMetrics: Optional[QualityMetrics] = None
    metadata: Optional[Dict[str, Any]] = {}


class SiteUpdate(BaseModel):
    siteCode: Optional[str] = None
    study: Optional[str] = None
    facility: Optional[str] = None
    principalInvestigator: Optional[str] = None
    status: Optional[str] = None
    sitePersonnel: Optional[List[SitePersonnelItem]] = None
    regulatoryApprovals: Optional[List[RegulatoryApprovalItem]] = None
    monitoring: Optional[MonitoringData] = None
    qualityMetrics: Optional[QualityMetrics] = None
    metadata: Optional[Dict[str, Any]] = None


class AddPersonnelBody(BaseModel):
    userId: str
    role: str

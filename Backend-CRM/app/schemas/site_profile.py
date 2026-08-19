"""Site profile schemas (detailed site information)."""
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SiteProfileCreate(BaseModel):
    """Schema for creating a site profile."""
    site_name: Optional[str] = None
    hospital_name: Optional[str] = None
    pi_name: Optional[str] = None
    pi_email: Optional[str] = None
    pi_phone: Optional[str] = None
    pi_designation: Optional[str] = None
    pi_department: Optional[str] = None
    primary_contracting_entity: Optional[str] = None
    authorized_signatory_name: Optional[str] = None
    authorized_signatory_email: Optional[str] = None
    authorized_signatory_title: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    site_coordinator_name: Optional[str] = None
    site_coordinator_email: Optional[str] = None
    site_coordinator_phone: Optional[str] = None
    site_head_name: Optional[str] = None
    site_head_email: Optional[str] = None
    site_head_phone: Optional[str] = None
    sub_investigator_name: Optional[str] = None
    sub_investigator_email: Optional[str] = None
    sub_investigator_phone: Optional[str] = None
    sub_investigator_designation: Optional[str] = None
    sub_investigator_department: Optional[str] = None


class SiteProfileUpdate(BaseModel):
    """Schema for updating a site profile."""
    site_name: Optional[str] = None
    hospital_name: Optional[str] = None
    pi_name: Optional[str] = None
    pi_email: Optional[str] = None
    pi_phone: Optional[str] = None
    pi_designation: Optional[str] = None
    pi_department: Optional[str] = None
    primary_contracting_entity: Optional[str] = None
    authorized_signatory_name: Optional[str] = None
    authorized_signatory_email: Optional[str] = None
    authorized_signatory_title: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    site_coordinator_name: Optional[str] = None
    site_coordinator_email: Optional[str] = None
    site_coordinator_phone: Optional[str] = None
    site_head_name: Optional[str] = None
    site_head_email: Optional[str] = None
    site_head_phone: Optional[str] = None
    sub_investigator_name: Optional[str] = None
    sub_investigator_email: Optional[str] = None
    sub_investigator_phone: Optional[str] = None
    sub_investigator_designation: Optional[str] = None
    sub_investigator_department: Optional[str] = None


class SiteProfileResponse(BaseModel):
    """Schema for site profile response."""
    id: UUID
    site_id: UUID
    site_name: Optional[str] = None
    hospital_name: Optional[str] = None
    pi_name: Optional[str] = None
    pi_email: Optional[str] = None
    pi_phone: Optional[str] = None
    pi_designation: Optional[str] = None
    pi_department: Optional[str] = None
    primary_contracting_entity: Optional[str] = None
    authorized_signatory_name: Optional[str] = None
    authorized_signatory_email: Optional[str] = None
    authorized_signatory_title: Optional[str] = None
    address_line_1: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    postal_code: Optional[str] = None
    site_coordinator_name: Optional[str] = None
    site_coordinator_email: Optional[str] = None
    site_coordinator_phone: Optional[str] = None
    site_head_name: Optional[str] = None
    site_head_email: Optional[str] = None
    site_head_phone: Optional[str] = None
    sub_investigator_name: Optional[str] = None
    sub_investigator_email: Optional[str] = None
    sub_investigator_phone: Optional[str] = None
    sub_investigator_designation: Optional[str] = None
    sub_investigator_department: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

"""User-profile sub-entity schemas: RD studies, IIS studies, events, profile."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class RDStudyCreate(BaseModel):
    study_title: str
    nct_number: Optional[str] = None
    asset: Optional[str] = None
    indication: Optional[str] = None
    enrollment: Optional[int] = None
    phases: Optional[str] = None
    start_date: Optional[datetime] = None
    completion_date: Optional[datetime] = None


class RDStudyResponse(BaseModel):
    id: UUID
    user_id: str
    study_title: str
    nct_number: Optional[str] = None
    asset: Optional[str] = None
    indication: Optional[str] = None
    enrollment: Optional[int] = None
    phases: Optional[str] = None
    start_date: Optional[datetime] = None
    completion_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class IISStudyCreate(BaseModel):
    study_title: str
    asset: Optional[str] = None
    indication: Optional[str] = None
    phases: Optional[str] = None
    enrollment: Optional[int] = None
    enrollment_start_date: Optional[datetime] = None
    completion_date: Optional[datetime] = None
    other_associated_hcp_ids: Optional[List[str]] = []


class IISStudyResponse(BaseModel):
    id: UUID
    user_id: str
    study_title: str
    asset: Optional[str] = None
    indication: Optional[str] = None
    phases: Optional[str] = None
    enrollment: Optional[int] = None
    enrollment_start_date: Optional[datetime] = None
    completion_date: Optional[datetime] = None
    other_associated_hcp_ids: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EventCreate(BaseModel):
    event_name: str
    internal_external: str  # 'Internal' or 'External'
    event_type: Optional[str] = None
    date_of_event: Optional[datetime] = None
    event_description: Optional[str] = None
    event_report: Optional[str] = None
    relevant_internal_stakeholders: Optional[List[str]] = []


class EventResponse(BaseModel):
    id: UUID
    user_id: str
    event_name: str
    internal_external: str
    event_type: Optional[str] = None
    date_of_event: Optional[datetime] = None
    event_description: Optional[str] = None
    event_report: Optional[str] = None
    relevant_internal_stakeholders: Optional[List[str]] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class UserProfileCreate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None
    specialty: Optional[str] = None


class UserProfileResponse(BaseModel):
    id: UUID
    user_id: str
    name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    affiliation: Optional[str] = None
    specialty: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

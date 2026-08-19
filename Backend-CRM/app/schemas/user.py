"""User auth, signup/login, and access-control schemas."""
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class UserCreate(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None  # For signup
    role: str = "participant"
    is_privileged: bool = False


class UserSignup(BaseModel):
    user_id: str
    name: Optional[str] = None
    email: str
    password: str
    role: str = "participant"


class UserLogin(BaseModel):
    email: str
    password: str


class Token(BaseModel):
    access_token: str
    token_type: str
    user: dict


class UserResponse(BaseModel):
    id: UUID
    user_id: str
    name: Optional[str] = None
    email: Optional[str] = None
    role: str
    is_privileged: str
    created_at: datetime

    class Config:
        from_attributes = True


class ConversationAccessCreate(BaseModel):
    user_id: str
    access_type: str = "read"  # 'read', 'write', 'admin'
    granted_by: Optional[str] = None


class ConversationAccessResponse(BaseModel):
    id: UUID
    conversation_id: UUID
    user_id: str
    access_type: str
    granted_by: Optional[str] = None
    granted_at: datetime

    class Config:
        from_attributes = True


class UpdateConversationAccessRequest(BaseModel):
    is_restricted: Optional[bool] = None
    is_confidential: Optional[bool] = None
    privileged_users: Optional[List[str]] = None


class GrantAccessRequest(BaseModel):
    user_id: str
    access_type: str = "read"  # 'read', 'write', 'admin'


class UserRoleAssignmentCreate(BaseModel):
    user_id: str
    role: str  # 'cra', 'study_manager', 'medical_monitor'
    site_id: Optional[UUID] = None
    study_id: Optional[UUID] = None


class UserRoleAssignmentResponse(BaseModel):
    id: UUID
    user_id: str
    role: str
    site_id: Optional[UUID] = None
    study_id: Optional[UUID] = None
    assigned_by: Optional[str] = None
    assigned_at: datetime
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

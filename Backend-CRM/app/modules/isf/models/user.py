from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import datetime
from enum import Enum
from bson import ObjectId
from ..utils.common import PyObjectId


class UserRole(str, Enum):
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    STUDY_LEAD = "STUDY_LEAD"
    SITE_MANAGER = "SITE_MANAGER"
    DATA_MANAGER = "DATA_MANAGER"
    QC_LEAD = "QC_LEAD"
    REVIEWER = "REVIEWER"
    APPROVER = "APPROVER"
    USER = "USER"


class UserBase(BaseModel):
    user_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    role: UserRole
    permissions: List[str] = []
    assigned_studies: List[str] = []
    is_active: bool = True


class UserCreate(UserBase):
    pass


class UserUpdate(BaseModel):
    user_name: Optional[str] = Field(None, min_length=1, max_length=100)
    email: Optional[EmailStr] = None
    role: Optional[UserRole] = None
    permissions: Optional[List[str]] = None
    assigned_studies: Optional[List[str]] = None
    is_active: Optional[bool] = None


class UserInDB(UserBase):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        populate_by_name = True
        json_encoders = {
            ObjectId: str
        }


class UserResponse(BaseModel):
    id: str
    user_name: str
    email: str
    role: UserRole
    permissions: List[str] = []
    assigned_studies: List[str] = []
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        json_encoders = {
            ObjectId: str
        }

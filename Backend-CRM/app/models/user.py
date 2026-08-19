"""User, role, and user-to-site/study assignment models."""
import enum
import uuid

from sqlalchemy import Column, DateTime, Enum as SQLEnum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class UserRole(str, enum.Enum):
    SPONSOR = "sponsor"
    SITE_MANAGER = "site_manager"
    COORDINATOR = "coordinator"
    PARTICIPANT = "participant"
    CRA = "cra"  # Clinical Research Associate
    STUDY_MANAGER = "study_manager"  # Study Manager
    MEDICAL_MONITOR = "medical_monitor"  # Medical Monitor


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), unique=True, nullable=False)  # Unique identifier (email, username, etc.)
    name = Column(String(255), nullable=True)
    email = Column(String(255), nullable=True, unique=True)  # Email should be unique for login
    password_hash = Column(String(255), nullable=True)  # Hashed password for authentication
    role = Column(SQLEnum(UserRole), nullable=False, default=UserRole.PARTICIPANT)
    is_privileged = Column(String(10), nullable=False, default='false')  # Can manage confidential conversations
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    access_grants = relationship(
        "ConversationAccess",
        back_populates="user",
        primaryjoin="User.user_id == foreign(ConversationAccess.user_id)",
    )


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey("users.user_id"), unique=True, nullable=False)
    name = Column(String(255), nullable=True)
    address = Column(Text, nullable=True)
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    affiliation = Column(String(500), nullable=True)
    specialty = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id], primaryjoin="UserProfile.user_id == User.user_id")


class UserSite(Base):
    __tablename__ = "user_sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=False)
    role = Column(String(50), nullable=True)  # 'principal_investigator', 'coordinator', 'monitor', etc.
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", foreign_keys=[user_id])
    site = relationship("Site", back_populates="user_associations")


class UserRoleAssignment(Base):
    """
    Links users to roles (CRA, Study Manager, Medical Monitor) with specific site/study access.

    Access rules:
    - CRA: Has access to specific sites and studies assigned to them
    - Study Manager: Has site-level access, so all studies in assigned sites are accessible
    - Medical Monitor: Same as CRA - has access to specific sites and studies assigned
    """
    __tablename__ = "user_role_assignments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), ForeignKey("users.user_id"), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)  # CRA, STUDY_MANAGER, or MEDICAL_MONITOR
    site_id = Column(UUID(as_uuid=True), ForeignKey("sites.id"), nullable=True)  # Optional: for site-level access
    study_id = Column(UUID(as_uuid=True), ForeignKey("studies.id"), nullable=True)  # Optional: for study-level access
    assigned_by = Column(String(255), nullable=True)  # User who assigned this role
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", foreign_keys=[user_id])
    site = relationship("Site", foreign_keys=[site_id])
    study = relationship("Study", foreign_keys=[study_id])

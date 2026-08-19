"""Site model (the trial-site entity)."""
import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.db import Base


class Site(Base):
    __tablename__ = "sites"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_id = Column(String(100), unique=True, nullable=False)  # External site identifier
    name = Column(String(500), nullable=False)
    code = Column(String(100), nullable=True)  # Site code
    location = Column(String(500), nullable=True)
    principal_investigator = Column(String(255), nullable=True)  # Display string (kept for legacy reads)
    principal_investigator_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    facility_external_id = Column(UUID(as_uuid=True), nullable=True)  # Links to row in external Azure facilities DB
    address = Column(Text, nullable=True)
    city = Column(String(255), nullable=True)
    country = Column(String(255), nullable=True)
    status = Column(String(50), nullable=True)  # 'active', 'inactive', etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user_associations = relationship("UserSite", back_populates="site", cascade="all, delete-orphan")
    principal_investigator_user = relationship("User", foreign_keys=[principal_investigator_id])

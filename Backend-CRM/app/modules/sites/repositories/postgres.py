"""sites domain repositories (PostgreSQL).

Moved from app/repositories/postgres_repository.py during folder cleanup.
Holds StudyRepository, SiteRepository.
"""
"""
PostgreSQL repository implementations for core CRM entities.
This module contains repositories for PostgreSQL-backed entities (Users, Studies, Sites, etc.).
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from typing import Optional, List
from uuid import UUID
from app.models import (
    User, Study, Site, UserSite, UserProfile, RDStudy, IISStudy, Event,
    ConversationAccess, AuditLog, ChatMessage, ChatDocument, UserRoleAssignment, UserRole, StudySite
)
import logging

logger = logging.getLogger(__name__)



class StudyRepository:
    """Repository for Study entities in PostgreSQL."""
    
    @staticmethod
    async def get_by_study_id(db: AsyncSession, study_id: str) -> Optional[Study]:
        """Get study by study_id (external identifier)."""
        result = await db.execute(select(Study).where(Study.study_id == study_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list(db: AsyncSession, limit: int = 100, offset: int = 0) -> List[Study]:
        """List all studies."""
        result = await db.execute(
            select(Study)
            .order_by(Study.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())



class SiteRepository:
    """Repository for Site entities in PostgreSQL."""
    
    @staticmethod
    async def get_by_site_id(db: AsyncSession, site_id: str) -> Optional[Site]:
        """Get site by site_id (external identifier)."""
        result = await db.execute(select(Site).where(Site.site_id == site_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_by_study(
        db: AsyncSession,
        study_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[Site]:
        """List sites for a study."""
        # First get study by study_id
        study = await StudyRepository.get_by_study_id(db, study_id)
        if not study:
            return []

        result = await db.execute(
            select(Site)
            .join(StudySite, StudySite.site_id == Site.id)
            .where(StudySite.study_id == study.id)
            .order_by(Site.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())




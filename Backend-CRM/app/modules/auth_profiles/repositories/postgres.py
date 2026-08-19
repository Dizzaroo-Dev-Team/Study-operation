"""auth_profiles domain repositories (PostgreSQL).

Moved from app/repositories/postgres_repository.py during folder cleanup.
Holds UserRepository, ConversationAccessRepository, UserRoleAssignmentRepository.
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



class UserRepository:
    """Repository for User entities in PostgreSQL."""
    
    @staticmethod
    async def get_by_id(db: AsyncSession, user_id: str) -> Optional[User]:
        """Get user by user_id."""
        result = await db.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_email(db: AsyncSession, email: str) -> Optional[User]:
        """Get user by email."""
        result = await db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list(db: AsyncSession, limit: int = 100, offset: int = 0) -> List[User]:
        """List all users."""
        result = await db.execute(
            select(User)
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())



class ConversationAccessRepository:
    """Repository for ConversationAccess entities in PostgreSQL."""
    
    @staticmethod
    async def get_by_conversation_and_user(
        db: AsyncSession,
        conversation_id: UUID,
        user_id: str
    ) -> Optional[ConversationAccess]:
        """Get access grant for a user and conversation."""
        result = await db.execute(
            select(ConversationAccess)
            .where(ConversationAccess.conversation_id == conversation_id)
            .where(ConversationAccess.user_id == user_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_by_conversation(
        db: AsyncSession,
        conversation_id: UUID
    ) -> List[ConversationAccess]:
        """List all access grants for a conversation."""
        result = await db.execute(
            select(ConversationAccess)
            .where(ConversationAccess.conversation_id == conversation_id)
        )
        return list(result.scalars().all())



class UserRoleAssignmentRepository:
    """Repository for UserRoleAssignment entities in PostgreSQL."""

    @staticmethod
    def _coerce_role(role_str: Optional[str]) -> Optional[UserRole]:
        if not role_str:
            return None
        return UserRole(str(role_str).strip().lower())

    @staticmethod
    def _rows_to_assignments(rows) -> List[UserRoleAssignment]:
        """Convert raw rows to model-shaped objects without SQLAlchemy enum loading."""
        assignments: List[UserRoleAssignment] = []
        for row in rows:
            role_str = getattr(row, "role_str", None)
            try:
                assignment = UserRoleAssignment(
                    id=row.id,
                    user_id=row.user_id,
                    role=UserRoleAssignmentRepository._coerce_role(role_str),
                    site_id=row.site_id,
                    study_id=row.study_id,
                    assigned_by=row.assigned_by,
                    assigned_at=row.assigned_at,
                    created_at=row.created_at,
                    updated_at=row.updated_at
                )
                assignments.append(assignment)
            except (ValueError, AttributeError) as e:
                logger.warning(f"Skipping invalid role assignment: {e}, role_str={role_str}")
                continue
        return assignments
    
    @staticmethod
    async def create(
        db: AsyncSession,
        user_id: str,
        role: UserRole,
        site_id: Optional[UUID] = None,
        study_id: Optional[UUID] = None,
        assigned_by: Optional[str] = None
    ) -> UserRoleAssignment:
        """Create a new role assignment."""
        assignment = UserRoleAssignment(
            user_id=user_id,
            role=role,
            site_id=site_id,
            study_id=study_id,
            assigned_by=assigned_by
        )
        db.add(assignment)
        await db.flush()
        await db.refresh(assignment)
        return assignment
    
    @staticmethod
    async def get_by_id(db: AsyncSession, assignment_id: UUID) -> Optional[UserRoleAssignment]:
        """Get role assignment by ID."""
        result = await db.execute(
            select(UserRoleAssignment).where(UserRoleAssignment.id == assignment_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def list_by_user(
        db: AsyncSession,
        user_id: str,
        role: Optional[UserRole] = None
    ) -> List[UserRoleAssignment]:
        """List all role assignments for a user, optionally filtered by role."""
        # Use raw SQL to avoid SQLAlchemy enum conversion issues
        # Cast enum to text in query, then convert back to enum in Python
        if role:
            sql = text("""
                SELECT id, user_id, role::text as role_str, site_id, study_id, 
                       assigned_by, assigned_at, created_at, updated_at
                FROM user_role_assignments
                WHERE user_id = :user_id AND LOWER(role::text) = :role_value
                ORDER BY assigned_at DESC
            """)
            result = await db.execute(sql, {
                "user_id": user_id,
                "role_value": role.value if hasattr(role, 'value') else str(role)
            })
        else:
            sql = text("""
                SELECT id, user_id, role::text as role_str, site_id, study_id, 
                       assigned_by, assigned_at, created_at, updated_at
                FROM user_role_assignments
                WHERE user_id = :user_id
                ORDER BY assigned_at DESC
            """)
            result = await db.execute(sql, {"user_id": user_id})
        
        return UserRoleAssignmentRepository._rows_to_assignments(result)
    
    @staticmethod
    async def list_by_site(
        db: AsyncSession,
        site_id: UUID,
        role: Optional[UserRole] = None
    ) -> List[UserRoleAssignment]:
        """List all role assignments for a site, optionally filtered by role."""
        sql = text("""
            SELECT id, user_id, role::text as role_str, site_id, study_id,
                   assigned_by, assigned_at, created_at, updated_at
            FROM user_role_assignments
            WHERE site_id = :site_id
              AND (CAST(:role_value AS text) IS NULL OR LOWER(role::text) = CAST(:role_value AS text))
            ORDER BY assigned_at DESC
        """)
        result = await db.execute(sql, {
            "site_id": site_id,
            "role_value": role.value if role else None,
        })
        return UserRoleAssignmentRepository._rows_to_assignments(result)
    
    @staticmethod
    async def list_by_study(
        db: AsyncSession,
        study_id: UUID,
        role: Optional[UserRole] = None
    ) -> List[UserRoleAssignment]:
        """List all role assignments for a study, optionally filtered by role."""
        sql = text("""
            SELECT id, user_id, role::text as role_str, site_id, study_id,
                   assigned_by, assigned_at, created_at, updated_at
            FROM user_role_assignments
            WHERE study_id = :study_id
              AND (CAST(:role_value AS text) IS NULL OR LOWER(role::text) = CAST(:role_value AS text))
            ORDER BY assigned_at DESC
        """)
        result = await db.execute(sql, {
            "study_id": study_id,
            "role_value": role.value if role else None,
        })
        return UserRoleAssignmentRepository._rows_to_assignments(result)
    
    @staticmethod
    async def delete(db: AsyncSession, assignment_id: UUID) -> bool:
        """Delete a role assignment."""
        assignment = await UserRoleAssignmentRepository.get_by_id(db, assignment_id)
        if assignment:
            await db.delete(assignment)
            await db.flush()
            return True
        return False
    
    @staticmethod
    async def delete_by_user_and_role(
        db: AsyncSession,
        user_id: str,
        role: UserRole,
        site_id: Optional[UUID] = None,
        study_id: Optional[UUID] = None
    ) -> int:
        """Delete role assignments matching criteria. Returns count of deleted assignments."""
        query = select(UserRoleAssignment).where(
            UserRoleAssignment.user_id == user_id,
            UserRoleAssignment.role == role
        )
        if site_id:
            query = query.where(UserRoleAssignment.site_id == site_id)
        if study_id:
            query = query.where(UserRoleAssignment.study_id == study_id)
        
        result = await db.execute(query)
        assignments = list(result.scalars().all())
        count = len(assignments)
        
        for assignment in assignments:
            await db.delete(assignment)
        
        await db.flush()
        return count




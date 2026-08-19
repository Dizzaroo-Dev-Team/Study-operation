"""Clause Library service.

All DB writes flush but never commit — the caller (route handler) commits.
Follows the layer rule: service → ORM, never service → route.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.clause import Clause, ClauseVersion, ClauseVersionStatus, LockPolicy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Clause CRUD
# ---------------------------------------------------------------------------

async def create_clause(
    db: AsyncSession,
    *,
    title: str,
    category: str,
    description: Optional[str],
    lock_policy: LockPolicy,
    created_by: Optional[str],
) -> Clause:
    """Create a Clause identity row.  No version is created here — call
    publish_clause_version() immediately after to add the first version."""
    clause = Clause(
        title=title,
        category=category,
        description=description,
        lock_policy=lock_policy,
        created_by=created_by,
    )
    db.add(clause)
    await db.flush()
    return clause


async def get_clause(db: AsyncSession, clause_id: UUID) -> Optional[Clause]:
    result = await db.execute(
        select(Clause)
        .where(Clause.id == clause_id)
        .options(selectinload(Clause.current_version))
    )
    return result.scalar_one_or_none()


async def search_clauses(
    db: AsyncSession,
    *,
    q: Optional[str] = None,
    category: Optional[str] = None,
) -> List[Clause]:
    """Return clauses filtered by optional free-text search and/or category."""
    stmt = select(Clause).options(selectinload(Clause.current_version)).order_by(Clause.category, Clause.title)
    if category:
        stmt = stmt.where(func.lower(Clause.category) == category.strip().lower())
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Clause.title).like(pattern),
                func.lower(Clause.description).like(pattern),
            )
        )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_clause_metadata(
    db: AsyncSession,
    clause_id: UUID,
    *,
    title: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    lock_policy: Optional[LockPolicy] = None,
) -> Clause:
    """Update clause identity fields only (not content — that goes via a new version)."""
    result = await db.execute(
        select(Clause)
        .where(Clause.id == clause_id)
        .options(selectinload(Clause.current_version))
    )
    clause = result.scalar_one_or_none()
    if clause is None:
        raise ValueError(f"Clause {clause_id} not found")

    if title is not None:
        clause.title = title
    if category is not None:
        clause.category = category
    if description is not None:
        clause.description = description
    if lock_policy is not None:
        clause.lock_policy = lock_policy

    await db.flush()
    return clause


async def delete_clause(db: AsyncSession, clause_id: UUID) -> None:
    """Hard-delete a clause and all its versions.

    Order matters because of the circular FK:
      clauses.current_version_id → clause_versions.id  (forward, nullable)
      clause_versions.clause_id  → clauses.id          (back, NOT NULL, DEFERRABLE)

    1. Delete any template_clauses rows referencing this clause (legacy join table)
    2. Break the forward FK (set current_version_id = NULL, flush)
    3. Delete all child ClauseVersion rows via raw DELETE (avoids ORM SET NULL)
    4. Delete the Clause row

    Note: this does NOT touch StudyTemplate.clause_insertions (a JSON column, not
    an FK). A deleted clause referenced there will simply be skipped at generation.
    """
    from sqlalchemy import delete as sa_delete

    from app.models.clause import TemplateClause

    result = await db.execute(select(Clause).where(Clause.id == clause_id))
    clause = result.scalar_one_or_none()
    if clause is None:
        raise ValueError(f"Clause {clause_id} not found")

    # Step 1: remove legacy join rows that FK to this clause (and its versions)
    await db.execute(sa_delete(TemplateClause).where(TemplateClause.clause_id == clause_id))
    await db.flush()

    # Step 2: break the circular FK so the versions can be deleted
    clause.current_version_id = None
    await db.flush()

    # Step 3: delete all versions (raw SQL — avoids ORM trying to SET NULL on clause_id)
    await db.execute(sa_delete(ClauseVersion).where(ClauseVersion.clause_id == clause_id))
    await db.flush()

    # Step 4: delete the clause itself
    await db.delete(clause)
    await db.flush()


# ---------------------------------------------------------------------------
# Version management
# ---------------------------------------------------------------------------

async def publish_clause_version(
    db: AsyncSession,
    clause_id: UUID,
    *,
    content_json: dict,
    created_by: Optional[str],
    status: ClauseVersionStatus = ClauseVersionStatus.APPROVED,
) -> ClauseVersion:
    """Append a new immutable ClauseVersion and advance clause.current_version_id.

    Version numbering is auto-incremented from the current max.  The caller
    must commit after this call (and any other flushes in the same unit of work).
    """
    result = await db.execute(
        select(Clause)
        .where(Clause.id == clause_id)
        .options(selectinload(Clause.current_version))
    )
    clause = result.scalar_one_or_none()
    if clause is None:
        raise ValueError(f"Clause {clause_id} not found")

    # Next version number
    max_result = await db.execute(
        select(func.max(ClauseVersion.version_number)).where(
            ClauseVersion.clause_id == clause_id
        )
    )
    current_max: Optional[int] = max_result.scalar_one_or_none()
    next_num = (current_max or 0) + 1

    version = ClauseVersion(
        clause_id=clause_id,
        version_number=next_num,
        content_json=content_json,
        status=status,
        created_by=created_by,
    )
    db.add(version)
    await db.flush()  # populate version.id

    # Advance the pointer
    clause.current_version_id = version.id
    await db.flush()

    logger.info(
        "Published ClauseVersion %s v%d (status=%s) for clause %s",
        version.id, next_num, status.value, clause_id,
    )
    return version


async def get_clause_versions(
    db: AsyncSession, clause_id: UUID
) -> List[ClauseVersion]:
    """Return all versions for a clause, ordered ascending."""
    result = await db.execute(
        select(ClauseVersion)
        .where(ClauseVersion.clause_id == clause_id)
        .order_by(ClauseVersion.version_number)
    )
    return list(result.scalars().all())


async def get_clause_version(
    db: AsyncSession, version_id: UUID
) -> Optional[ClauseVersion]:
    result = await db.execute(
        select(ClauseVersion).where(ClauseVersion.id == version_id)
    )
    return result.scalar_one_or_none()

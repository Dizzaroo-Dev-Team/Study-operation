"""REST API: Clause Library CRUD.

Endpoints:
  GET    /clauses                  – search / list clauses
  POST   /clauses                  – create clause + first version
  GET    /clauses/{id}             – get one clause with current version inline
  PATCH  /clauses/{id}             – update clause metadata (not content)
  DELETE /clauses/{id}             – delete clause (hard)
  GET    /clauses/{id}/versions    – list all versions
  POST   /clauses/{id}/versions    – publish a new version
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import get_current_user_optional
from app.db import get_db
from app.models.clause import Clause, ClauseVersionStatus, LockPolicy
from app.modules.agreements.services import clause_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Clause Library"])


# ---------------------------------------------------------------------------
# Pydantic schemas (inline — small surface, no shared schema needed yet)
# ---------------------------------------------------------------------------

class ClauseCreate(BaseModel):
    title:        str
    category:     str
    description:  Optional[str] = None
    lock_policy:  LockPolicy    = LockPolicy.STANDARD_LOCKED
    # Initial version content — required on create so there's always ≥1 version
    content_json: Dict[str, Any]


class ClauseUpdate(BaseModel):
    title:       Optional[str]       = None
    category:    Optional[str]       = None
    description: Optional[str]       = None
    lock_policy: Optional[LockPolicy] = None


class ClauseVersionCreate(BaseModel):
    content_json: Dict[str, Any]
    status:       ClauseVersionStatus = ClauseVersionStatus.APPROVED


class ClauseVersionResponse(BaseModel):
    id:             UUID
    clause_id:      UUID
    version_number: int
    content_json:   Dict[str, Any]
    status:         str
    created_by:     Optional[str] = None
    created_at:     Any

    class Config:
        from_attributes = True


class ClauseResponse(BaseModel):
    id:                 UUID
    title:              str
    category:           str
    description:        Optional[str] = None
    lock_policy:        str
    current_version_id: Optional[UUID] = None
    current_version:    Optional[ClauseVersionResponse] = None
    created_by:         Optional[str] = None
    created_at:         Any
    updated_at:         Any

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_clause(clause: Any, include_version: bool = True) -> dict:
    cv = None
    if include_version and clause.current_version:
        cv = {
            "id":             clause.current_version.id,
            "clause_id":      clause.current_version.clause_id,
            "version_number": clause.current_version.version_number,
            "content_json":   clause.current_version.content_json,
            "status":         clause.current_version.status.value
                              if hasattr(clause.current_version.status, "value")
                              else clause.current_version.status,
            "created_by":     clause.current_version.created_by,
            "created_at":     clause.current_version.created_at,
        }
    return {
        "id":                 clause.id,
        "title":              clause.title,
        "category":           clause.category,
        "description":        clause.description,
        "lock_policy":        clause.lock_policy.value
                              if hasattr(clause.lock_policy, "value")
                              else clause.lock_policy,
        "current_version_id": clause.current_version_id,
        "current_version":    cv,
        "created_by":         clause.created_by,
        "created_at":         clause.created_at,
        "updated_at":         clause.updated_at,
    }


def _serialize_version(cv: Any) -> dict:
    return {
        "id":             cv.id,
        "clause_id":      cv.clause_id,
        "version_number": cv.version_number,
        "content_json":   cv.content_json,
        "status":         cv.status.value if hasattr(cv.status, "value") else cv.status,
        "created_by":     cv.created_by,
        "created_at":     cv.created_at,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/clauses", response_model=List[dict])
async def list_clauses(
    q:        Optional[str] = Query(None, description="Free-text search on title/description"),
    category: Optional[str] = Query(None, description="Exact category filter"),
    db:       AsyncSession  = Depends(get_db),
):
    """Return all clauses, optionally filtered."""
    clauses = await clause_service.search_clauses(db, q=q, category=category)
    return [_serialize_clause(c) for c in clauses]


@router.post("/clauses", status_code=201)
async def create_clause(
    body:         ClauseCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Create a new clause and immediately publish its first version."""
    user_id = (current_user or {}).get("user_id")

    try:
        clause = await clause_service.create_clause(
            db,
            title=body.title,
            category=body.category,
            description=body.description,
            lock_policy=body.lock_policy,
            created_by=user_id,
        )
        await clause_service.publish_clause_version(
            db,
            clause.id,
            content_json=body.content_json,
            created_by=user_id,
            status=ClauseVersionStatus.APPROVED,
        )
        await db.commit()
        # Re-fetch with current_version eagerly loaded (async session can't lazy-load)
        result = await db.execute(
            select(Clause)
            .where(Clause.id == clause.id)
            .options(selectinload(Clause.current_version))
        )
        clause = result.scalar_one()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("create_clause: unexpected error")
        raise HTTPException(status_code=500, detail="Failed to create clause")

    return _serialize_clause(clause)


@router.get("/clauses/{clause_id}")
async def get_clause(
    clause_id: UUID,
    db:        AsyncSession = Depends(get_db),
):
    clause = await clause_service.get_clause(db, clause_id)
    if clause is None:
        raise HTTPException(status_code=404, detail="Clause not found")
    return _serialize_clause(clause)


@router.patch("/clauses/{clause_id}")
async def update_clause(
    clause_id:    UUID,
    body:         ClauseUpdate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Update clause metadata (title, category, description, lock_policy).
    To update content, POST to /clauses/{id}/versions instead."""
    try:
        clause = await clause_service.update_clause_metadata(
            db,
            clause_id,
            title=body.title,
            category=body.category,
            description=body.description,
            lock_policy=body.lock_policy,
        )
        await db.commit()
        result = await db.execute(
            select(Clause)
            .where(Clause.id == clause_id)
            .options(selectinload(Clause.current_version))
        )
        clause = result.scalar_one()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("update_clause: unexpected error")
        raise HTTPException(status_code=500, detail="Failed to update clause")

    return _serialize_clause(clause)


@router.delete("/clauses/{clause_id}", status_code=204)
async def delete_clause(
    clause_id:    UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    try:
        await clause_service.delete_clause(db, clause_id)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("delete_clause: unexpected error")
        raise HTTPException(status_code=500, detail="Failed to delete clause")


@router.get("/clauses/{clause_id}/versions")
async def list_clause_versions(
    clause_id: UUID,
    db:        AsyncSession = Depends(get_db),
):
    clause = await clause_service.get_clause(db, clause_id)
    if clause is None:
        raise HTTPException(status_code=404, detail="Clause not found")
    versions = await clause_service.get_clause_versions(db, clause_id)
    return [_serialize_version(v) for v in versions]


@router.post("/clauses/{clause_id}/versions", status_code=201)
async def publish_clause_version(
    clause_id:    UUID,
    body:         ClauseVersionCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db:           AsyncSession   = Depends(get_db),
):
    """Publish a new immutable version for an existing clause.

    This is an APPEND-ONLY operation — the previous version is never modified.
    The clause's current_version_id advances to point at the new version.
    """
    user_id = (current_user or {}).get("user_id")
    try:
        version = await clause_service.publish_clause_version(
            db,
            clause_id,
            content_json=body.content_json,
            created_by=user_id,
            status=body.status,
        )
        await db.commit()
        await db.refresh(version)
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        await db.rollback()
        logger.exception("publish_clause_version: unexpected error")
        raise HTTPException(status_code=500, detail="Failed to publish version")

    return _serialize_version(version)

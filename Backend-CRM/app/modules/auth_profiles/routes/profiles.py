from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header, Query, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, delete, update
from sqlalchemy.orm import selectinload
from typing import Optional, List
from uuid import UUID
from datetime import timedelta, datetime, timezone
import asyncio
import os
import hashlib
import shutil
from pathlib import Path
import secrets
from app.db import get_db, init_db
from app import crud, schemas
from app.models import MessageDirection, MessageStatus, MessageChannel, ConversationAccessLevel, ThreadAttachment, Attachment, Conversation, ChatDocument, PrimarySiteStatus, UserRoleAssignment, Site, Study, StudySite, SiteStatus, SiteWorkflowStep, SiteDocument, WorkflowStepName, StepStatus, DocumentCategory, DocumentType, ReviewStatus, ProjectFeasibilityCustomQuestion, FeasibilityRequest, FeasibilityResponse, FeasibilityRequestStatus, FeasibilityAttachment
from app.websocket_manager import manager
from app.config import settings
from app.auth import create_access_token, get_password_hash, get_current_user, get_current_user_optional, ACCESS_TOKEN_EXPIRE_MINUTES
from app.modules.sites.services.site_status_service import (
    get_study_status_summary,
    get_country_site_counts,
    get_sites_by_status,
    get_site_status_detail,
)
from app.integrations.ai import ai_service
import uuid
import logging
# Tasks imported where needed to avoid circular imports


router = APIRouter(tags=["Auth", "Profiles"])
logger = logging.getLogger(__name__)

@router.post("/users", response_model=schemas.UserResponse)
async def create_user(
    user: schemas.UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new user."""
    existing = await crud.get_user(db, user.user_id)
    if existing:
        raise HTTPException(status_code=400, detail="User with this user_id already exists")
    return await crud.create_user(db, user)


@router.get("/users", response_model=List[schemas.UserResponse])
async def list_users(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """
    User roster for dropdowns (Principal Investigator, etc.).

    Source of truth is IAM Kafka → Mongo `local_users`. Each listing ensures a
    matching Postgres `users` row exists so FKs (`sites.principal_investigator_id`)
    stay valid — same dual-write policy as the Kafka consumer.
    """
    from app.db.mongo import get_mongo_db
    from app.integrations.kafka.models.sync_models import COLL_LOCAL_USERS

    mongo_db = await get_mongo_db()
    cursor = (
        mongo_db[COLL_LOCAL_USERS]
        .find({})
        .sort([("displayName", 1), ("email", 1)])
        .skip(offset)
        .limit(limit)
    )
    docs = await cursor.to_list(length=limit)

    out: List[schemas.UserResponse] = []
    for doc in docs:
        uid = str(doc.get("_id") or "")
        if not uid:
            continue

        raw_email = doc.get("email")
        email = raw_email.strip() if isinstance(raw_email, str) else None
        if email == "":
            email = None

        display_name = (
            doc.get("displayName")
            or doc.get("name")
            or doc.get("full_name")
            or email
            or uid
        )
        if display_name is not None and not isinstance(display_name, str):
            display_name = str(display_name)

        pg_user = await crud.ensure_postgres_user_for_iam_mirror(
            db,
            user_id=uid,
            email=email,
            display_name=display_name,
        )
        if pg_user is None:
            continue
        out.append(schemas.UserResponse.model_validate(pg_user))

    await db.commit()
    return out


@router.get("/users/{user_id}", response_model=schemas.UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get user by user_id."""
    user = await crud.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# Role Assignment Endpoints
@router.post("/role-assignments", response_model=schemas.UserRoleAssignmentResponse)
async def create_role_assignment(
    assignment: schemas.UserRoleAssignmentCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new role assignment for a user."""
    from app.modules.auth_profiles.repositories import UserRoleAssignmentRepository
    from app.models import UserRole
    
    # Validate role
    try:
        role = UserRole(assignment.role)
        if role not in [UserRole.CRA, UserRole.STUDY_MANAGER, UserRole.MEDICAL_MONITOR]:
            raise HTTPException(
                status_code=400,
                detail="Role must be one of: cra, study_manager, medical_monitor"
            )
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {assignment.role}"
        )
    
    # Validate user exists
    user = await crud.get_user(db, assignment.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Validate site if provided
    if assignment.site_id:
        from app.modules.sites.repositories import SiteRepository
        result = await db.execute(select(Site).where(Site.id == assignment.site_id))
        site = result.scalar_one_or_none()
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
    
    # Validate study if provided
    if assignment.study_id:
        from app.modules.sites.repositories import StudyRepository
        result = await db.execute(select(Study).where(Study.id == assignment.study_id))
        study = result.scalar_one_or_none()
        if not study:
            raise HTTPException(status_code=404, detail="Study not found")
    
    # Create assignment
    role_assignment = await UserRoleAssignmentRepository.create(
        db=db,
        user_id=assignment.user_id,
        role=role,
        site_id=assignment.site_id,
        study_id=assignment.study_id,
        assigned_by=current_user.get("user_id")
    )
    
    await db.commit()
    await db.refresh(role_assignment)
    
    return role_assignment


@router.get("/role-assignments", response_model=List[schemas.UserRoleAssignmentResponse])
async def list_role_assignments(
    user_id: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    site_id: Optional[UUID] = Query(None),
    study_id: Optional[UUID] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """List role assignments with optional filters."""
    from app.modules.auth_profiles.repositories import UserRoleAssignmentRepository
    from app.models import UserRole
    
    if user_id:
        role_filter = None
        if role:
            try:
                role_filter = UserRole(role)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
        
        assignments = await UserRoleAssignmentRepository.list_by_user(db, user_id, role_filter)
    elif site_id:
        role_filter = None
        if role:
            try:
                role_filter = UserRole(role)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
        assignments = await UserRoleAssignmentRepository.list_by_site(db, site_id, role_filter)
    elif study_id:
        role_filter = None
        if role:
            try:
                role_filter = UserRole(role)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid role: {role}")
        assignments = await UserRoleAssignmentRepository.list_by_study(db, study_id, role_filter)
    else:
        # List all assignments (admin only - you may want to add permission check)
        result = await db.execute(select(UserRoleAssignment))
        assignments = list(result.scalars().all())
    
    return assignments


@router.get("/role-assignments/{assignment_id}", response_model=schemas.UserRoleAssignmentResponse)
async def get_role_assignment(
    assignment_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get a role assignment by ID."""
    from app.modules.auth_profiles.repositories import UserRoleAssignmentRepository
    
    assignment = await UserRoleAssignmentRepository.get_by_id(db, assignment_id)
    if not assignment:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    return assignment


@router.delete("/role-assignments/{assignment_id}")
async def delete_role_assignment(
    assignment_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a role assignment."""
    from app.modules.auth_profiles.repositories import UserRoleAssignmentRepository
    
    deleted = await UserRoleAssignmentRepository.delete(db, assignment_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Role assignment not found")
    
    await db.commit()
    return {"message": "Role assignment deleted successfully"}


@router.get("/users/{user_id}/accessible-sites")
async def get_user_accessible_sites(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all sites that a user has access to based on their role assignments."""
    sites = await crud.get_user_accessible_sites(db, user_id)

    # Resolve study identifiers via StudySite mappings instead of deprecated sites.study_id
    from app.models import StudySite, Study
    from sqlalchemy import select as sa_select

    site_ids = [site.id for site in sites]
    study_site_map = {}

    if site_ids:
        study_site_result = await db.execute(
            sa_select(StudySite).where(StudySite.site_id.in_(site_ids))
        )
        for study_site in study_site_result.scalars().all():
            # Prefer the first mapping per site for this summary endpoint
            if study_site.site_id not in study_site_map:
                study_site_map[study_site.site_id] = study_site.study_id

    study_ids = {study_id for study_id in study_site_map.values() if study_id}
    study_map = {}
    if study_ids:
        study_result = await db.execute(
            sa_select(Study).where(Study.id.in_(study_ids))
        )
        for study in study_result.scalars().all():
            study_map[study.id] = study

    return [
        {
            "id": str(site.id),
            "site_id": site.site_id,
            "name": site.name,
            "code": site.code,
            "location": site.location,
            "study_id": (
                # Prefer external study_id string when available, otherwise UUID string
                study_map.get(study_site_map.get(site.id)).study_id
                if study_map.get(study_site_map.get(site.id))
                else None
            ),
        }
        for site in sites
    ]


@router.get("/users/{user_id}/accessible-studies")
async def get_user_accessible_studies(
    user_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all studies that a user has access to based on their role assignments."""
    studies = await crud.get_user_accessible_studies(db, user_id)
    return [
        {
            "id": str(study.id),
            "study_id": study.study_id,
            "name": study.name,
            "description": study.description,
            "status": study.status
        }
        for study in studies
    ]


@router.post("/auth/signup", response_model=schemas.Token)
async def signup(
    user_data: schemas.UserSignup,
    db: AsyncSession = Depends(get_db)
):
    """Register a new user."""
    # Check if user already exists
    existing_user = await crud.get_user_by_email(db, user_data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    existing_user_id = await crud.get_user(db, user_data.user_id)
    if existing_user_id:
        raise HTTPException(status_code=400, detail="User ID already taken")
    
    # Hash password
    password_hash = get_password_hash(user_data.password)
    
    # Create user
    user_create = schemas.UserCreate(
        user_id=user_data.user_id,
        name=user_data.name,
        email=user_data.email,
        role=user_data.role,
        is_privileged=False
    )
    
    user = await crud.create_user(db, user_create, password_hash=password_hash)
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.user_id},
        expires_delta=access_token_expires
    )
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "email": user.email,
            "name": user.name,
            "role": user.role.value,
            "is_privileged": user.is_privileged == 'true'
        }
    }


# NOTE on /api/auth route ownership:
#   • POST /auth/login — legacy local password login (this file). Used by
#     the frontend when VITE_IAM_AUTH_MODE=local (dev default) so devs can
#     keep working with the existing email+password flow.
#   • GET  /auth/login — SSO redirect handler (app/modules/sso/routes/sso.py).
#     Triggered when VITE_IAM_AUTH_MODE=hub (production). Different HTTP
#     method, no conflict.
#   • GET  /auth/me    — owned by the SSO module, which falls back to bearer
#     JWT via get_current_user so local mode keeps working unchanged.


@router.post("/auth/login", response_model=schemas.Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """Local-mode password login (form-encoded). User lookup goes against
    Mongo `local_users` (mirrored from the IAM hub) — Postgres `users` is no
    longer the source of truth for auth.

    Returns a bearer JWT the frontend stores in localStorage. Coexists with
    the SSO GET handler at the same path because FastAPI keys routes by
    (path, method).
    """
    from app.db.mongo import get_mongo_db
    from app.integrations.iam.users import authenticate_local_user, local_user_to_dict

    mongo_db = await get_mongo_db()
    doc = await authenticate_local_user(mongo_db, form_data.username, form_data.password)
    if not doc:
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user_dict = await local_user_to_dict(mongo_db, doc)
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user_dict["user_id"]},
        expires_delta=access_token_expires,
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": user_dict,
    }


# File Upload/Download Endpoints
@router.get("/profile", response_model=schemas.UserProfileResponse)
async def get_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get current user's profile."""
    user_id = current_user["user_id"]
    profile = await crud.get_user_profile(db, user_id)
    if not profile:
        # Return empty profile if not exists
        return schemas.UserProfileResponse(
            id=uuid.uuid4(),
            user_id=user_id,
            name=None,
            address=None,
            phone=None,
            email=None,
            affiliation=None,
            specialty=None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    return profile


@router.get("/users/{user_id}/profile", response_model=schemas.UserProfileResponse)
async def get_user_profile(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get profile for any user by user_id (read-only)."""
    profile = await crud.get_user_profile(db, user_id)
    if not profile:
        # Return empty profile if not exists
        return schemas.UserProfileResponse(
            id=uuid.uuid4(),
            user_id=user_id,
            name=None,
            address=None,
            phone=None,
            email=None,
            affiliation=None,
            specialty=None,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
    return profile


@router.get("/users/{user_id}/rd-studies", response_model=List[schemas.RDStudyResponse])
async def get_user_rd_studies(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all R&D studies for a user by user_id (read-only)."""
    return await crud.get_rd_studies(db, user_id)


@router.get("/users/{user_id}/iis-studies", response_model=List[schemas.IISStudyResponse])
async def get_user_iis_studies(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all IIS studies for a user by user_id (read-only)."""
    return await crud.get_iis_studies(db, user_id)


@router.get("/users/{user_id}/events", response_model=List[schemas.EventResponse])
async def get_user_events(
    user_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get all events for a user by user_id (read-only)."""
    return await crud.get_events(db, user_id)


@router.get("/users/{user_id}/public-info", response_model=List[schemas.ResearchPaperSummary])
async def get_user_public_info(
    user_id: str,
    num_results: int = Query(10, ge=1, le=10, description="Number of results (max 10)"),
    db: AsyncSession = Depends(get_db)
):
    """Search for research papers for a user by user_id (read-only). Automatically uses user's profile details."""
    from app.integrations.google_search import google_search_service
    
    if not google_search_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Google Search API is not configured. Please set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID in .env"
        )
    
    # Get user profile to construct search query from their basic details
    profile = await crud.get_user_profile(db, user_id)
    if not profile:
        return []
    
    # Use profile details to construct search query
    search_terms = []
    if profile.name:
        search_terms.append(profile.name)
    if profile.affiliation:
        search_terms.append(profile.affiliation)
    if profile.specialty:
        search_terms.append(profile.specialty)
    
    if not search_terms:
        return []
    
    query = ' '.join(search_terms)
    papers = await google_search_service.search_research_papers(query, num_results)
    return papers


@router.put("/profile", response_model=schemas.UserProfileResponse)
async def update_profile(
    profile: schemas.UserProfileCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create or update current user's profile."""
    user_id = current_user["user_id"]
    return await crud.create_or_update_user_profile(db, user_id, profile)


# R&D Studies Endpoints
@router.post("/profile/rd-studies", response_model=schemas.RDStudyResponse)
async def create_rd_study(
    study: schemas.RDStudyCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new R&D study for current user."""
    user_id = current_user["user_id"]
    return await crud.create_rd_study(db, user_id, study)


@router.get("/profile/rd-studies", response_model=List[schemas.RDStudyResponse])
async def get_rd_studies(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all R&D studies for current user."""
    user_id = current_user["user_id"]
    return await crud.get_rd_studies(db, user_id)


@router.put("/profile/rd-studies/{study_id}", response_model=schemas.RDStudyResponse)
async def update_rd_study(
    study_id: UUID,
    study: schemas.RDStudyCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an R&D study."""
    user_id = current_user["user_id"]
    updated = await crud.update_rd_study(db, study_id, user_id, study)
    if not updated:
        raise HTTPException(status_code=404, detail="R&D study not found")
    return updated


@router.delete("/profile/rd-studies/{study_id}")
async def delete_rd_study(
    study_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an R&D study."""
    user_id = current_user["user_id"]
    success = await crud.delete_rd_study(db, study_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="R&D study not found")
    return {"status": "deleted", "study_id": str(study_id)}


# IIS Studies Endpoints
@router.post("/profile/iis-studies", response_model=schemas.IISStudyResponse)
async def create_iis_study(
    study: schemas.IISStudyCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new IIS study for current user."""
    user_id = current_user["user_id"]
    return await crud.create_iis_study(db, user_id, study)


@router.get("/profile/iis-studies", response_model=List[schemas.IISStudyResponse])
async def get_iis_studies(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all IIS studies for current user."""
    user_id = current_user["user_id"]
    return await crud.get_iis_studies(db, user_id)


@router.put("/profile/iis-studies/{study_id}", response_model=schemas.IISStudyResponse)
async def update_iis_study(
    study_id: UUID,
    study: schemas.IISStudyCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an IIS study."""
    user_id = current_user["user_id"]
    updated = await crud.update_iis_study(db, study_id, user_id, study)
    if not updated:
        raise HTTPException(status_code=404, detail="IIS study not found")
    return updated


@router.delete("/profile/iis-studies/{study_id}")
async def delete_iis_study(
    study_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an IIS study."""
    user_id = current_user["user_id"]
    success = await crud.delete_iis_study(db, study_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="IIS study not found")
    return {"status": "deleted", "study_id": str(study_id)}


# Events Endpoints
@router.post("/profile/events", response_model=schemas.EventResponse)
async def create_event(
    event: schemas.EventCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new event for current user."""
    user_id = current_user["user_id"]
    return await crud.create_event(db, user_id, event)


@router.get("/profile/events", response_model=List[schemas.EventResponse])
async def get_events(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get all events for current user."""
    user_id = current_user["user_id"]
    return await crud.get_events(db, user_id)


@router.put("/profile/events/{event_id}", response_model=schemas.EventResponse)
async def update_event(
    event_id: UUID,
    event: schemas.EventCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update an event."""
    user_id = current_user["user_id"]
    updated = await crud.update_event(db, event_id, user_id, event)
    if not updated:
        raise HTTPException(status_code=404, detail="Event not found")
    return updated


@router.delete("/profile/events/{event_id}")
async def delete_event(
    event_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete an event."""
    user_id = current_user["user_id"]
    success = await crud.delete_event(db, event_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"status": "deleted", "event_id": str(event_id)}


# Public Info (Google Search) Endpoint
@router.get("/profile/public-info", response_model=List[schemas.ResearchPaperSummary])
async def search_public_info(
    query: str = Query(..., description="Search query for research papers"),
    num_results: int = Query(10, ge=1, le=10, description="Number of results (max 10)"),
    current_user: dict = Depends(get_current_user),
):
    """Search for research papers using Google Custom Search API."""
    from app.integrations.google_search import google_search_service
    
    if not google_search_service.is_available():
        raise HTTPException(
            status_code=503,
            detail="Google Search API is not configured. Please set GOOGLE_SEARCH_API_KEY and GOOGLE_SEARCH_ENGINE_ID in .env"
        )
    
    papers = await google_search_service.search_research_papers(query, num_results)
    return papers


# Chat/Ask Me Anything endpoints

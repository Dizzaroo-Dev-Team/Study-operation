"""
Sites API endpoints for managing hospital sites and their associated doctors and studies.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID
from app.db import get_db
from app.models import User, Study, Site, UserSite, SiteProfile, StudySite
from app.modules.sites.site_irb_validation import clear_incompatible_site_irb_mapping
from app.auth import get_current_user, get_current_user_optional
from app import schemas
from datetime import datetime
import uuid

router = APIRouter()
logger = logging.getLogger(__name__)

# Hub roles that grant blanket access to every study in this app (Option A —
# owner override). Stored in Mongo `local_hub_user_attributes` under
# attributeKey="hub_roles", value=[...] (mirrored from IAM via Kafka).
_OWNER_HUB_ROLES = {"APP_OWNER", "HUB_OWNER"}


async def _user_is_hub_owner(mongo_db, user_id: str) -> bool:
    """True when the user's `hub_roles` attribute contains an owner role.

    Owners bypass the per-study `resource_access` filter and see every study
    in the app. The roles live in `local_hub_user_attributes`:
        { userId, attributeKey: "hub_roles", value: ["APP_OWNER", "USER"] }
    `value` may also arrive as a single string, so we coerce defensively.
    """
    if not user_id:
        return False
    doc = await mongo_db["local_hub_user_attributes"].find_one({
        "userId": user_id,
        "attributeKey": "hub_roles",
    })
    if not doc:
        return False
    raw = doc.get("value")
    roles = raw if isinstance(raw, list) else [raw]
    return any(str(r).strip().upper() in _OWNER_HUB_ROLES for r in roles if r)


# A study is a level-3 resource with metadata.type "study" that is active.
# IAM's newer resource contract (the Kafka mirror) carries active-state in
# metadata.resource_status and no longer stores top-level isActive / appKey; we
# also accept legacy isActive:True so pre-existing mirror docs aren't hidden.
# App-scoping is enforced upstream (Kafka routing target + per-user
# resource_access), so the old appKey filter is dropped.
_ACTIVE_STUDY_MATCH: dict = {"$or": [{"metadata.resource_status": "active"}, {"isActive": True}]}


async def _all_app_studies(mongo_db, app_key: str) -> list[dict]:
    """Every active level-3 study resource for this app — the owner view."""
    query: dict = {**_ACTIVE_STUDY_MATCH, "level": 3}
    out: list[dict] = []
    async for doc in mongo_db["local_resources"].find(query).sort("name", 1):
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        meta_type = str(meta.get("type") or "").strip().lower()
        if meta_type and meta_type != "study":
            continue
        out.append({
            "id": str(doc["_id"]),
            "study_id": doc.get("name") or doc.get("resourceExternalId") or str(doc["_id"]),
            "name": doc.get("name") or "",
            "description": meta.get("description") or "",
            "status": meta.get("resource_status") or ("active" if doc.get("isActive") else "inactive"),
        })
    return out


@router.get("/studies")
async def list_studies(
    current_user: dict = Depends(get_current_user),
):
    """
    List studies sourced from MongoDB `local_resources` (mirrored from the IAM
    hub via the Kafka sync), restricted to those the **current user** has been
    granted access to via the IAM `resource_access` attribute.

    A "study" is a resource entry with:
      * `appKey` matching the configured `IAM_APPLICATION_ID`, AND
      * `level == 3` (per IAM hub convention), AND
      * `isActive == True`, AND
      * `_id` present in the current user's `local_app_user_attributes`
        document where `attributeName == "resource_access"`. Each item in
        that doc's `value` array is `{role, resource_id}`.

    A user with no `resource_access` row (or an empty list) sees zero studies
    — IAM is the source of truth. No row = no access.

    EXCEPTION (Option A — owner override): a user whose `hub_roles` attribute
    contains APP_OWNER or HUB_OWNER bypasses the per-study filter entirely and
    sees every study in the app.

    Response shape preserved 1:1 with the previous Postgres-backed endpoint:
        { id, study_id, name, description, status }
    """
    from app.config import settings
    from app.db.mongo import get_mongo_db

    mongo_db = await get_mongo_db()
    app_key = (settings.iam_application_id or "").strip().lower()
    user_id = (current_user or {}).get("user_id") or ""

    # ── Owner override: APP_OWNER / HUB_OWNER see ALL studies ─────────────
    if await _user_is_hub_owner(mongo_db, user_id):
        out = await _all_app_studies(mongo_db, app_key)
        logger.info(
            "[sites/studies] owner override: user_id=%s sees all %d studies",
            user_id, len(out),
        )
        return out

    # ── Resolve the user's allowed resource ids from IAM ABAC ─────────────
    allowed_resource_ids: set[str] = set()
    access_doc = None
    if user_id:
        access_doc = await mongo_db["local_app_user_attributes"].find_one({
            "userId": user_id,
            "attributeName": "resource_access",
        })
        if access_doc and isinstance(access_doc.get("value"), list):
            for entry in access_doc["value"]:
                if not isinstance(entry, dict):
                    continue
                rid = entry.get("resource_id") or entry.get("resourceId") or entry.get("id")
                if rid:
                    allowed_resource_ids.add(str(rid))

    # DIAGNOSTIC — when studies dropdown stays empty, this line pinpoints which
    # layer is the cause:
    #   • user_id empty           → session didn't propagate, or normalize_hub_user lost it
    #   • access_doc None         → Kafka mirror has no resource_access doc for this user
    #   • allowed_resource_ids 0  → access_doc exists but `value` array is empty / malformed
    #   • out length 0 but rids>0 → local_resources missing the studies (Kafka mirror)
    #                                or appKey/level filter excludes them
    logger.info(
        "[sites/studies] user_id=%s app_key=%s access_doc_found=%s "
        "allowed_resource_ids=%s",
        user_id or "<empty>",
        app_key or "<empty>",
        access_doc is not None,
        sorted(allowed_resource_ids),
    )

    # No access list → no studies. IAM is authoritative.
    if not allowed_resource_ids:
        return []

    # ── Pull the matching study resources ────────────────────────────────
    query: dict = {
        **_ACTIVE_STUDY_MATCH,
        "level": 3,
        "_id": {"$in": list(allowed_resource_ids)},
    }

    out: list[dict] = []
    async for doc in mongo_db["local_resources"].find(query).sort("name", 1):
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        # Defensive: IAM may omit `metadata.type` for some resources. Skip
        # entries that explicitly identify as something other than a study.
        meta_type = str(meta.get("type") or "").strip().lower()
        if meta_type and meta_type != "study":
            continue
        out.append({
            "id": str(doc["_id"]),
            "study_id": doc.get("name") or doc.get("resourceExternalId") or str(doc["_id"]),
            "name": doc.get("name") or "",
            "description": meta.get("description") or "",
            "status": meta.get("resource_status") or ("active" if doc.get("isActive") else "inactive"),
        })

    logger.info(
        "[sites/studies] returning %d studies for user_id=%s",
        len(out), user_id,
    )
    return out


@router.get("/study-team")
async def list_study_team(
    study_id: Optional[str] = Query(
        None,
        description=(
            "Optional Mongo `local_resources._id` (study UUID). When set, only "
            "returns users whose IAM `resource_access` includes this study."
        ),
    ),
    current_user: dict = Depends(get_current_user),
):
    """
    Return the IAM-managed user roster for this Study Operations app.

    Sources (all Mongo, mirrored from the IAM hub via the Kafka sync):
      * `local_app_user_attributes`  — `resource_access` per user (the
        `{role, resource_id}` array your IAM publishes).
      * `local_users`                — display name / email.
      * `local_hub_user_attributes`  — user status (attributeKey 'user_status').
      * `local_resources`            — study names for each resource_id.

    Each user row includes ALL studies they're granted in `resource_access`
    (filtered to studies in this app), regardless of the optional `study_id`
    filter — the filter only decides which users SHOW UP, not which studies
    appear inside their row, so the UI can show full context.

    Sites access is intentionally NOT filtered here — site grants live in
    this app's database, not in IAM.
    """
    from app.db.mongo import get_mongo_db
    from app.integrations.iam.membership import parse_resource_access_value

    mongo_db = await get_mongo_db()

    # 1) Pre-load study resources for this app so we can map resource_id → name.
    study_query: dict = {**_ACTIVE_STUDY_MATCH, "level": 3}
    studies_by_id: dict[str, dict] = {}
    async for doc in mongo_db["local_resources"].find(study_query):
        meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
        meta_type = str(meta.get("type") or "").strip().lower()
        if meta_type and meta_type != "study":
            continue
        studies_by_id[str(doc["_id"])] = {
            "id": str(doc["_id"]),
            "name": doc.get("name") or "",
            "study_id": doc.get("name") or doc.get("resourceExternalId") or str(doc["_id"]),
        }

    # 2) Pull every resource_access row.
    raw_access: list[dict] = await mongo_db["local_app_user_attributes"].find({
        "attributeName": "resource_access"
    }).to_list(length=None)

    # 3) Pull all known users in one go (small set, single query). User status
    #    is no longer stored on local_users — it lives in
    #    local_hub_user_attributes under attributeKey 'user_status'.
    user_ids = [str(d.get("userId") or "") for d in raw_access if d.get("userId")]
    users_by_id: dict[str, dict] = {}
    status_by_id: dict[str, str] = {}
    if user_ids:
        async for u in mongo_db["local_users"].find({"_id": {"$in": user_ids}}):
            users_by_id[str(u["_id"])] = u
        async for a in mongo_db["local_hub_user_attributes"].find(
            {"userId": {"$in": user_ids}, "attributeKey": "user_status"}
        ):
            if a.get("value"):
                status_by_id[str(a["userId"])] = str(a["value"])

    target_study = (study_id or "").strip()
    rows: list[dict] = []
    for access in raw_access:
        uid = str(access.get("userId") or "")
        if not uid:
            continue
        # Project resource_access entries to known studies in this app only.
        # The resource_access → resource_id resolution is shared with
        # app.integrations.iam.membership.user_can_access_study so there is ONE
        # implementation (parse_resource_access_value dedups + preserves order).
        my_studies: list[dict] = []
        for entry in parse_resource_access_value(access.get("value")):
            study_meta = studies_by_id.get(entry["resource_id"])
            if study_meta is None:
                # Resource isn't a study in this app (or is from a different app/level).
                continue
            my_studies.append({
                "id": study_meta["id"],
                "name": study_meta["name"],
                "study_id": study_meta["study_id"],
                "role": entry["role"],
            })

        if not my_studies:
            # User has resource_access but none of the resources are studies
            # in this app — skip (would just be visual noise).
            continue

        if target_study and not any(s["id"] == target_study for s in my_studies):
            continue

        local_user = users_by_id.get(uid) or {}
        rows.append({
            "user_id": uid,
            "email": local_user.get("email") or None,
            "name": local_user.get("displayName") or local_user.get("name") or local_user.get("email") or uid,
            "status": status_by_id.get(uid) or "unknown",
            "studies": my_studies,
        })

    # Stable order: name asc.
    rows.sort(key=lambda r: (r.get("name") or "").lower())
    return {
        "data": rows,
        "total": len(rows),
        "study_id": target_study or None,
    }


@router.get("/sites")
async def list_sites(
    study_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Return sites linked to the given study via the `study_sites` mapping table.

    Sites are created in Study Setup → Site Setup, and each create stamps a
    `StudySite` row. This endpoint is the single source of truth for every
    site picker in the app (navbar, conversations, monitoring, etc.) — when a
    `study_id` is passed, the result is the exact same filtered roster the
    Site Setup tab shows for that study.

    `study_id` accepts either the Postgres UUID or the human study code
    (e.g. `"ASLAN001-009"`). When omitted, the endpoint returns every site
    (kept for any caller that still wants the unfiltered roster).
    """
    stmt = select(Site)

    if study_id:
        # Resolve the study by UUID first, then by external study_id string.
        study_obj: Optional[Study] = None
        try:
            sid = UUID(str(study_id))
            study_obj = (
                await db.execute(select(Study).where(Study.id == sid))
            ).scalar_one_or_none()
        except (ValueError, TypeError):
            pass
        if study_obj is None:
            study_obj = (
                await db.execute(select(Study).where(Study.study_id == str(study_id)))
            ).scalar_one_or_none()

        if study_obj is None:
            return []

        stmt = (
            stmt.join(StudySite, StudySite.site_id == Site.id)
            .where(StudySite.study_id == study_obj.id)
        )

    sites = (await db.execute(stmt.order_by(Site.name))).scalars().all()

    # Hydrate the real study_id (human code) for each site from the
    # study_sites mapping. When the caller filtered by study_id we keep
    # echoing it; otherwise we look up the first study linked to each site.
    study_id_by_site: dict = {}
    if sites:
        site_ids = [s.id for s in sites]
        link_rows = (
            await db.execute(
                select(StudySite.site_id, Study.study_id)
                .join(Study, Study.id == StudySite.study_id)
                .where(StudySite.site_id.in_(site_ids))
            )
        ).all()
        for sid, std_code in link_rows:
            study_id_by_site.setdefault(sid, std_code)

    echoed_study_id = study_id or None

    return [
        {
            "id": str(site.id),
            "site_id": site.site_id,
            "study_id": echoed_study_id or study_id_by_site.get(site.id),
            "name": site.name,
            "code": site.code,
            "location": site.location,
            "principal_investigator": site.principal_investigator,
            "principal_investigator_uuid":site.principal_investigator_id,
            "address": site.address,
            "city": site.city,
            "country": site.country,
            "status": site.status,
        }
        for site in sites
    ]


@router.get("/sites/{site_id}")
async def get_site(
    site_id: UUID,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get site details with associated doctors and their studies. Returns mock data for now."""
    # TODO: Implement actual Site model and database queries
    # For now, return mock data
    
    # Get some users to show as doctors
    result = await db.execute(select(User).limit(3))
    users = result.scalars().all()
    
    doctors_data = []
    for user in users:
        doctors_data.append({
            "id": str(user.id),
            "user_id": user.user_id,
            "name": user.name or "Unknown Doctor",
            "email": user.email or "no-email@example.com",
            "role": user.role.value if hasattr(user.role, 'value') else str(user.role),
            "studies": [
                {
                    "id": str(uuid.uuid4()),
                    "title": "Clinical Trial Study A",
                    "description": "Phase 3 study for treatment evaluation",
                    "status": "active"
                },
                {
                    "id": str(uuid.uuid4()),
                    "title": "Research Study B",
                    "description": "Long-term efficacy study",
                    "status": "active"
                }
            ]
        })
    
    return {
        "id": str(site_id),
        "name": "City General Hospital",
        "address": "123 Medical Center Drive",
        "city": "New York",
        "country": "USA",
        "doctors": doctors_data
    }


@router.get("/sites/{site_id}/profile", response_model=schemas.SiteProfileResponse)
async def get_site_profile(
    site_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Get site profile for a site.
    """
    try:
        # Resolve site
        try:
            site_uuid = UUID(str(site_id))
            site_result = await db.execute(select(Site).where(Site.id == site_uuid))
            site = site_result.scalar_one_or_none()
        except (ValueError, TypeError):
            site_result = await db.execute(select(Site).where(Site.site_id == site_id))
            site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        
        # Get profile
        profile_result = await db.execute(
            select(SiteProfile).where(SiteProfile.site_id == site.id)
        )
        profile = profile_result.scalar_one_or_none()
        
        if not profile:
            raise HTTPException(status_code=404, detail="Site profile not found")
        
        return profile
    except HTTPException:
        raise
    except Exception as e:
        # Log the actual error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting site profile: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}. Please ensure the site_profiles table exists. Run the migration script: python create_site_profile_table.py"
        )


@router.post("/sites/{site_id}/profile", response_model=schemas.SiteProfileResponse)
async def create_site_profile(
    site_id: str,
    profile_data: schemas.SiteProfileCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Create site profile for a site. If profile already exists, returns existing profile.
    """
    try:
        # Resolve site
        try:
            site_uuid = UUID(str(site_id))
            site_result = await db.execute(select(Site).where(Site.id == site_uuid))
            site = site_result.scalar_one_or_none()
        except (ValueError, TypeError):
            site_result = await db.execute(select(Site).where(Site.site_id == site_id))
            site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        
        # Check if profile already exists
        profile_result = await db.execute(
            select(SiteProfile).where(SiteProfile.site_id == site.id)
        )
        existing_profile = profile_result.scalar_one_or_none()
        
        if existing_profile:
            # Return existing profile
            return existing_profile
        
        # Create new profile
        profile = SiteProfile(
            site_id=site.id,
            **profile_data.model_dump(exclude_unset=True)
        )
        db.add(profile)
        await db.commit()
        await db.refresh(profile)
        
        return profile
    except HTTPException:
        raise
    except Exception as e:
        # Log the actual error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error creating site profile: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}. Please ensure the site_profiles table exists. Run the migration script: python create_site_profile_table.py"
        )


@router.put("/sites/{site_id}/profile", response_model=schemas.SiteProfileResponse)
async def update_site_profile(
    site_id: str,
    profile_data: schemas.SiteProfileUpdate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """
    Update site profile for a site. Creates profile if it doesn't exist.
    """
    try:
        # Resolve site
        try:
            site_uuid = UUID(str(site_id))
            site_result = await db.execute(select(Site).where(Site.id == site_uuid))
            site = site_result.scalar_one_or_none()
        except (ValueError, TypeError):
            site_result = await db.execute(select(Site).where(Site.site_id == site_id))
            site = site_result.scalar_one_or_none()
        
        if not site:
            raise HTTPException(status_code=404, detail="Site not found")
        
        # Get or create profile
        profile_result = await db.execute(
            select(SiteProfile).where(SiteProfile.site_id == site.id)
        )
        profile = profile_result.scalar_one_or_none()
        
        if not profile:
            # Create new profile
            profile = SiteProfile(
                site_id=site.id,
                **profile_data.model_dump(exclude_unset=True)
            )
            db.add(profile)
        else:
            # Update existing profile
            update_data = profile_data.model_dump(exclude_unset=True)
            for key, value in update_data.items():
                setattr(profile, key, value)

        await db.flush()
        if "country" in profile_data.model_dump(exclude_unset=True):
            await clear_incompatible_site_irb_mapping(db, site.id)

        await db.commit()
        await db.refresh(profile)
        
        return profile
    except HTTPException:
        raise
    except Exception as e:
        # Log the actual error for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error updating site profile: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}. Please ensure the site_profiles table exists. Run the migration script: python create_site_profile_table.py"
        )


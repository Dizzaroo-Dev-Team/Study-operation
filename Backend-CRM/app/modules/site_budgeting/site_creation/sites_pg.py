"""
Postgres-backed implementation of /api/budgeting/site/sites.

Replaces the previous Mongo path so that sites created from the in-app form
land in the same `sites` table the rest of the CRM (navbar selector, study
status, control tower, conversations) reads from.

Public functions: list_sites, get_site, create_site, update_site, delete_site.
All return the same camelCase shape the existing frontend expects so the
shadcn table + react-hook-form keep working unchanged.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any, Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.facilities.services import data_platform_client
from app import crud
from app.config import settings
from app.db.mongo import get_mongo_db
from app.utils.log_sanitize import sfmt
from app.integrations.iam.users import get_local_user_by_id
from app.models import (
    Site,
    Study,
    StudySite,
    User,
)

logger = logging.getLogger(__name__)


# ─── Lookups ──────────────────────────────────────────────────────────────────

async def _get_study(db: AsyncSession, ref: str) -> Optional[Study]:
    """Resolve a study by UUID id, or by external study_id string."""
    if not ref:
        return None
    try:
        sid = UUID(str(ref))
        result = await db.execute(select(Study).where(Study.id == sid))
        study = result.scalar_one_or_none()
        if study:
            return study
    except (ValueError, TypeError):
        pass
    result = await db.execute(select(Study).where(Study.study_id == str(ref)))
    return result.scalar_one_or_none()


def _iam_doc_to_postgres_study_fields(doc: dict, fallback_uuid: UUID) -> tuple[str, str, Optional[str], str]:
    """Derive Study columns from a Mongo `local_resources` document (same rules as IAM Kafka mirror)."""
    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    clean_name = (doc.get("name") or "").strip() or None
    external_id = (
        str(doc.get("resourceExternalId") or doc.get("resource_external_id") or "").strip() or None
    )
    study_id_value = clean_name or external_id or str(fallback_uuid)
    description = str(meta.get("description") or "").strip() or None
    raw_status = meta.get("resource_status")
    is_active = bool(doc.get("isActive", doc.get("is_active", True)))
    status_value = (
        str(raw_status).strip()
        if raw_status
        else ("active" if is_active else "inactive")
    )
    display_name = clean_name or study_id_value
    return study_id_value, display_name, description, status_value


async def _get_or_mirror_study_from_iam(db: AsyncSession, ref: str) -> Optional[Study]:
    """
    Resolve Postgres Study by id / study_id, or insert a row by reading IAM Mongo `local_resources`.

    GET /studies is IAM-backed; POST /api/budgeting/site/sites needs a Postgres `studies` row for FKs.
    Machines without Kafka mirroring often have an empty `studies` table — this bridges that gap.
    """
    study = await _get_study(db, ref)
    if study is not None:
        return study
    if not (ref or "").strip():
        return None

    try:
        uid = UUID(str(ref))
    except (ValueError, TypeError):
        return None

    try:
        mongo_db = await get_mongo_db()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[sites_pg] Mongo unavailable while resolving study %s: %s", ref, exc)
        return None

    coll = mongo_db["local_resources"]
    doc = await coll.find_one({"_id": ref})
    if doc is None:
        doc = await coll.find_one({"_id": str(uid)})
    if doc is None:
        logger.info("[sites_pg] No IAM local_resources document for study ref=%s", ref)
        return None

    meta = doc.get("metadata") if isinstance(doc.get("metadata"), dict) else {}
    level = int(doc.get("level") or 0)
    app_key = str(doc.get("appKey") or "").strip().lower()
    expected_app = (settings.iam_application_id or "").strip().lower()
    if expected_app and app_key != expected_app:
        logger.info(
            "[sites_pg] IAM resource appKey mismatch for %s — got %r expected %r",
            ref,
            app_key,
            expected_app,
        )
        return None
    meta_type = str(meta.get("type") or "").strip().lower()
    if meta_type and meta_type != "study":
        return None
    if level != 3:
        logger.info("[sites_pg] IAM resource level=%s — not mirroring as study for %s", level, ref)
        return None

    study_id_value, display_name, description, status_value = _iam_doc_to_postgres_study_fields(doc, uid)

    by_sid = (await db.execute(select(Study).where(Study.study_id == study_id_value))).scalar_one_or_none()
    if by_sid is not None:
        if by_sid.id != uid:
            logger.warning(
                "[sites_pg] IAM id %s vs Postgres studies.id=%s for study_id=%r — using existing Postgres row",
                uid,
                by_sid.id,
                study_id_value,
            )
        return by_sid

    existing_pk = (await db.execute(select(Study).where(Study.id == uid))).scalar_one_or_none()
    if existing_pk is not None:
        return existing_pk

    row = Study(
        id=uid,
        study_id=study_id_value,
        name=display_name,
        description=description,
        status=status_value,
    )
    db.add(row)
    await db.flush()
    logger.info("[sites_pg] Mirrored IAM study %s into Postgres (study_id=%r)", uid, study_id_value)
    return row


async def _get_user(db: AsyncSession, ref: str) -> Optional[User]:
    """Resolve a user by UUID id or by user_id string."""
    if not ref:
        return None
    try:
        uid = UUID(str(ref))
        result = await db.execute(select(User).where(User.id == uid))
        user = result.scalar_one_or_none()
        if user:
            return user
    except (ValueError, TypeError):
        pass
    result = await db.execute(select(User).where(User.user_id == str(ref)))
    return result.scalar_one_or_none()


async def _get_facility_row(facility_ref: str) -> Optional[dict]:
    """Fetch a single facility from the Data Platform API.

    Returns the same snake_case row dict the old asyncpg queries produced; the
    client resolves legacy Azure/IAM ids stored on existing sites via the
    by-iam-id endpoint.
    """
    if not facility_ref:
        return None
    try:
        return await data_platform_client.fetch_facility_row(str(facility_ref))
    except data_platform_client.DataPlatformError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Facilities service unavailable: {exc}",
        ) from exc


async def _get_facility_row_optional(facility_ref: str) -> Optional[dict]:
    """Best-effort facility lookup for read paths.

    Site assignment reads should still work when the external read-only
    facilities source is offline or its DNS is unavailable. Write paths keep
    using _get_facility_row so they still validate the chosen facility.
    """
    try:
        return await _get_facility_row(facility_ref)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[sites_pg] facility lookup unavailable for %s: %s",
            facility_ref,
            exc,
        )
        return None


async def _get_facility_map_optional(facility_ids: list[UUID]) -> dict:
    """Best-effort batched facility hydration for read paths."""
    if not facility_ids:
        return {}
    try:
        return await data_platform_client.fetch_facility_rows_map(facility_ids)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[sites_pg] facility hydration unavailable: %s", exc)
        return {}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _last3(s: Optional[str], default: str) -> str:
    if not s:
        return default
    s = str(s).strip()
    return s[-3:].upper() if len(s) >= 3 else (s.upper() or default)


def _generate_site_code(study: Study, facility: dict, pi: Optional[User]) -> str:
    """SITE-{study}-{facility}-{pi}-{rand} — unique and human-readable."""
    suffix = secrets.token_hex(2).upper()
    return (
        f"SITE-"
        f"{_last3(study.study_id or str(study.id), 'STD')}-"
        f"{_last3(facility.get('facility_code'), 'FAC')}-"
        f"{_last3(pi.user_id if pi else None, 'PI')}-"
        f"{suffix}"
    )


def _user_display_name(u: Optional[User]) -> str:
    if u is None:
        return ""
    return u.name or u.email or u.user_id or ""


def _serialise_site(
    site: Site,
    study: Optional[Study] = None,
    facility: Optional[dict] = None,
    pi: Optional[User] = None,
) -> dict:
    """Shape the row the way the existing frontend expects."""
    facility_obj = None
    if facility is not None:
        facility_obj = {
            "id": str(facility["id"]),
            "_id": str(facility["id"]),
            "name": facility.get("name"),
            "facilityId": facility.get("facility_code"),
            "facilityCode": facility.get("facility_code"),
            "address": {
                "street": facility.get("street") or "",
                "city": facility.get("city") or "",
                "state": facility.get("state") or "",
                "country": facility.get("country") or "",
                "postalCode": facility.get("postal_code") or "",
            },
        }
    elif site.location or site.city or site.country:
        facility_obj = {
            "id": None,
            "_id": None,
            "name": site.name,
            "facilityId": None,
            "facilityCode": None,
            "address": {
                "street": site.address or "",
                "city": site.city or "",
                "state": "",
                "country": site.country or "",
                "postalCode": "",
            },
        }

    study_obj = None
    if study is not None:
        study_obj = {
            "id": str(study.id),
            "_id": str(study.id),
            "title": study.name,
            "name": study.name,
            "study_id": study.study_id,
            "studyId": study.study_id,
        }

    pi_obj = None
    if pi is not None:
        pi_obj = {
            "id": str(pi.id),
            "_id": str(pi.id),
            "user_id": pi.user_id,
            "userId": pi.user_id,
            "name": _user_display_name(pi),
            "email": pi.email,
        }

    return {
        "id": str(site.id),
        "_id": str(site.id),
        "siteCode": site.site_id,
        "name": site.name,
        "study": study_obj,
        "facility": facility_obj,
        "principalInvestigator": pi_obj,
        # Pre-computed display strings so the frontend never has to render "Unknown".
        "studyTitle": study.name if study else None,
        "facilityName": facility["name"] if facility else site.name,
        "principalInvestigatorName": _user_display_name(pi) if pi else "Not Assigned",
        "status": (site.status or "PENDING").upper(),
        "createdAt": site.created_at.isoformat() if site.created_at else None,
        "updatedAt": site.updated_at.isoformat() if site.updated_at else None,
    }


async def _study_for_site(db: AsyncSession, site_id) -> Optional[Study]:
    """Find a Study linked to a Site via StudySite mapping (first one)."""
    result = await db.execute(
        select(Study)
        .join(StudySite, StudySite.study_id == Study.id)
        .where(StudySite.site_id == site_id)
        .limit(1)
    )
    return result.scalar_one_or_none()


# ─── CRUD operations ──────────────────────────────────────────────────────────

async def list_sites(
    db: AsyncSession,
    *,
    page: int,
    limit: int,
    search: str,
    study: str,
    facility: str,
    status_q: str,
    principal_investigator: str,
) -> dict:
    """Paginated site list with the response shape `{success, data, pagination, total}`."""
    stmt = select(Site)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Site.name.ilike(like), Site.site_id.ilike(like), Site.code.ilike(like)))
    if status_q:
        stmt = stmt.where(Site.status.ilike(status_q))
    if principal_investigator:
        stmt = stmt.where(Site.principal_investigator.ilike(f"%{principal_investigator}%"))
    if facility:
        try:
            fid = UUID(str(facility))
            stmt = stmt.where(Site.facility_external_id == fid)
        except (ValueError, TypeError):
            # Treat as facility_code: resolve the row in the external DB and filter by its UUID.
            facility_row = await _get_facility_row(facility)
            if facility_row is None:
                return {"success": True, "data": [], "pagination": {"page": page, "limit": limit, "total": 0, "pages": 0}, "total": 0}
            stmt = stmt.where(Site.facility_external_id == facility_row["id"])
    if study:
        study_obj = await _get_study(db, study)
        if study_obj:
            stmt = stmt.join(StudySite, StudySite.site_id == Site.id).where(StudySite.study_id == study_obj.id)
        else:
            return {"success": True, "data": [], "pagination": {"page": page, "limit": limit, "total": 0, "pages": 0}, "total": 0}

    # total
    total_stmt = stmt.with_only_columns(Site.id).order_by(None)
    total_rows = (await db.execute(total_stmt)).all()
    total = len(total_rows)

    stmt = stmt.order_by(Site.created_at.desc()).offset((page - 1) * limit).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()

    # Hydrate study via StudySite mapping
    site_ids = [s.id for s in rows]
    study_map: dict = {}
    if site_ids:
        link_stmt = select(StudySite, Study).join(Study, Study.id == StudySite.study_id).where(StudySite.site_id.in_(site_ids))
        for ss, st in (await db.execute(link_stmt)).all():
            study_map.setdefault(ss.site_id, st)

    # Hydrate facility from external pool in one batched query
    facility_ids = [s.facility_external_id for s in rows if s.facility_external_id is not None]
    facility_map: dict = {}
    if facility_ids:
        facility_map = await _get_facility_map_optional(facility_ids)

    # Hydrate PI users in one batched query
    pi_ids = [s.principal_investigator_id for s in rows if s.principal_investigator_id is not None]
    user_map: dict = {}
    if pi_ids:
        u_rows = (await db.execute(select(User).where(User.id.in_(pi_ids)))).scalars().all()
        for u in u_rows:
            user_map[u.id] = u

    items = [
        _serialise_site(
            s,
            study=study_map.get(s.id),
            facility=facility_map.get(s.facility_external_id) if s.facility_external_id else None,
            pi=user_map.get(s.principal_investigator_id) if s.principal_investigator_id else None,
        )
        for s in rows
    ]
    pages = (total + limit - 1) // limit if total else 0
    return {
        "success": True,
        "data": items,
        "pagination": {"page": page, "limit": limit, "total": total, "pages": pages},
        "total": total,
    }


async def get_site(db: AsyncSession, site_id_ref: str) -> Optional[dict]:
    site = await _resolve_site(db, site_id_ref)
    if site is None:
        return None
    study = await _study_for_site(db, site.id)
    facility = None
    if site.facility_external_id:
        facility = await _get_facility_row_optional(str(site.facility_external_id))
    pi = None
    if site.principal_investigator_id:
        pi = (await db.execute(select(User).where(User.id == site.principal_investigator_id))).scalar_one_or_none()
    return _serialise_site(site, study=study, facility=facility, pi=pi)


async def _resolve_site(db: AsyncSession, ref: str) -> Optional[Site]:
    if not ref:
        return None
    try:
        uid = UUID(str(ref))
        return (await db.execute(select(Site).where(Site.id == uid))).scalar_one_or_none()
    except (ValueError, TypeError):
        pass
    return (await db.execute(select(Site).where(Site.site_id == str(ref)))).scalar_one_or_none()


async def create_site(
    db: AsyncSession,
    body: dict,
    *,
    current_user_id: str,
) -> dict:
    """Insert a Site, link it to the chosen Study, and grant the creator visibility."""
    study = await _get_or_mirror_study_from_iam(db, str(body.get("study") or ""))
    if study is None:
        raise HTTPException(status_code=400, detail="Study not found.")

    facility = await _get_facility_row(body.get("facility", ""))
    if facility is None:
        raise HTTPException(status_code=400, detail="Facility not found.")

    pi = await _get_user(db, body.get("principalInvestigator", ""))
    # PI is optional at the DB level (Site.principal_investigator is a string column),
    # but the form already validates it as required.

    site_code = body.get("siteCode") or _generate_site_code(study, facility, pi)
    # Status is derived, not chosen. Every new site starts 'pending' and only
    # advances via the Site Selection Outcome milestone (selected -> active).
    # Any client-supplied status is ignored on purpose.
    status_value = "pending"

    # Site is its own entity, distinct from the facility it sits at.
    # Derived display name: "{Facility Name} – {Study Code}", e.g. "Tagore Hospital – DIA-001".
    derived_name = body.get("name") or (
        f"{facility.get('name')} – {study.study_id}" if facility.get("name") and study.study_id else (facility.get("name") or "Site")
    )

    site = Site(
        site_id=site_code,
        name=derived_name,
        code=site_code,
        location=", ".join(p for p in [facility.get("city"), facility.get("country")] if p) or None,
        principal_investigator=_user_display_name(pi) or None,
        principal_investigator_id=pi.id if pi else None,
        facility_external_id=facility["id"],
        address=facility.get("street"),
        city=facility.get("city"),
        country=facility.get("country"),
        status=status_value,
    )
    db.add(site)
    await db.flush()

    # Map the new site to the chosen study.
    db.add(StudySite(study_id=study.id, site_id=site.id))

    # Grant the creator STUDY_MANAGER visibility on this site so it shows in
    # /api/sites for them (used by the navbar + conversations selector).
    #
    # FK: user_role_assignments.user_id → users.user_id. Local JWT auth resolves
    # identity from Mongo `local_users` only — Postgres may not have a row yet
    # if Kafka dual-write missed or login never touched hub provision. Mirror
    # the creator here before inserting the assignment.
    # NOTE: insert via raw SQL because SQLAlchemy's `SQLEnum(UserRole)` would
    # serialise the Python enum *name* ("STUDY_MANAGER"), but the table has a
    # check constraint `chk_role_type` that only accepts the lowercase enum
    # *values* ('cra', 'study_manager', 'medical_monitor'). Casting to ::userrole
    # below sends the lowercase value directly.
    if current_user_id:
        uid_str = str(current_user_id).strip()
        creator = await _get_user(db, uid_str)
        if creator is None:
            try:
                mongo_db = await get_mongo_db()
                doc = await get_local_user_by_id(mongo_db, uid_str)
                if doc:
                    raw_em = doc.get("email")
                    em = raw_em.strip() if isinstance(raw_em, str) else None
                    if em == "":
                        em = None
                    dn = doc.get("displayName") or doc.get("name") or em or uid_str
                    if dn is not None and not isinstance(dn, str):
                        dn = str(dn)
                    creator = await crud.ensure_postgres_user_for_iam_mirror(
                        db,
                        user_id=uid_str,
                        email=em,
                        display_name=dn,
                    )
            except Exception as exc:
                logger.warning(
                    "[sites_pg] could not ensure Postgres row for creator user_id=%s: %s",
                    sfmt(uid_str),
                    exc,
                )

        if creator is not None:
            await db.execute(
                text(
                    """
                    INSERT INTO user_role_assignments (user_id, role, site_id, study_id, assigned_by)
                    VALUES (:uid, 'study_manager'::userrole, :sid, :stid, :uid)
                    """
                ),
                {"uid": uid_str, "sid": site.id, "stid": study.id},
            )
        else:
            logger.warning(
                "[sites_pg] skipped study_manager assignment — no Postgres users row for creator %r",
                sfmt(uid_str),
            )

    await db.commit()
    await db.refresh(site)

    # Drop a note on the per-(study, site) Public Notice Board so anyone else
    # who lands on this site immediately sees that it was just created — and
    # who created it. Best-effort: a notice-board failure must never bubble
    # up and undo the just-committed Site row, so the helper swallows its
    # own errors internally.
    try:
        from app.utils.system_notices import post_site_event_notice

        await post_site_event_notice(
            db,
            site_ref=site,
            study_ref=study,
            event_type="site_created",
            message=f"Site '{site.name or site.site_id}' was added to study '{study.name or study.study_id}'.",
            metadata={
                "site_id": str(site.id),
                "site_external_id": site.site_id,
                "study_id": str(study.id),
                "study_external_id": study.study_id,
            },
        )
    except Exception:
        logger.exception("[sites_pg] post_site_event_notice failed for site=%s", site.id)

    return _serialise_site(site, study=study, facility=facility, pi=pi)


async def update_site(
    db: AsyncSession,
    site_id_ref: str,
    body: dict,
) -> Optional[dict]:
    site = await _resolve_site(db, site_id_ref)
    if site is None:
        return None

    # Status is derived from the Site Selection Outcome milestone, never set by
    # hand on the edit form — a client-supplied `status` is intentionally ignored.

    # If the form changes the linked facility, re-copy address fields.
    facility_ref = body.get("facility")
    if facility_ref:
        facility = await _get_facility_row(facility_ref)
        if facility is not None:
            site.name = facility.get("name") or site.name
            site.address = facility.get("street")
            site.city = facility.get("city")
            site.country = facility.get("country")
            site.location = ", ".join(p for p in [facility.get("city"), facility.get("country")] if p) or None

    pi_ref = body.get("principalInvestigator")
    if pi_ref:
        pi = await _get_user(db, pi_ref)
        site.principal_investigator = _user_display_name(pi) or site.principal_investigator

    # Re-map study if changed.
    new_study_ref = body.get("study")
    if new_study_ref:
        new_study = await _get_or_mirror_study_from_iam(db, str(new_study_ref))
        if new_study is not None:
            existing = await db.execute(
                select(StudySite).where(StudySite.site_id == site.id, StudySite.study_id == new_study.id)
            )
            if existing.scalar_one_or_none() is None:
                db.add(StudySite(study_id=new_study.id, site_id=site.id))

    await db.commit()
    await db.refresh(site)

    study = await _study_for_site(db, site.id)
    facility = None  # Skip facility reload on the update response — extra round trip not worth it.
    pi = None
    if site.principal_investigator:
        # Best-effort lookup by display name → user; this is cosmetic.
        pi = (
            await db.execute(select(User).where(User.name == site.principal_investigator))
        ).scalar_one_or_none()
    return _serialise_site(site, study=study, facility=facility, pi=pi)


async def delete_site(db: AsyncSession, site_id_ref: str) -> bool:
    site = await _resolve_site(db, site_id_ref)
    if site is None:
        return False

    # Most FKs into sites.id already use ON DELETE CASCADE / SET NULL, but a
    # handful are NO ACTION and would block the delete. Wipe in dependency
    # order: grandchildren → children → site.
    agreement_children = (
        "agreement_document_comments",
        "agreement_review_documents",
        "agreement_changes",
        "agreement_reviewer_signatures",
        "agreement_signing_tokens",
        "agreement_signing_otps",
        "agreement_internal_signatures",
        "agreement_review_otps",
        "agreement_review_tokens",
        "agreement_signed_documents",
        "agreement_inline_comments",
        "agreement_documents",
        "agreement_comments",
    )
    study_site_children = (
        "feasibility_attachments",
        # feasibility_responses → feasibility_requests, so wipe responses first
        ("feasibility_responses",
         "DELETE FROM feasibility_responses WHERE request_id IN "
         "(SELECT id FROM feasibility_requests WHERE study_site_id IN "
         "(SELECT id FROM study_sites WHERE site_id = :sid))"),
        "feasibility_requests",
        "site_workflow_steps",
    )

    for child in agreement_children:
        await db.execute(
            text(
                f"DELETE FROM {child} WHERE agreement_id IN "
                f"(SELECT id FROM agreements WHERE site_id = :sid)"
            ),
            {"sid": site.id},
        )

    for entry in study_site_children:
        if isinstance(entry, tuple):
            await db.execute(text(entry[1]), {"sid": site.id})
        else:
            await db.execute(
                text(
                    f"DELETE FROM {entry} WHERE study_site_id IN "
                    f"(SELECT id FROM study_sites WHERE site_id = :sid)"
                ),
                {"sid": site.id},
            )

    for sql in (
        "DELETE FROM site_packages WHERE site_id = :sid",
        "DELETE FROM site_status_history WHERE site_id = :sid",
        "DELETE FROM site_statuses WHERE site_id = :sid",
        "DELETE FROM site_profiles WHERE site_id = :sid",
        "DELETE FROM site_documents WHERE site_id = :sid",
        "DELETE FROM agreements WHERE site_id = :sid",
        "DELETE FROM study_sites WHERE site_id = :sid",
        "DELETE FROM user_role_assignments WHERE site_id = :sid",
        "DELETE FROM user_sites WHERE site_id = :sid",
    ):
        await db.execute(text(sql), {"sid": site.id})

    await db.delete(site)
    await db.commit()
    return True


__all__ = [
    "list_sites",
    "get_site",
    "create_site",
    "update_site",
    "delete_site",
    # Used by selectinload import linter — re-exported so removing this import
    # in the future is a single edit.
    "selectinload",
]

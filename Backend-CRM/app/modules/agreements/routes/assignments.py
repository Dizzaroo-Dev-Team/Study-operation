"""assignments.py — "my CTA assignments" read endpoint.

Extracted (2026-06-18) from the retired ``types/cta/routes.py`` during the legacy
per-document-type retirement. The CTA *workflow* now runs on the general engine,
but the reviewer / sponsor-head **assignment inbox** (Navbar bell + WorkspaceHome
"My CTA Reviews & Signatures" card) still reads the ``cta_assignments`` table
directly. Only this read path survived the retirement; it lives here, in the
shared agreements routes, rather than in a type sub-module.

  GET /agreements/cta/my-assignments  (auth) — open CTAs where the caller is the
                                               assigned reviewer or sponsor head.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.models import Agreement, AgreementStatus
from app.modules.agreements.types.cta.models import CTAAssignment

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Legal"])


def _actor_id(current_user: dict) -> str:
    return str(current_user.get("user_id") or current_user.get("id") or current_user.get("email") or "unknown")


async def _resolve_caller_candidates(current_user: dict, db: AsyncSession) -> List[UUID]:
    """Return every UUID that could legitimately identify the caller against a
    ``cta_assignments.*_user_id`` column.

    Includes the canonical Postgres ``users.id`` (resolved via user_id-string →
    email → UUID) plus the JWT ``user_id`` parsed as UUID (legacy save rows
    stored the Mongo ``_id``). Empty list when no User row can be found.
    """
    from app.models import User  # noqa: PLC0415

    caller_id = _actor_id(current_user)
    caller_email = (current_user.get("email") or "").strip().lower()

    user_row = None
    try:
        if caller_id:
            r = await db.execute(select(User).where(User.user_id == caller_id))
            user_row = r.scalar_one_or_none()
        if user_row is None and caller_id:
            try:
                as_uuid = UUID(caller_id)
                r = await db.execute(select(User).where(User.id == as_uuid))
                user_row = r.scalar_one_or_none()
            except (ValueError, AttributeError, TypeError):
                pass
        if user_row is None and caller_email:
            r = await db.execute(select(User).where(User.email == caller_email))
            user_row = r.scalar_one_or_none()
    except Exception as exc:
        logger.warning(
            "_resolve_caller_candidates: DB lookup failed (user_id=%s, email=%s): %s",
            caller_id, caller_email, exc,
        )
        return []

    if user_row is None:
        return []

    candidates: List[UUID] = [user_row.id]
    try:
        legacy = UUID(str(user_row.user_id))
        if legacy != user_row.id:
            candidates.append(legacy)
    except (ValueError, AttributeError, TypeError):
        pass
    return candidates


@router.get("/agreements/cta/my-assignments", status_code=200)
async def my_cta_assignments(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return open CTAs where the current user is assigned as reviewer or sponsor head."""
    candidates = await _resolve_caller_candidates(current_user, db)
    if not candidates:
        logger.info("my-assignments: could not resolve caller (user_id=%s, email=%s)",
                    current_user.get("user_id"), current_user.get("email"))
        return []

    assignments_result = await db.execute(
        select(CTAAssignment).where(
            CTAAssignment.internal_reviewer_user_id.in_(candidates)
            | CTAAssignment.sponsor_head_user_id.in_(candidates)
        )
    )
    relevant = list(assignments_result.scalars().all())
    logger.info(
        "my-assignments: candidates=%s -> %d match(es)",
        [str(c) for c in candidates], len(relevant),
    )

    if not relevant:
        return []

    agreement_ids = [a.agreement_id for a in relevant]
    terminal = {AgreementStatus.EXECUTED, AgreementStatus.CLOSED}

    agreements_result = await db.execute(
        select(Agreement).where(
            Agreement.id.in_(agreement_ids),
            Agreement.status.notin_(list(terminal)),
        )
    )
    agreements_map = {a.id: a for a in agreements_result.scalars().all()}

    from app.models import Study, Site  # noqa: PLC0415
    study_ids = {a.study_id for a in agreements_map.values() if a.study_id}
    site_ids = {a.site_id for a in agreements_map.values()}

    study_names: Dict[Any, str] = {}
    if study_ids:
        studies_result = await db.execute(select(Study).where(Study.id.in_(study_ids)))
        for s in studies_result.scalars().all():
            study_names[s.id] = getattr(s, "study_name", None) or getattr(s, "name", None) or str(s.id)

    site_names: Dict[Any, str] = {}
    if site_ids:
        sites_result = await db.execute(select(Site).where(Site.id.in_(site_ids)))
        for s in sites_result.scalars().all():
            site_names[s.id] = getattr(s, "name", None) or getattr(s, "site_id", None) or str(s.id)

    output = []
    for assignment in relevant:
        agreement = agreements_map.get(assignment.agreement_id)
        if agreement is None:
            continue
        role = (
            "reviewer"
            if assignment.internal_reviewer_user_id in candidates
            else "sponsor_head"
        )
        output.append({
            "agreement_id": str(agreement.id),
            "study_id": str(agreement.study_id) if agreement.study_id else None,
            "site_id": str(agreement.site_id) if agreement.site_id else None,
            "study_name": study_names.get(agreement.study_id, ""),
            "site_name": site_names.get(agreement.site_id, ""),
            "role": role,
            "status": agreement.status.value,
            "assigned_at": assignment.created_at.isoformat() if assignment.created_at else None,
        })

    return output

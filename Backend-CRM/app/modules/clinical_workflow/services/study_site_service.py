"""StudySite get-or-create with race-condition handling.

This helper was previously a top-level function in clinical_workflow.py and is
imported by legal_docs.py and feasibility submit. The race-condition handling
(select -> insert -> catch IntegrityError -> retry select) is non-trivial
enough to deserve its own module + future tests.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Site, StudySite

logger = logging.getLogger(__name__)


# Maps the Site Selection Outcome decision (recorded on the workflow step) to
# the legacy Site.status string shown in Study Setup -> Site Setup. This is the
# single source of truth for the bridge between the milestone workflow and the
# site's headline status — the status is no longer picked by hand on the form.
#   selected     -> 'active'  (site proceeds to start-up)
#   not_selected -> 'pending' (stays pending; a reason is captured in the
#                              step's comments — suspended/terminated are
#                              reserved for later lifecycle stages)
SELECTION_OUTCOME_STATUS = {
    "selected": "active",
    "not_selected": "pending",
}


async def sync_site_status_from_selection(
    db: AsyncSession,
    study_site_id: UUID,
    decision: str | None,
) -> str | None:
    """Flip the linked Site's status from a Site Selection Outcome decision.

    Resolves the StudySite -> Site and applies SELECTION_OUTCOME_STATUS. Does
    NOT commit — the caller owns the transaction so the status change lands in
    the same commit as the workflow step update (audit-consistent).

    Returns the new status string when applied, else None (unknown decision or
    site not found).
    """
    new_status = SELECTION_OUTCOME_STATUS.get((decision or "").lower())
    if new_status is None:
        return None

    study_site = (
        await db.execute(select(StudySite).where(StudySite.id == study_site_id))
    ).scalar_one_or_none()
    if study_site is None or study_site.site_id is None:
        logger.warning(
            "site status sync skipped: no StudySite/site for study_site_id=%s",
            study_site_id,
        )
        return None

    site = (
        await db.execute(select(Site).where(Site.id == study_site.site_id))
    ).scalar_one_or_none()
    if site is None:
        logger.warning(
            "site status sync skipped: no Site row for id=%s", study_site.site_id
        )
        return None

    if site.status != new_status:
        site.status = new_status
        logger.info(
            "site %s status -> %s (selection outcome=%s)",
            site.id, new_status, decision,
        )
    return new_status


async def _ensure_notice_board_for(study_id: UUID, site_id: UUID) -> None:
    """Best-effort: make sure the (study, site) notice board exists.

    Imported lazily to avoid a circular import (communications service
    imports crud, which transitively imports this module via clinical
    workflow). Failures are logged and swallowed — the notice board is
    also pre-created by the inbox-open path, so this is a "first try"
    rather than the sole guarantee.
    """
    try:
        from app.modules.communications.repositories import ConversationRepository
        await ConversationRepository.find_or_create_pinned_notice_board(
            site_id=str(site_id),
            study_id=str(study_id),
        )
    except Exception as exc:
        logger.warning(
            "Failed to eagerly create notice board for study=%s site=%s: %s",
            study_id, site_id, exc,
        )


async def get_or_create_study_site(
    db: AsyncSession,
    study_id: UUID,
    site_id: UUID,
) -> StudySite:
    """
    Get or create a study_site mapping.

    Returns the StudySite record for the given study_id and site_id.
    Handles race conditions where multiple requests try to create the same mapping.

    Side effect: also ensures the Public Notice Board conversation for this
    (study, site) exists. The notice board is part of the (study, site)
    lifecycle — it must be present from the moment the mapping exists, not
    lazily on first inbox open.
    """
    try:
        # Try to find existing mapping first
        result = await db.execute(
            select(StudySite).where(
                StudySite.study_id == study_id,
                StudySite.site_id == site_id,
            )
        )
        study_site = result.scalar_one_or_none()

        if study_site:
            # Mapping already existed; still ensure the notice board for it.
            # The find_or_create call is fast (single find_one when present).
            await _ensure_notice_board_for(study_id, site_id)
            return study_site

        # Try to create new mapping
        # Handle race condition: if another request created it between select and insert,
        # we'll catch the IntegrityError and retry the select
        try:
            study_site = StudySite(
                study_id=study_id,
                site_id=site_id,
            )
            db.add(study_site)
            await db.flush()
            await db.refresh(study_site)
            # New mapping landed — create the notice board now so the inbox
            # is populated from minute 1.
            await _ensure_notice_board_for(study_id, site_id)
            return study_site
        except Exception as insert_error:
            # Check if it's a unique constraint violation (race condition)
            error_msg = str(insert_error)
            if "unique constraint" in error_msg.lower() or "duplicate key" in error_msg.lower() or "uq_study_site" in error_msg:
                # Another request created it, so fetch it now
                await db.rollback()
                result = await db.execute(
                    select(StudySite).where(
                        StudySite.study_id == study_id,
                        StudySite.site_id == site_id,
                    )
                )
                study_site = result.scalar_one_or_none()
                if study_site:
                    # Race-winner path: still ensure the notice board exists
                    # for this mapping. The other request may not have
                    # reached the notice-board step yet.
                    await _ensure_notice_board_for(study_id, site_id)
                    return study_site
                # If still not found, re-raise the original error
                raise insert_error
            # For other errors, re-raise
            raise insert_error

    except HTTPException:
        raise
    except Exception as e:
        # If table doesn't exist, raise a helpful error
        error_msg = str(e)
        if "does not exist" in error_msg or "relation" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail="study_sites table does not exist. Please run the migration script: python create_study_site_mapping.py",
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get or create study_site mapping: {error_msg}",
        )

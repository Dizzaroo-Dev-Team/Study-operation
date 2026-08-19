"""Workflow-completion → site-readiness bridge.

THE documented integration point between the general workflow engine and site-readiness
gating. When an agreement-backed workflow instance completes on the engine, the engine
calls :func:`complete_site_milestone_for_executed_agreement` (see
``app/modules/workflows/service.py``). For a CDA agreement this completes the matching
``SiteWorkflowStep.CDA_EXECUTION`` milestone — exactly what the legacy per-type CDA
signing path did — so site activation/readiness gating stays correct while CDA rides the
general engine.

General by construction: it self-checks the agreement's template type and only acts when
there is a site milestone to complete (CDA today); for any other type it is a safe no-op.
Lives in the shared services layer (NOT in ``types/cda``) so it survives the retirement
of the per-type modules.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    Agreement,
    Site,
    SiteWorkflowStep,
    StepStatus,
    StudySite,
    StudyTemplate,
    WorkflowStepName,
)

logger = logging.getLogger(__name__)

# Agreement template type -> the site-readiness milestone its execution completes.
# The single, explicit place the engine↔readiness mapping lives. Add an entry here
# (not scattered `if type ==` branches) if a future type also gates a site milestone.
_TYPE_TO_SITE_MILESTONE = {
    "CDA": WorkflowStepName.CDA_EXECUTION,
}


async def complete_site_milestone_for_executed_agreement(
    db: AsyncSession,
    agreement: Agreement,
    completed_by: Optional[str] = None,
) -> Any:
    """Complete the site-readiness milestone for an executed agreement.

    Determines the agreement's template type, maps it to its site milestone via
    ``_TYPE_TO_SITE_MILESTONE`` (CDA → CDA_EXECUTION today), resolves the StudySite, and
    marks the matching ``SiteWorkflowStep`` COMPLETED with the same ``step_data`` the
    legacy path wrote. Idempotent (no-op if already COMPLETED) and defensive (no-op +
    log when the type has no milestone, or required data is missing). Returns the
    updated step, or None when nothing was done.
    """
    # Lazy import to keep this module free of clinical_workflow at import time.
    from app.modules.clinical_workflow.services.study_site_service import get_or_create_study_site

    # ALWAYS reload the agreement with its documents eagerly. Accessing a lazy
    # relationship (agreement.documents) on an async session would raise MissingGreenlet
    # when the caller passed an object from db.get() that didn't eager-load documents — so
    # never rely on the passed object's loaded state; re-query by id (the PK is always
    # available) with selectinload.
    agreement = (await db.execute(
        select(Agreement)
        .where(Agreement.id == agreement.id)
        .options(selectinload(Agreement.documents))
    )).scalar_one_or_none()
    if not agreement or not agreement.documents:
        logger.info("site_readiness_bridge: agreement has no documents; nothing to complete")
        return None

    first_doc = agreement.documents[0]
    if not first_doc.created_from_template_id:
        return None

    template = (await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == first_doc.created_from_template_id)
    )).scalar_one_or_none()
    if not template:
        return None

    template_type = template.template_type.value if hasattr(template.template_type, "value") else str(template.template_type)
    milestone = _TYPE_TO_SITE_MILESTONE.get(template_type)
    if milestone is None:
        # Not a type that gates a site milestone — safe no-op (general).
        return None

    if not agreement.site_id:
        logger.warning("site_readiness_bridge: agreement %s has no site_id", agreement.id)
        return None

    site = (await db.execute(select(Site).where(Site.id == agreement.site_id))).scalar_one_or_none()
    if not site:
        logger.warning("site_readiness_bridge: site not found for agreement %s", agreement.id)
        return None

    # Resolve the StudySite (study-specific milestone).
    study_site = None
    if getattr(agreement, "study_site_id", None):
        study_site = (await db.execute(
            select(StudySite).where(StudySite.id == agreement.study_site_id)
        )).scalar_one_or_none()
    if not study_site and getattr(agreement, "study_id", None):
        try:
            study_uuid = UUID(str(agreement.study_id))
        except (ValueError, TypeError):
            study_uuid = None
        if study_uuid:
            study_site = await get_or_create_study_site(db, study_uuid, site.id)
    if not study_site:
        logger.warning("site_readiness_bridge: study site not found for agreement %s", agreement.id)
        return None

    # Get or create the milestone step.
    step = (await db.execute(
        select(SiteWorkflowStep).where(
            SiteWorkflowStep.study_site_id == study_site.id,
            SiteWorkflowStep.step_name == milestone,
        )
    )).scalar_one_or_none()
    if not step:
        step = SiteWorkflowStep(
            study_site_id=study_site.id,
            step_name=milestone,
            status=StepStatus.NOT_STARTED,
            step_data={},
        )
        db.add(step)
        await db.flush()

    if step.status == StepStatus.COMPLETED:
        logger.info("site_readiness_bridge: %s already completed for agreement %s", milestone, agreement.id)
        return step

    now = datetime.now(timezone.utc)
    step.status = StepStatus.COMPLETED
    step.completed_at = now
    step.completed_by = completed_by or "system"
    step.updated_at = now
    # REASSIGN (don't mutate in place): a plain JSON column does not track in-place dict
    # mutation, so step.step_data["x"]=y would not persist. Build a new dict and assign it.
    new_data = dict(step.step_data or {})
    new_data["completed_via_agreement"] = True
    new_data["agreement_id"] = str(agreement.id)
    new_data["cda_status"] = "CDA_COMPLETED"
    step.step_data = new_data

    await db.flush()
    logger.info(
        "site_readiness_bridge: completed %s for agreement %s (site %s)",
        milestone, agreement.id, getattr(site, "site_id", site.id),
    )
    return step

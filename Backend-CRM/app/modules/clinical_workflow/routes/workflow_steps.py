"""REST API: per-site workflow step state machine (Under Consideration stage).

Three endpoints:
  GET    /sites/{site_id}/workflow/steps              -- read all steps + lock state
  POST   /sites/{site_id}/workflow/steps/{step_name}  -- advance / update a specific step
  DELETE /sites/{site_id}/workflow/steps              -- reset all steps for a (site, study)

The POST handler is the largest single endpoint in the codebase (525 lines).
It owns the CDA send/sign/upload sub-states and decides when the next step
in the chain unlocks.
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.auth import get_current_user, get_current_user_optional
from app.db import get_db
from app.models import (
    Agreement,
    AgreementStatus,
    DocumentCategory,
    DocumentType,
    FeasibilityRequestStatus,
    ProjectFeasibilityCustomQuestion,
    ReviewStatus,
    Site,
    SiteDocument,
    SiteWorkflowStep,
    StepStatus,
    Study,
    StudySite,
    WorkflowStepName,
)
from app.modules.clinical_workflow.services.cda_documents import (
    generate_cda_document_html,
    get_cda_document_path,
)
from app.modules.clinical_workflow.services.study_site_service import (
    get_or_create_study_site,
    sync_site_status_from_selection,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Clinical Workflow"])


# Study-specific workflow steps that require study_site_id (rather than site_id)
STUDY_SPECIFIC_STEPS = {
    WorkflowStepName.SITE_IDENTIFICATION,
    WorkflowStepName.CDA_EXECUTION,
    WorkflowStepName.FEASIBILITY,
    WorkflowStepName.SITE_SELECTION_OUTCOME,
}


@router.get("/sites/{site_id}/workflow/steps", response_model=schemas.WorkflowStepsResponse)
async def get_site_workflow_steps(
    site_id: str,
    study_id: Optional[str] = Query(
        None,
        description=(
            "Study identifier (UUID or external study_id string). "
            "Required for study-specific workflow steps (Site Identification, CDA, Feasibility, Site Selection Outcome). "
            "If not provided, uses the site's default study_id."
        ),
    ),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all workflow steps for a site.
    For study-specific steps (Site Identification, CDA, Feasibility, Site Selection Outcome),
    requires study_id to scope steps to a (study + site) combination.
    Returns step states including locked/unlocked status based on dependencies.
    """
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

    # Capture the DB UUID for this site once so we don't trigger any lazy loads later.
    # Using a local primitive avoids async IO from ORM attribute access in unexpected places.
    site_db_id = site.id
    
    # Resolve study_id and StudySite mapping
    resolved_study_id = None
    study_site = None
    if study_id:
        try:
            resolved_study_id = UUID(str(study_id))
            study_result = await db.execute(select(Study).where(Study.id == resolved_study_id))
            study = study_result.scalar_one_or_none()
            if not study:
                raise HTTPException(status_code=404, detail="Study not found")
        except (ValueError, TypeError):
            study_result = await db.execute(select(Study).where(Study.study_id == study_id))
            study = study_result.scalar_one_or_none()
            if not study:
                raise HTTPException(status_code=404, detail="Study not found")
            resolved_study_id = study.id

        # Get or create study_site mapping for the explicit study_id
        try:
            study_site = await get_or_create_study_site(db, resolved_study_id, site_db_id)
        except HTTPException:
            # Re-raise HTTP exceptions (they have helpful messages)
            raise
        except Exception as e:
            # If study_sites table doesn't exist, provide helpful error
            error_msg = str(e)
            if "does not exist" in error_msg or "relation" in error_msg.lower():
                raise HTTPException(
                    status_code=500,
                    detail="study_sites table does not exist. Please run the migration script: python create_study_site_mapping.py"
                )
            raise
    else:
        # No explicit study_id – resolve via existing StudySite mapping for this site
        study_site_result = await db.execute(
            select(StudySite)
            .where(StudySite.site_id == site_db_id)
            .order_by(StudySite.created_at)
        )
        study_site = study_site_result.scalars().first()
        if not study_site:
            raise HTTPException(status_code=404, detail="Study site mapping not found for site")
        resolved_study_id = study_site.study_id
    
    # Get all steps for this site/study combination
    # For study-specific steps, use study_site_id; for others, use site_id
    # Build query for study-specific steps
    study_specific_steps_query = select(SiteWorkflowStep).where(
        SiteWorkflowStep.study_site_id == study_site.id
    )
    # Filter by step names - need to check each enum value
    study_specific_conditions = [
        SiteWorkflowStep.step_name == step_enum
        for step_enum in STUDY_SPECIFIC_STEPS
    ]
    if study_specific_conditions:
        study_specific_steps_query = study_specific_steps_query.where(
            or_(*study_specific_conditions)
        )
    
    # Build query for non-study-specific steps (if any exist in the future)
    # For now, all 4 steps are study-specific, so this query may return empty
    other_steps_query = select(SiteWorkflowStep).where(
        SiteWorkflowStep.site_id == site_db_id,
        SiteWorkflowStep.study_site_id.is_(None)  # Only non-study-specific steps
    )
    
    # Execute both queries and combine results
    try:
        study_specific_result = await db.execute(study_specific_steps_query)
        other_result = await db.execute(other_steps_query)
        all_steps = list(study_specific_result.scalars().all()) + list(other_result.scalars().all())
    except Exception as e:
        error_msg = str(e)
        # Check if it's a table/column doesn't exist error
        if "does not exist" in error_msg or "relation" in error_msg.lower() or "column" in error_msg.lower():
            raise HTTPException(
                status_code=500,
                detail=f"Database schema error. Please run the migration script: python create_study_site_mapping.py. Error: {error_msg}"
            )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch workflow steps: {error_msg}"
        )
    # Index by both enum instance and string value for flexible lookup
    existing_steps = {}
    for step in all_steps:
        # step.step_name is an enum instance when retrieved from DB
        step_name_enum = step.step_name
        step_name_value = step_name_enum.value if hasattr(step_name_enum, 'value') else str(step_name_enum)
        existing_steps[step_name_enum] = step
        existing_steps[step_name_value] = step
    
    # Ensure all steps exist (create if not)
    step_order = [
        WorkflowStepName.SITE_IDENTIFICATION,
        WorkflowStepName.CDA_EXECUTION,
        WorkflowStepName.FEASIBILITY,
        WorkflowStepName.SITE_SELECTION_OUTCOME,
    ]
    
    steps_list = []
    for step_name_enum in step_order:
        step_name_value = step_name_enum.value
        step = existing_steps.get(step_name_value)

        if not step:
            # Concurrent GETs from the same browser session (React StrictMode
            # double-mount, parallel module loads on first deploy) can both
            # SELECT empty and race here. INSERT … ON CONFLICT DO NOTHING
            # makes the create idempotent against either UNIQUE
            # (study_site_id, step_name) or (site_id, step_name); on conflict
            # we re-fetch the row another request just inserted.
            if step_name_enum in STUDY_SPECIFIC_STEPS:
                ins_values = {
                    "study_site_id": study_site.id,
                    "step_name": step_name_enum,
                    "status": StepStatus.NOT_STARTED,
                    "step_data": {},
                }
                conflict_cols = ["study_site_id", "step_name"]
                # Matches the partial UNIQUE index `uq_study_site_workflow_step`.
                index_predicate = SiteWorkflowStep.study_site_id.isnot(None)
                refetch_filter = and_(
                    SiteWorkflowStep.study_site_id == study_site.id,
                    SiteWorkflowStep.step_name == step_name_enum,
                )
            else:
                ins_values = {
                    "site_id": site.id,
                    "step_name": step_name_enum,
                    "status": StepStatus.NOT_STARTED,
                    "step_data": {},
                }
                conflict_cols = ["site_id", "step_name"]
                # Matches the partial UNIQUE index `uq_site_workflow_step`.
                index_predicate = SiteWorkflowStep.site_id.isnot(None)
                refetch_filter = and_(
                    SiteWorkflowStep.site_id == site.id,
                    SiteWorkflowStep.study_site_id.is_(None),
                    SiteWorkflowStep.step_name == step_name_enum,
                )

            await db.execute(
                pg_insert(SiteWorkflowStep)
                .values(**ins_values)
                .on_conflict_do_nothing(
                    index_elements=conflict_cols,
                    index_where=index_predicate,
                )
            )
            await db.flush()

            step = (
                await db.execute(select(SiteWorkflowStep).where(refetch_filter))
            ).scalar_one_or_none()
            if step is None:
                # Should not happen — conflict-do-nothing + refetch guarantees one row.
                raise HTTPException(
                    status_code=500,
                    detail=f"Could not materialise workflow step {step_name_enum.value}",
                )

        # --- CDA reconciliation (legacy external signing before JSONB tracking fix) ---
        # If the CDA HTML file and/or SiteDocument exists but step_data wasn't persisted (JSONB tracking),
        # automatically reconcile the CDA step back to SIGNED so CRM can enable "Complete Step".
        if step_name_enum == WorkflowStepName.CDA_EXECUTION:
            try:
                from sqlalchemy.orm.attributes import flag_modified

                sd = step.step_data or {}
                cda_required_val = sd.get("cda_required")
                cda_required_truthy = str(cda_required_val).lower() in ("true", "1", "yes")
                cda_status_lower = str(sd.get("cda_status") or "").lower()
                cda_doc_path = sd.get("cda_document_path")

                # Only reconcile when CDA is required, we have a document path, and we're not already signed
                if cda_required_truthy and cda_doc_path and cda_status_lower != "signed":
                    # Look for a signed CDA SiteDocument that matches the snapshot file
                    signed_doc_result = await db.execute(
                        select(SiteDocument)
                        .where(
                            SiteDocument.site_id == site.id,
                            SiteDocument.category == DocumentCategory.SIGNED_CDA,
                            SiteDocument.file_path == str(cda_doc_path),
                        )
                        .order_by(SiteDocument.uploaded_at.desc())
                        .limit(1)
                    )
                    signed_doc = signed_doc_result.scalar_one_or_none()

                    if signed_doc:
                        # Derive the document URL from the snapshot filename (stem)
                        try:
                            snapshot_stem = Path(str(cda_doc_path)).stem
                        except Exception:
                            snapshot_stem = None

                        if snapshot_stem:
                            sd.update(
                                {
                                    "cda_status": "SIGNED",
                                    "final_document_url": f"/api/cda/document/{snapshot_stem}",
                                    "cda_document_url": f"/api/cda/document/{snapshot_stem}",
                                    "signed_cda_document_id": str(signed_doc.id),
                                    # Best-effort: treat uploaded_at as the time the site signed
                                    "site_signed_at": sd.get("site_signed_at")
                                    or (signed_doc.uploaded_at.isoformat() if signed_doc.uploaded_at else None),
                                    # Token should no longer be usable once we consider it signed
                                    "cda_sign_token": None,
                                    "cda_sign_token_expires_at": None,
                                }
                            )
                            step.step_data = sd.copy()
                            step.updated_at = datetime.now(timezone.utc)
                            flag_modified(step, "step_data")
                            logger.info(
                                f"Reconciled CDA step to SIGNED from SiteDocument: step_id={step.id}, signed_doc_id={signed_doc.id}"
                            )
            except Exception as e:
                logger.warning(f"CDA reconciliation skipped due to error: {e}")
        
        # Determine if step should be locked based on previous step completion or workflow lock
        is_locked = False
        
        # Check if workflow is locked (Do Not Proceed was selected in Site Identification)
        # For study-specific steps, look up by study_site_id context
        site_ident_step = existing_steps.get(WorkflowStepName.SITE_IDENTIFICATION) or existing_steps.get(WorkflowStepName.SITE_IDENTIFICATION.value)
        workflow_locked = False
        if site_ident_step:
            # Check if decision was "Do Not Proceed"
            decision = site_ident_step.step_data.get('decision') if site_ident_step.step_data else None
            workflow_locked = (decision == 'do_not_proceed') or (site_ident_step.step_data.get('workflow_locked') is True)
        
        if step_name_enum == WorkflowStepName.SITE_IDENTIFICATION:
            # First step is never locked
            is_locked = False
        elif workflow_locked:
            # If workflow is locked (Do Not Proceed), all subsequent steps are locked
            is_locked = True
        elif step_name_enum == WorkflowStepName.CDA_EXECUTION:
            # Locked if site identification not completed OR if decision was "Do Not Proceed"
            if not site_ident_step or site_ident_step.status != StepStatus.COMPLETED:
                is_locked = True
        elif step_name_enum == WorkflowStepName.FEASIBILITY:
            # Locked if CDA not completed
            cda_step = existing_steps.get(WorkflowStepName.CDA_EXECUTION) or existing_steps.get(WorkflowStepName.CDA_EXECUTION.value)
            if not cda_step or cda_step.status != StepStatus.COMPLETED:
                is_locked = True
        elif step_name_enum == WorkflowStepName.SITE_SELECTION_OUTCOME:
            # Locked if feasibility not completed
            feasibility_step = existing_steps.get(WorkflowStepName.FEASIBILITY) or existing_steps.get(WorkflowStepName.FEASIBILITY.value)
            if not feasibility_step or feasibility_step.status != StepStatus.COMPLETED:
                is_locked = True
        
        # Update step status based on lock state
        if is_locked:
            # If step should be locked and it's not started, set to LOCKED
            if step.status == StepStatus.NOT_STARTED:
                step.status = StepStatus.LOCKED
        else:
            # If step should NOT be locked but status is LOCKED, change to NOT_STARTED
            if step.status == StepStatus.LOCKED:
                step.status = StepStatus.NOT_STARTED
        
        steps_list.append({
            "step_name": step.step_name.value if hasattr(step.step_name, 'value') else str(step.step_name),
            "status": step.status.value if hasattr(step.status, 'value') else str(step.status),
            "step_data": step.step_data or {},
            "completed_at": step.completed_at.isoformat() if step.completed_at else None,
            "completed_by": step.completed_by,
            "created_at": step.created_at,
            "updated_at": step.updated_at,
        })
    
    await db.commit()
    
    return {
        "site_id": str(site.id),
        "steps": steps_list
    }

@router.post("/sites/{site_id}/workflow/steps/{step_name}")
async def update_workflow_step(
    site_id: str,
    step_name: str,
    update_data: schemas.WorkflowStepUpdate,
    study_id: Optional[str] = Query(
        None,
        description=(
            "Study identifier (UUID or external study_id string). "
            "Required for study-specific workflow steps (Site Identification, CDA, Feasibility, Site Selection Outcome). "
            "If not provided, uses the site's default study_id."
        ),
    ),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Update a workflow step state.
    For study-specific steps, requires study_id to scope steps to a (study + site) combination.
    Enforces sequential dependencies - cannot complete a step if previous step is not completed.
    """
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
    
    # Validate step name
    try:
        step_enum = WorkflowStepName(step_name)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid step name: {step_name}")
    
    # Resolve study_id for study-specific steps
    resolved_study_id = None
    study_site = None
    if step_enum in STUDY_SPECIFIC_STEPS:
        if study_id:
            try:
                resolved_study_id = UUID(str(study_id))
                study_result = await db.execute(select(Study).where(Study.id == resolved_study_id))
                study = study_result.scalar_one_or_none()
                if not study:
                    raise HTTPException(status_code=404, detail="Study not found")
            except (ValueError, TypeError):
                study_result = await db.execute(select(Study).where(Study.study_id == study_id))
                study = study_result.scalar_one_or_none()
                if not study:
                    raise HTTPException(status_code=404, detail="Study not found")
                resolved_study_id = study.id

            # Get or create study_site mapping for the explicit study_id
            study_site = await get_or_create_study_site(db, resolved_study_id, site.id)
        else:
            # No explicit study_id – resolve via existing StudySite mapping for this site
            study_site_result = await db.execute(
                select(StudySite)
                .where(StudySite.site_id == site.id)
                .order_by(StudySite.created_at)
            )
            study_site = study_site_result.scalars().first()
            if not study_site:
                raise HTTPException(status_code=404, detail="Study site mapping not found for site")
            resolved_study_id = study_site.study_id
    
    # Get or create step
    if step_enum in STUDY_SPECIFIC_STEPS:
        step_result = await db.execute(
            select(SiteWorkflowStep).where(
                SiteWorkflowStep.study_site_id == study_site.id,
                SiteWorkflowStep.step_name == step_enum
            )
        )
    else:
        step_result = await db.execute(
            select(SiteWorkflowStep).where(
                SiteWorkflowStep.site_id == site.id,
                SiteWorkflowStep.step_name == step_enum
            )
        )
    step = step_result.scalar_one_or_none()
    
    if not step:
        if step_enum in STUDY_SPECIFIC_STEPS:
            step = SiteWorkflowStep(
                study_site_id=study_site.id,
                step_name=step_enum,
                status=StepStatus.NOT_STARTED,
                step_data={}
            )
        else:
            step = SiteWorkflowStep(
                site_id=site.id,
                step_name=step_enum,
                status=StepStatus.NOT_STARTED,
                step_data={}
            )
        db.add(step)
    
    # PART 3: Prevent Manual Override for CDA Execution
    # If CDA Execution step and CDA is required, check if CDA Agreement exists
    is_cda_step = step_enum == WorkflowStepName.CDA_EXECUTION
    if is_cda_step and update_data.status == StepStatus.COMPLETED.value:
        # Check if CDA is required (check step_data)
        cda_required_value = step.step_data.get('cda_required') if step.step_data else None
        cda_required = False
        cda_not_applicable = False
        
        if cda_required_value is True or str(cda_required_value).lower() in ['true', 'yes', '1']:
            cda_required = True
        elif cda_required_value == 'not_applicable' or str(cda_required_value).lower() == 'not_applicable':
            cda_not_applicable = True
        
        # If CDA is required (Yes), check if Agreement is executed
        if cda_required:
            # Check if CDA Agreement exists and is executed
            from app.models import Agreement, AgreementDocument, StudyTemplate, TemplateType
            from sqlalchemy.orm import selectinload
            
            # Get study_id for querying agreements
            study_id_for_query = None
            if study_site and study_site.study_id:
                study_id_for_query = study_site.study_id
            
            # Find CDA agreements for this Study + Site pair
            # Prefer StudySite-based scoping when available, with legacy fallback.
            cda_agreements_query = None

            if study_id_for_query:
                # Try to resolve StudySite first
                study_site_result = await db.execute(
                    select(StudySite)
                    .where(StudySite.site_id == site.id)
                    .where(StudySite.study_id == study_id_for_query)
                )
                study_site = study_site_result.scalar_one_or_none()
            else:
                study_site = None

            if not (study_site and study_site.id):
                logger.info(
                    "CDA milestone check: no StudySite mapping for study=%s, site=%s; treating as no CDA agreement",
                    str(study_id_for_query),
                    str(site.id),
                )
                cda_agreements = []
            else:
                logger.info(
                    "CDA milestone check via study_site_id=%s (study=%s, site=%s)",
                    str(study_site.id),
                    str(study_id_for_query),
                    str(site.id),
                )
                cda_agreements_query = select(Agreement).where(
                    Agreement.study_site_id == study_site.id
                )

                cda_agreements_result = await db.execute(
                    cda_agreements_query.options(selectinload(Agreement.documents))
                )
                cda_agreements = cda_agreements_result.scalars().all()
            
            # Filter for CDA type agreements
            cda_agreement_executed = False
            for agreement in cda_agreements:
                if agreement.documents and len(agreement.documents) > 0:
                    first_doc = agreement.documents[0]
                    if first_doc.created_from_template_id:
                        template_result = await db.execute(
                            select(StudyTemplate).where(StudyTemplate.id == first_doc.created_from_template_id)
                        )
                        template = template_result.scalar_one_or_none()
                        if template and template.template_type == TemplateType.CDA:
                            # This is a CDA agreement
                            if agreement.status == AgreementStatus.EXECUTED:
                                cda_agreement_executed = True
                                break
            
            if not cda_agreement_executed:
                # CDA Agreement doesn't exist or is not executed
                raise HTTPException(
                    status_code=400,
                    detail="CDA must be executed via Agreement module. Please create and execute a CDA Agreement first."
                )
            # If CDA Agreement is executed, mark in step_data to skip old validation
            # merged_step_data will be created later from step.step_data, so setting it here is sufficient
            if step.step_data is None:
                step.step_data = {}
            step.step_data['completed_via_agreement'] = True
            # If CDA Agreement is executed, allow completion
        # If CDA is Not Applicable or No, allow manual completion (no Agreement check needed)
        # Comment requirement for "No" is handled by frontend validation
    
    # Check dependencies and completion requirements before allowing completion
    if update_data.status == StepStatus.COMPLETED.value:
        step_order = [
            WorkflowStepName.SITE_IDENTIFICATION,
            WorkflowStepName.CDA_EXECUTION,
            WorkflowStepName.FEASIBILITY,
            WorkflowStepName.SITE_SELECTION_OUTCOME,
        ]
        current_index = step_order.index(step_enum)
        
        # Check previous step completion and workflow lock status
        if current_index > 0:
            prev_step_name = step_order[current_index - 1]
            # For study-specific steps, use study_site_id; otherwise use site_id
            if prev_step_name in STUDY_SPECIFIC_STEPS and step_enum in STUDY_SPECIFIC_STEPS:
                prev_result = await db.execute(
                    select(SiteWorkflowStep).where(
                        SiteWorkflowStep.study_site_id == study_site.id,
                        SiteWorkflowStep.step_name == prev_step_name
                    )
                )
            else:
                prev_result = await db.execute(
                    select(SiteWorkflowStep).where(
                        SiteWorkflowStep.site_id == site.id,
                        SiteWorkflowStep.step_name == prev_step_name
                    )
                )
            prev_step = prev_result.scalar_one_or_none()
            
            if not prev_step or prev_step.status != StepStatus.COMPLETED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot complete {step_name}: previous step {prev_step_name.value} is not completed"
                )
            
            # Check if previous step locked the workflow (e.g., "do_not_proceed", "not_required", etc.)
            prev_step_data = prev_step.step_data or {}
            if prev_step_data.get('workflow_locked') is True:
                # Determine lock reason based on which step locked it
                if prev_step_name == WorkflowStepName.SITE_IDENTIFICATION:
                    reason = 'Site Identification decision was "Do Not Proceed"'
                elif prev_step_name == WorkflowStepName.CDA_EXECUTION:
                    cda_required = prev_step_data.get('cda_required')
                    if cda_required is False:
                        reason = 'CDA Execution was marked as "Not Required"'
                    elif cda_required == 'not_applicable':
                        reason = 'CDA Execution was marked as "Not Applicable"'
                    else:
                        reason = f'{prev_step_name.value} locked the workflow'
                else:
                    reason = f'{prev_step_name.value} locked the workflow'
                
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot complete {step_name}: {reason} - workflow is locked"
                )
        
        # Step-specific completion validation
        merged_step_data = {**(step.step_data or {}), **(update_data.step_data or {})}
        
        if step_enum == WorkflowStepName.SITE_IDENTIFICATION:
            # Site Identification now only requires a decision to complete.
            # Uploading a Site Visibility Report is optional and handled via Site Documents.
            if not merged_step_data.get('decision'):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot complete Site Identification: Decision is required"
                )
            # If "Do Not Proceed", lock all subsequent steps
            if merged_step_data.get('decision') == 'do_not_proceed':
                merged_step_data['workflow_locked'] = True
        
        elif step_enum == WorkflowStepName.CDA_EXECUTION:
            # Must have cda_required decision
            if merged_step_data.get('cda_required') is None:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot complete CDA Execution: Please indicate if CDA is required"
                )
            # If CDA is required, check if it was completed via Agreement module
            # The validation above (lines 614-670) already checks if CDA Agreement is executed
            # If we reach here with CDA required, it means either:
            # 1. CDA Agreement is executed (validation passed above), OR
            # 2. This is a legacy flow with signed_cda_document_id
            if merged_step_data.get('cda_required') is True:
                # Check if completed via Agreement module (new flow)
                completed_via_agreement = merged_step_data.get('completed_via_agreement') or step.step_data.get('completed_via_agreement')
                
                if not completed_via_agreement:
                    # Legacy flow - check for signed_cda_document_id
                    cda_status_value = str(merged_step_data.get('cda_status') or '').upper()
                    # Accept both legacy internal flow ('SIGNED') and Zoho flow ('CDA_COMPLETED', 'COMPLETED')
                    if cda_status_value not in ('SIGNED', 'CDA_COMPLETED', 'COMPLETED'):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Cannot complete CDA Execution: Signed/Completed CDA must be present when "
                                "CDA is required (expected status SIGNED or CDA_COMPLETED)"
                            ),
                        )
                    if not merged_step_data.get('signed_cda_document_id'):
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Cannot complete CDA Execution: Signed CDA document must be stored "
                                "in Site Documents (missing signed_cda_document_id). "
                                "For new CDA workflow, please use the Agreement module."
                            ),
                        )
                # If completed_via_agreement is True, skip signed_cda_document_id check
                # The Agreement module validation already passed above
            # If CDA is NOT required (False), require a comment and lock all subsequent steps
            if merged_step_data.get('cda_required') is False:
                cda_comment = merged_step_data.get('cda_comment', '').strip()
                if not cda_comment:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Cannot complete CDA Execution: A comment explaining why CDA is not required "
                            "is mandatory"
                        ),
                    )
                merged_step_data['workflow_locked'] = True
            # If CDA is NOT applicable, lock all subsequent steps (no comment required)
            elif merged_step_data.get('cda_required') == 'not_applicable':
                merged_step_data['workflow_locked'] = True
        
        elif step_enum == WorkflowStepName.FEASIBILITY:
            # Normalize possible frontend camelCase payload keys to snake_case.
            # This keeps backward compatibility across UI versions.
            if merged_step_data.get('response_received') is None and 'responseReceived' in merged_step_data:
                merged_step_data['response_received'] = merged_step_data.get('responseReceived')
            if merged_step_data.get('response_received_at') is None and 'responseReceivedAt' in merged_step_data:
                merged_step_data['response_received_at'] = merged_step_data.get('responseReceivedAt')
            if merged_step_data.get('onsite_visit_required') is None and 'onsiteVisitRequired' in merged_step_data:
                merged_step_data['onsite_visit_required'] = merged_step_data.get('onsiteVisitRequired')
            if merged_step_data.get('onsite_report_uploaded') is None and 'onsiteReportUploaded' in merged_step_data:
                merged_step_data['onsite_report_uploaded'] = merged_step_data.get('onsiteReportUploaded')

            # Check CDA dependency if required
            # CDA is study-specific, so use study_site_id
            if step_enum in STUDY_SPECIFIC_STEPS and study_site:
                cda_result = await db.execute(
                    select(SiteWorkflowStep).where(
                        SiteWorkflowStep.study_site_id == study_site.id,
                        SiteWorkflowStep.step_name == WorkflowStepName.CDA_EXECUTION
                    )
                )
            else:
                cda_result = await db.execute(
                    select(SiteWorkflowStep).where(
                        SiteWorkflowStep.site_id == site.id,
                        SiteWorkflowStep.step_name == WorkflowStepName.CDA_EXECUTION
                    )
                )
            cda_step = cda_result.scalar_one_or_none()
            if cda_step:
                cda_required_value = cda_step.step_data.get('cda_required')
                cda_required_truthy = (
                    cda_required_value is True
                    or str(cda_required_value).lower() in ("true", "1", "yes")
                )
                cda_status_value = str(cda_step.step_data.get('cda_status') or '').upper()
                # Accept both legacy and Zoho-based completed statuses.
                if cda_required_truthy and cda_status_value not in ('SIGNED', 'CDA_COMPLETED', 'COMPLETED'):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Cannot complete Feasibility: CDA is required and not yet signed/completed "
                            "(expected SIGNED or CDA_COMPLETED)"
                        ),
                    )
            # Must have questionnaire response - check step_data or verify responses exist
            response_received = merged_step_data.get('response_received')
            if not response_received:
                # Auto-check if feasibility responses exist for this study_site
                if study_site:
                    from app.models import FeasibilityRequest, FeasibilityResponse
                    response_check = await db.execute(
                        select(FeasibilityResponse)
                        .join(FeasibilityRequest, FeasibilityResponse.request_id == FeasibilityRequest.id)
                        .where(FeasibilityRequest.study_site_id == study_site.id)
                        .where(FeasibilityRequest.status == FeasibilityRequestStatus.COMPLETED.value)
                        .limit(1)
                    )
                    has_responses = response_check.scalar_one_or_none() is not None
                    if has_responses:
                        # Auto-set response_received if responses exist
                        merged_step_data['response_received'] = True
                        if not merged_step_data.get('response_received_at'):
                            merged_step_data['response_received_at'] = datetime.now(timezone.utc).isoformat()
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail="Cannot complete Feasibility: Questionnaire response must be received"
                        )
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot complete Feasibility: Questionnaire response must be received"
                    )
            # Must have all toggles resolved
            if merged_step_data.get('onsite_visit_required') is None:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot complete Feasibility: On-site visit requirement must be specified"
                )
            # If onsite visit required, report must be uploaded
            if merged_step_data.get('onsite_visit_required') is True:
                if not merged_step_data.get('onsite_report_uploaded'):
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot complete Feasibility: On-site visit report must be uploaded when required"
                    )
        
        elif step_enum == WorkflowStepName.SITE_SELECTION_OUTCOME:
            # Must have final decision
            if not merged_step_data.get('decision'):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot complete Site Selection Outcome: Final decision is required"
                )
    
    # Track if status was updated to COMPLETED
    status_updated_to_completed = False
    validated_status = None
    
    # Update step
    if update_data.status:
        # Validate that status is a valid StepStatus value, then store as enum
        try:
            validated_status = StepStatus(update_data.status)
            step.status = validated_status  # SQLEnum will convert enum to value for DB
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {update_data.status}")
        
        # Check if status is completed
        if validated_status == StepStatus.COMPLETED:
            status_updated_to_completed = True
            step.completed_at = datetime.now(timezone.utc)
            if current_user:
                step.completed_by = current_user.get("user_id") or current_user.get("email", "unknown")
        # Note: When changing from COMPLETED to IN_PROGRESS (reopening), we preserve completed_at/completed_by
        # for audit history. The status change itself is allowed - no validation needed for reopening.
        
        # TODO: Consider invalidating dependent steps when reopening earlier steps if business logic requires it.
        # For example, if Site Identification decision changes from "proceed" to "do_not_proceed", 
        # subsequent steps should be invalidated. However, this should only happen if the change
        # truly invalidates later steps - not for simple data updates.
    
    if update_data.step_data is not None:
        if step.step_data is None:
            step.step_data = {}
        # Merge the update data with existing step_data
        step.step_data = {**(step.step_data or {}), **update_data.step_data}
        step.updated_at = datetime.now(timezone.utc)

    # Bridge: when the Site Selection Outcome milestone is completed, derive the
    # site's headline status from the decision (selected -> active, not_selected
    # -> pending). Runs in THIS transaction so the status change is committed
    # atomically with the step. This is the only path that sets Site.status —
    # the create/edit form no longer lets users pick it by hand.
    step_is_completed = (
        validated_status == StepStatus.COMPLETED
        or step.status == StepStatus.COMPLETED
    )
    if (
        step_enum == WorkflowStepName.SITE_SELECTION_OUTCOME
        and step_is_completed
        and step.study_site_id
    ):
        try:
            await sync_site_status_from_selection(
                db,
                step.study_site_id,
                (step.step_data or {}).get("decision"),
            )
        except Exception:
            logger.exception(
                "Failed to sync site status from selection outcome for step %s",
                step.id,
            )

    await db.commit()
    await db.refresh(step)

    # Kafka: when Site Selection Outcome is completed, publish SITE_SELECTED /
    # SITE_REJECTED to the Data Platform based on the recorded decision.
    # Best-effort and self-guarded — never breaks the already-committed step.
    if (
        step_enum == WorkflowStepName.SITE_SELECTION_OUTCOME
        and (status_updated_to_completed or step.status == StepStatus.COMPLETED)
        and step.study_site_id
    ):
        try:
            from app.integrations.milestones_kafka import publish_site_milestone, SiteMilestone

            decision = str((step.step_data or {}).get("decision") or "").lower()
            milestone = None
            if decision == "selected":
                milestone = SiteMilestone.SITE_SELECTED
            elif decision == "not_selected":
                milestone = SiteMilestone.SITE_REJECTED

            if milestone is not None:
                ss_row = (
                    await db.execute(
                        select(StudySite).where(StudySite.id == step.study_site_id)
                    )
                ).scalar_one_or_none()
                if ss_row and ss_row.site_id:
                    await publish_site_milestone(milestone, site_id=str(ss_row.site_id))
        except Exception:
            logger.exception(
                "Failed to publish site-selection milestone for step %s", step.id
            )

    # Append to Public Notice Board on EVERY workflow step completion, not
    # just CDA. The previous block hard-coded `is_cda_step` so the other
    # three Under-Consideration steps (Site Identification, Feasibility,
    # Site Selection Outcome) never posted anything. It also passed
    # `study.study_id` (friendly external code) as the notice's study_id —
    # but the frontend filters the inbox by `str(study.id)` (UUID), so
    # even the CDA notice was landing on a phantom board the user never
    # reads from. Both fixes inline below: cover all 4 steps + delegate to
    # `post_site_event_notice`, which already enforces the correct
    # (site.site_id, str(study.id)) convention via the shared helper.
    was_completed = status_updated_to_completed or step.status == StepStatus.COMPLETED
    step_name_value = step.step_name.value if hasattr(step.step_name, 'value') else str(step.step_name)

    if was_completed:
        try:
            from app.utils.system_notices import post_site_event_notice

            # Resolve the specific study+site attached to this step. Study-
            # specific steps (Site Identification, CDA, Feasibility, Site
            # Selection Outcome) have step.site_id = NULL and instead carry
            # study_site_id → StudySite(site_id, study_id). The earlier guard
            # `if step.site_id` silently skipped all four of those, so the
            # board stayed empty even on completion. Resolve via study_site
            # when step.site_id isn't directly populated.
            study_uuid_str: Optional[str] = None
            resolved_site_id = step.site_id
            if step.study_site_id:
                study_site_result = await db.execute(
                    select(StudySite).where(StudySite.id == step.study_site_id)
                )
                study_site_row = study_site_result.scalar_one_or_none()
                if study_site_row:
                    if study_site_row.study_id:
                        study_uuid_str = str(study_site_row.study_id)
                    if resolved_site_id is None and study_site_row.site_id:
                        resolved_site_id = study_site_row.site_id

            if resolved_site_id is None:
                logger.warning(
                    "workflow notice skipped: could not resolve site_id for step %s",
                    step.id,
                )
                raise RuntimeError("no site_id resolved")

            sd = step.step_data or {}

            # Step-specific message — surfaces the actual decision the user
            # made so the board entry is informative, not just "Step X done".
            def _label(v: Any) -> str:
                if v is None:
                    return "—"
                return str(v).replace("_", " ").strip().title() or "—"

            if step_name_value == WorkflowStepName.SITE_IDENTIFICATION.value:
                msg = f"Step 1: Site Identification completed — Decision: {_label(sd.get('decision'))}"
                event_type = "workflow_site_identification_completed"
            elif step_name_value == WorkflowStepName.CDA_EXECUTION.value:
                req = sd.get('cda_required') or sd.get('cda_status')
                msg = f"Step 2: CDA Execution completed — CDA Required: {_label(req)}"
                event_type = "workflow_cda_execution_completed"
            elif step_name_value == WorkflowStepName.FEASIBILITY.value:
                visit = sd.get('onsite_visit') or sd.get('on_site_visit')
                resp = sd.get('feasibility_outcome') or sd.get('response_received')
                bits = []
                if visit is not None:
                    bits.append(f"On-site Visit: {_label(visit)}")
                if resp is not None:
                    bits.append(f"Outcome: {_label(resp)}")
                tail = " — " + " · ".join(bits) if bits else ""
                msg = f"Step 3: Feasibility completed{tail}"
                event_type = "workflow_feasibility_completed"
            elif step_name_value == WorkflowStepName.SITE_SELECTION_OUTCOME.value:
                outcome = sd.get('decision') or sd.get('outcome') or sd.get('selection_outcome')
                msg = f"Step 4: Final Site Selection completed — Decision: {_label(outcome)}"
                event_type = "workflow_site_selection_completed"
            else:
                # Unknown step name — still post a generic notice so future
                # additions to WorkflowStepName show up without code changes.
                msg = f"Workflow step '{step_name_value}' marked as completed."
                event_type = "workflow_step_completed"

            await post_site_event_notice(
                db,
                site_ref=resolved_site_id,
                study_ref=study_uuid_str,
                event_type=event_type,
                message=msg,
                created_by=(current_user or {}).get("user_id"),
                metadata={
                    "step_name": step_name_value,
                    "step_data": sd,
                    "completed_at": step.completed_at.isoformat() if step.completed_at else None,
                    "completed_by": step.completed_by,
                    "site_id": str(resolved_site_id),
                    "study_site_id": str(step.study_site_id) if step.study_site_id else None,
                },
            )
            logger.info(
                "workflow notice posted: step=%s site=%s study=%s",
                step_name_value, resolved_site_id, study_uuid_str,
            )
        except Exception:
            logger.exception("Failed to post workflow-step completion notice")
    
    return {
        "step_name": step.step_name.value if hasattr(step.step_name, 'value') else str(step.step_name),
        "status": step.status.value if hasattr(step.status, 'value') else str(step.status),
        "step_data": step.step_data or {},
        "completed_at": step.completed_at.isoformat() if step.completed_at else None,
        "completed_by": step.completed_by,
        "updated_at": step.updated_at,
    }


# ---------------------------------------------------------------------------
# Workflow Reset Endpoint (for testing)
# ---------------------------------------------------------------------------


@router.delete("/sites/{site_id}/workflow/steps")
async def reset_workflow_steps(
    site_id: str,
    study_id: Optional[str] = Query(
        None,
        description=(
            "Study identifier (UUID or external study_id string). "
            "If provided, only resets study-specific workflow steps for this study+site combination. "
            "If not provided, resets all workflow steps for the site."
        ),
    ),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Reset workflow steps for a site (for testing purposes).
    If study_id is provided, only resets study-specific steps for that study+site combination.
    Otherwise, resets all workflow steps for the site.
    """
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
    
    # Delete workflow steps
    from sqlalchemy import delete
    if study_id:
        # Resolve study_id
        try:
            resolved_study_id = UUID(str(study_id))
            study_result = await db.execute(select(Study).where(Study.id == resolved_study_id))
            study = study_result.scalar_one_or_none()
            if not study:
                raise HTTPException(status_code=404, detail="Study not found")
        except (ValueError, TypeError):
            study_result = await db.execute(select(Study).where(Study.study_id == study_id))
            study = study_result.scalar_one_or_none()
            if not study:
                raise HTTPException(status_code=404, detail="Study not found")
            resolved_study_id = study.id
        
        # Get study_site mapping
        study_site = await get_or_create_study_site(db, resolved_study_id, site.id)
        
        # Delete only study-specific steps for this study+site
        # Build conditions for each study-specific step
        step_conditions = [
            SiteWorkflowStep.step_name == step_enum
            for step_enum in STUDY_SPECIFIC_STEPS
        ]
        await db.execute(
            delete(SiteWorkflowStep).where(
                SiteWorkflowStep.study_site_id == study_site.id,
                or_(*step_conditions)
            )
        )
        message = f"Study-specific workflow steps reset for study {study.study_id} and site {site.site_id or site.id}"
    else:
        # Delete all workflow steps for this site
        await db.execute(delete(SiteWorkflowStep).where(SiteWorkflowStep.site_id == site.id))
        message = f"Workflow steps reset for site {site.site_id or site.id}"
    
    await db.commit()
    
    return {"message": message, "site_id": str(site.id)}


# ---------------------------------------------------------------------------
# Site Documents Endpoints
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# Feasibility Request Endpoints
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# CDA Signing Endpoints (Extending Existing CDA Functionality)
# ---------------------------------------------------------------------------


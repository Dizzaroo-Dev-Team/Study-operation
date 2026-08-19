"""REST API: feasibility request lifecycle (create -> public form -> submit + lookup + responses + reset)."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.auth import get_current_user_optional
from app.config import settings
from app.db import get_db
from app.models import (
    FeasibilityAttachment,
    FeasibilityRequest,
    FeasibilityRequestStatus,
    FeasibilityResponse,
    ProjectFeasibilityCustomQuestion,
    Site,
    SiteWorkflowStep,
    StepStatus,
    Study,
    StudySite,
    WorkflowStepName,
)
from app.modules.clinical_workflow.services.study_site_service import get_or_create_study_site

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Clinical Workflow"])


@router.post("/feasibility-requests", response_model=schemas.FeasibilityRequestResponse)
async def create_feasibility_request(
    request_data: schemas.FeasibilityRequestCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a feasibility request and send email with form link.
    Generates a secure token and persists the request before sending email.

    If email is not provided in request_data, uses FEASIBILITY_DEFAULT_EMAIL from environment.
    """
    from app.integrations.smtp_service import smtp_service

    recipient_email = request_data.email
    if not recipient_email or not recipient_email.strip():
        recipient_email = settings.feasibility_default_email or "labeshg@dizzaroo.com"

    study_site_result = await db.execute(
        select(StudySite).where(StudySite.id == request_data.study_site_id)
    )
    study_site = study_site_result.scalar_one_or_none()

    if not study_site:
        raise HTTPException(status_code=404, detail="Study site not found")

    # Check if there's already a completed request for this study_site
    existing_result = await db.execute(
        select(FeasibilityRequest)
        .where(FeasibilityRequest.study_site_id == request_data.study_site_id)
        .where(FeasibilityRequest.status == FeasibilityRequestStatus.COMPLETED.value)
    )
    existing = existing_result.scalar_one_or_none()

    if existing:
        raise HTTPException(
            status_code=400,
            detail="A feasibility request has already been completed for this study site",
        )

    token = secrets.token_urlsafe(32)

    expires_at = None
    if request_data.expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=request_data.expires_in_days)

    feasibility_request = FeasibilityRequest(
        study_site_id=request_data.study_site_id,
        email=recipient_email.strip(),
        token=token,
        status=FeasibilityRequestStatus.SENT.value,
        expires_at=expires_at,
    )

    db.add(feasibility_request)
    await db.flush()
    await db.refresh(feasibility_request)

    study_result = await db.execute(select(Study).where(Study.id == study_site.study_id))
    study = study_result.scalar_one_or_none()

    site_result = await db.execute(select(Site).where(Site.id == study_site.site_id))
    site = site_result.scalar_one_or_none()

    study_name = study.name if study else "Unknown Study"
    site_name = site.name if site else "Unknown Site"

    # Build form URL from the dedicated FRONTEND_BASE_URL setting — the same
    # source the rest of the app uses for outbound links (e.g. agreements).
    # Do NOT derive this from CORS_ORIGINS: that list legitimately contains
    # localhost entries for local dev, and picking origins[0] put a localhost
    # URL into production emails. Strip any trailing slash to avoid `//form`.
    frontend_url = (getattr(settings, "frontend_base_url", None) or "http://localhost:5173").rstrip("/")

    form_url = f"{frontend_url}/feasibility/form?token={token}"

    # Check if Protocol Synopsis attachment exists
    attachment_result = await db.execute(
        select(FeasibilityAttachment).where(FeasibilityAttachment.study_site_id == request_data.study_site_id)
    )
    attachment = attachment_result.scalar_one_or_none()

    email_subject = f"Feasibility Form Request - {study_name}"
    protocol_synopsis_note = ""
    if attachment:
        protocol_synopsis_note = "\n\nA Protocol Synopsis document is attached to this email and is also available for download within the feasibility form."

    email_body = f"""
Dear Site Contact,

You have been requested to complete a feasibility form for the following study:

Study: {study_name}
Site: {site_name}

Please click the link below to access the feasibility form:

{form_url}

This link will expire on {expires_at.strftime('%Y-%m-%d') if expires_at else 'never'}.{protocol_synopsis_note}

If you have any questions, please contact the study team.

Best regards,
CRM System
"""

    email_attachments = []
    if attachment:
        file_path = Path(attachment.file_path)
        if file_path.exists():
            email_attachments.append(str(file_path))

    from_email = settings.smtp_user or "noreply@crm.com"
    # Behavior change: feasibility request notification is now enqueued via
    # Celery. The previous 500-and-rollback on SMTP failure no longer fires
    # — once we have committed the DB state, the email retries asynchronously.
    # If you need to guarantee transactional email-or-fail semantics, move
    # the send to a Celery task that's chained off the commit and exposes
    # delivery status via WebSocket / status endpoint.
    from app.integrations.smtp_service import enqueue_email
    enqueue_email(
        to=recipient_email.strip(),
        subject=email_subject,
        body=email_body,
        from_email=from_email,
        html=False,
        attachments=email_attachments if email_attachments else None,
    )

    await db.commit()

    # Kafka: publish FEASIBILITY_QUESTIONNAIRE_SENT to the Data Platform.
    # Best-effort and self-guarded (no-op when the producer is disabled) — a
    # publish failure must never surface as a 500 after the DB is committed.
    try:
        from app.integrations.milestones_kafka import publish_site_milestone, SiteMilestone

        await publish_site_milestone(
            SiteMilestone.FEASIBILITY_QUESTIONNAIRE_SENT,
            site_id=str(study_site.site_id),
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "create_feasibility_request: milestone Kafka hook failed for study_site=%s",
            request_data.study_site_id,
        )

    # Public Notice Board entry for the request being sent out. Best-effort;
    # the request itself is already committed.
    try:
        from app.utils.system_notices import post_site_event_notice

        await post_site_event_notice(
            db,
            site_ref=study_site.site_id,
            study_ref=study_site.study_id,
            event_type="feasibility_request_sent",
            message=(
                f"Feasibility form sent to {recipient_email.strip()} "
                f"for study '{study_name}' / site '{site_name}'."
            ),
            metadata={
                "feasibility_request_id": str(feasibility_request.id),
                "study_site_id": str(study_site.id),
                "recipient_email": recipient_email.strip(),
            },
        )
    except Exception:
        logger.exception(
            "create_feasibility_request: notice-board hook failed for request %s",
            feasibility_request.id,
        )

    return feasibility_request


@router.get("/feasibility/form", response_model=schemas.FeasibilityFormResponse)
async def get_feasibility_form(
    token: str = Query(..., description="Secure token for accessing the form"),
    db: AsyncSession = Depends(get_db),
):
    """Public endpoint to load feasibility form questions using token. No authentication required."""
    request_result = await db.execute(
        select(FeasibilityRequest).where(FeasibilityRequest.token == token)
    )
    request = request_result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="Invalid or expired token")

    if request.status == FeasibilityRequestStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="This feasibility form has already been submitted")

    if request.expires_at and request.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This form link has expired")

    study_site_result = await db.execute(
        select(StudySite).where(StudySite.id == request.study_site_id)
    )
    study_site = study_site_result.scalar_one_or_none()

    if not study_site:
        raise HTTPException(status_code=404, detail="Study site not found")

    study_result = await db.execute(select(Study).where(Study.id == study_site.study_id))
    study = study_result.scalar_one_or_none()

    site_result = await db.execute(select(Site).where(Site.id == study_site.site_id))
    site = site_result.scalar_one_or_none()

    study_name = study.name if study else "Unknown Study"
    site_name = site.name if site else "Unknown Site"

    all_questions: List[schemas.FeasibilityQuestion] = []

    # 1. Fetch external questions from MongoDB (read-only)
    from app.modules.feasibility.services.feasibility_service import get_feasibility_questions_for_form

    study, external_questions = await get_feasibility_questions_for_form(db, str(study.id))

    if not study:
        raise HTTPException(status_code=404, detail="Study/Project not found")

    all_questions.extend(external_questions)

    # 2. Fetch custom questions from CRM DB
    custom_questions_result = await db.execute(
        select(ProjectFeasibilityCustomQuestion)
        .where(ProjectFeasibilityCustomQuestion.study_id == study.id)
        .where(ProjectFeasibilityCustomQuestion.workflow_step == "feasibility")
        .order_by(ProjectFeasibilityCustomQuestion.display_order, ProjectFeasibilityCustomQuestion.created_at)
    )
    custom_questions = custom_questions_result.scalars().all()

    for cq in custom_questions:
        all_questions.append(schemas.FeasibilityQuestion(
            text=cq.question_text,
            section=cq.section,
            type=cq.expected_response_type or "text",
            source="custom",
            criterion_reference=None,
            display_order=cq.display_order,
            id=cq.id,
        ))

    # Sort by display_order (external first when tied)
    all_questions.sort(key=lambda q: (q.display_order or 0, 0 if q.source == "external" else 1))

    form_questions = [
        schemas.FeasibilityFormQuestion(
            text=q.text,
            section=q.section,
            type=q.type,
            id=q.id,
            display_order=q.display_order,
        )
        for q in all_questions
    ]

    attachment_result = await db.execute(
        select(FeasibilityAttachment).where(FeasibilityAttachment.study_site_id == request.study_site_id)
    )
    attachment = attachment_result.scalar_one_or_none()

    protocol_synopsis = None
    if attachment:
        protocol_synopsis = schemas.FeasibilityAttachmentResponse(
            id=attachment.id,
            study_site_id=attachment.study_site_id,
            file_name=attachment.file_name,
            file_path=attachment.file_path,
            content_type=attachment.content_type,
            size=attachment.size,
            uploaded_by=attachment.uploaded_by,
            uploaded_at=attachment.uploaded_at,
        )

    return schemas.FeasibilityFormResponse(
        request_id=request.id,
        study_name=study_name,
        site_name=site_name,
        questions=form_questions,
        protocol_synopsis=protocol_synopsis,
    )


@router.post("/feasibility/submit")
async def submit_feasibility_form(
    submit_data: schemas.FeasibilityFormSubmit,
    db: AsyncSession = Depends(get_db),
):
    """Submit feasibility form responses. Validates token, stores answers, and marks request as completed."""
    request_result = await db.execute(
        select(FeasibilityRequest).where(FeasibilityRequest.token == submit_data.token)
    )
    request = request_result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="Invalid or expired token")

    if request.status == FeasibilityRequestStatus.COMPLETED.value:
        raise HTTPException(status_code=400, detail="This feasibility form has already been submitted")

    if request.expires_at and request.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="This form link has expired")

    if not submit_data.answers:
        raise HTTPException(status_code=400, detail="No answers provided")

    responses = []
    for answer_data in submit_data.answers:
        response = FeasibilityResponse(
            request_id=request.id,
            question_text=answer_data.question_text,
            question_id=answer_data.question_id,
            answer=answer_data.answer,
            section=answer_data.section,
        )
        db.add(response)
        responses.append(response)

    request.status = FeasibilityRequestStatus.COMPLETED.value
    request.updated_at = datetime.now(timezone.utc)

    await db.flush()

    # Update feasibility workflow step status (best-effort; failure doesn't block submit)
    try:
        study_site_result = await db.execute(
            select(StudySite).where(StudySite.id == request.study_site_id)
        )
        study_site = study_site_result.scalar_one_or_none()

        if study_site:
            workflow_step_result = await db.execute(
                select(SiteWorkflowStep)
                .where(SiteWorkflowStep.study_site_id == study_site.id)
                .where(SiteWorkflowStep.step_name == WorkflowStepName.FEASIBILITY)
            )
            workflow_step = workflow_step_result.scalar_one_or_none()

            if workflow_step:
                step_data = workflow_step.step_data or {}
                step_data["response_received"] = True
                step_data["response_received_at"] = datetime.now(timezone.utc).isoformat()
                workflow_step.step_data = step_data
                workflow_step.updated_at = datetime.now(timezone.utc)
    except Exception as e:
        logger.warning(f"Failed to update workflow step: {e}")

    await db.commit()

    # Public Notice Board entry for the submission. We re-read study_site if
    # the earlier best-effort block didn't run (e.g. lookup failed), so the
    # board still gets the announcement.
    try:
        from app.utils.system_notices import post_site_event_notice

        if 'study_site' not in locals() or study_site is None:
            study_site_lookup = await db.execute(
                select(StudySite).where(StudySite.id == request.study_site_id)
            )
            study_site = study_site_lookup.scalar_one_or_none()

        if study_site is not None:
            await post_site_event_notice(
                db,
                site_ref=study_site.site_id,
                study_ref=study_site.study_id,
                event_type="feasibility_submitted",
                message=(
                    f"Feasibility form submitted ({len(responses)} responses) "
                    f"by {request.email}."
                ),
                metadata={
                    "feasibility_request_id": str(request.id),
                    "study_site_id": str(study_site.id),
                    "responses_count": len(responses),
                    "submitted_by_email": request.email,
                },
            )
    except Exception:
        logger.exception(
            "submit_feasibility_form: notice-board hook failed for request %s", request.id
        )

    return {
        "message": "Feasibility form submitted successfully",
        "request_id": str(request.id),
        "responses_count": len(responses),
    }


@router.get("/study-sites/lookup")
async def get_study_site_id(
    site_id: str = Query(..., description="Site ID (UUID or external site_id string)"),
    study_id: str = Query(..., description="Study ID (UUID or external study_id string)"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Get or create study_site_id for a given site_id and study_id combination.
    Returns the study_site_id UUID.
    """
    try:
        site_uuid = UUID(str(site_id))
        site_result = await db.execute(select(Site).where(Site.id == site_uuid))
        site = site_result.scalar_one_or_none()
    except (ValueError, TypeError):
        site_result = await db.execute(select(Site).where(Site.site_id == site_id))
        site = site_result.scalar_one_or_none()

    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    try:
        study_uuid = UUID(str(study_id))
        study_result = await db.execute(select(Study).where(Study.id == study_uuid))
        study = study_result.scalar_one_or_none()
    except (ValueError, TypeError):
        study_result = await db.execute(select(Study).where(Study.study_id == study_id))
        study = study_result.scalar_one_or_none()

    if not study:
        raise HTTPException(status_code=404, detail="Study not found")

    study_site = await get_or_create_study_site(db, study.id, site.id)

    return {"study_site_id": str(study_site.id)}


@router.get("/feasibility-responses/{study_site_id}", response_model=List[schemas.FeasibilityResponsesDisplay])
async def get_feasibility_responses(
    study_site_id: UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Get all feasibility responses for a study_site. Used to display responses in the CRM app."""
    requests_result = await db.execute(
        select(FeasibilityRequest)
        .where(FeasibilityRequest.study_site_id == study_site_id)
        .order_by(FeasibilityRequest.created_at.desc())
    )
    requests = requests_result.scalars().all()

    result = []
    for req in requests:
        responses_result = await db.execute(
            select(FeasibilityResponse)
            .where(FeasibilityResponse.request_id == req.id)
            .order_by(FeasibilityResponse.created_at)
        )
        responses = responses_result.scalars().all()

        # Only include requests that have responses (completed requests)
        if not responses or len(responses) == 0:
            continue

        # Find completed_at from the first response (they're all created at the same time)
        completed_at = responses[0].created_at if responses else None

        result.append(schemas.FeasibilityResponsesDisplay(
            study_site_id=req.study_site_id,
            request_id=req.id,
            email=req.email,
            status=req.status,
            created_at=req.created_at,
            updated_at=req.updated_at,
            completed_at=completed_at,
            responses=[
                schemas.FeasibilityResponseDisplay(
                    id=resp.id,
                    question_text=resp.question_text,
                    answer=resp.answer,
                    section=resp.section,
                    created_at=resp.created_at,
                )
                for resp in responses
            ],
        ))

    return result


@router.post("/feasibility/reset-all")
async def reset_all_feasibility_requests(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Reset all feasibility requests and responses for testing purposes."""
    try:
        # Delete all feasibility responses first (FK constraint)
        await db.execute(delete(FeasibilityResponse))

        # Delete all feasibility requests
        await db.execute(delete(FeasibilityRequest))

        # Reset feasibility workflow steps for all study sites
        await db.execute(
            update(SiteWorkflowStep)
            .where(SiteWorkflowStep.step_name == WorkflowStepName.FEASIBILITY.value)
            .values(
                status=StepStatus.NOT_STARTED.value,
                step_data={},
                completed_at=None,
                completed_by=None,
            )
        )

        await db.commit()

        return {
            "message": "All feasibility requests and responses have been reset successfully",
            "reset_items": {
                "feasibility_requests": "deleted",
                "feasibility_responses": "deleted",
                "workflow_steps": "reset to NOT_STARTED",
            },
        }
    except Exception as e:
        await db.rollback()
        logger.error(f"Error resetting feasibility data: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reset feasibility data: {str(e)}")

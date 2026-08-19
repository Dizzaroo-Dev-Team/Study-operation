from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header, Query, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, delete, update, text
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


router = APIRouter(tags=["Operations"])
logger = logging.getLogger(__name__)

@router.get("/health")
async def health():
    return {"status": "ok"}


def _task_doc_to_response(task: dict) -> schemas.TaskResponse:
    """Map a Mongo task doc to TaskResponse — single source of truth so new
    fields (requestedBy/assignedTo/etc.) are surfaced everywhere."""
    def _parse_dt(value):
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value)
        except Exception:
            return None

    due_date = _parse_dt(task.get("dueDate"))
    closed_date = _parse_dt(task.get("closedDate"))
    created_at = _parse_dt(task.get("createdAt")) or datetime.now(timezone.utc)
    updated_at = _parse_dt(task.get("updatedAt")) or created_at

    return schemas.TaskResponse(
        id=task.get("id"),
        title=task.get("title"),
        description=task.get("description"),
        status=task.get("status", "open"),
        assigneeId=task.get("assigneeId"),
        assigneeName=task.get("assigneeName"),
        requestedBy=task.get("requestedBy"),
        assignedTo=task.get("assignedTo"),
        sponsorId=task.get("sponsorId") or (task.get("links") or {}).get("sponsorId"),
        sponsorName=task.get("sponsorName"),
        role=task.get("role"),
        taskMode=task.get("taskMode"),
        dueDate=due_date,
        closedDate=closed_date,
        statusUpdate=task.get("statusUpdate") or task.get("comment"),
        createdAt=created_at,
        updatedAt=updated_at,
        createdByUserId=task.get("createdByUserId"),
        links=schemas.TaskLinks(**task["links"]) if task.get("links") else None,
        siteId=task.get("siteId"),
        monitoringVisitId=task.get("monitoringVisitId"),
        monitoringReportId=task.get("monitoringReportId"),
        sourceConversationId=task.get("sourceConversationId"),
    )


@router.post("/tasks", response_model=schemas.TaskResponse)
async def create_task(
    task: schemas.TaskCreate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Create a new task. Requires an authenticated user."""
    try:
        from app.modules.operations.repositories import TaskRepository

        # If the caller did not supply a title (new Tasks page does not), fall
        # back to the first chunk of the description so legacy listings still
        # show something sensible.
        resolved_title = task.title
        if not resolved_title and task.description:
            resolved_title = task.description.strip().splitlines()[0][:120]

        # Resolve assignee: if caller passed an assigneeId, look up the user so
        # the stored assignee name is the canonical one (cannot just be free text).
        resolved_assignee_id = task.assigneeId
        resolved_assignee_name = task.assigneeName or task.assignedTo
        resolved_assigned_to = task.assignedTo
        if resolved_assignee_id:
            assignee_user = await crud.get_user(db, resolved_assignee_id)
            if not assignee_user:
                raise HTTPException(status_code=400, detail="Assignee is not a known user")
            canonical_name = (
                getattr(assignee_user, "name", None)
                or getattr(assignee_user, "email", None)
                or resolved_assignee_id
            )
            resolved_assignee_name = canonical_name
            resolved_assigned_to = canonical_name

        task_data = {
            "id": str(uuid.uuid4()),
            "title": resolved_title,
            "description": task.description,
            "status": task.status,
            "assigneeId": resolved_assignee_id,
            "assigneeName": resolved_assignee_name,
            "requestedBy": task.requestedBy,
            "assignedTo": resolved_assigned_to,
            "taskMode": task.taskMode,
            "dueDate": task.dueDate.isoformat() if task.dueDate else None,
            "statusUpdate": (task.statusUpdate or "").strip() or None,
            "createdByUserId": task.createdByUserId or current_user.get("user_id"),
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "updatedAt": datetime.now(timezone.utc).isoformat(),
        }
        if task.status in ("done", "cancelled"):
            task_data["closedDate"] = (
                task.closedDate.isoformat()
                if task.closedDate
                else datetime.now(timezone.utc).date().isoformat()
            )
        elif task.closedDate:
            task_data["closedDate"] = task.closedDate.isoformat()

        # Handle links
        if task.links:
            task_data["links"] = {
                "siteId": task.links.siteId,
                "sponsorId": task.links.sponsorId,
                "monitoringVisitId": task.links.monitoringVisitId,
                "monitoringReportId": task.links.monitoringReportId,
                "conversationId": task.links.conversationId,
                "messageId": task.links.messageId,
            }

        # Legacy fields for backward compatibility
        if task.siteId:
            task_data["siteId"] = task.siteId
        if task.sponsorId:
            task_data["sponsorId"] = task.sponsorId
        if task.sponsorName:
            task_data["sponsorName"] = task.sponsorName
        if task.role:
            task_data["role"] = task.role
        if task.monitoringVisitId:
            task_data["monitoringVisitId"] = task.monitoringVisitId
        if task.monitoringReportId:
            task_data["monitoringReportId"] = task.monitoringReportId
        if task.sourceConversationId:
            task_data["sourceConversationId"] = task.sourceConversationId

        created_task = await TaskRepository.create(task_data)

        # Audit the creation. Tasks previously had no audit row; a mutating action
        # must be recorded (21 CFR Part 11). Provenance (e.g. agentic assistant)
        # is auto-merged into details by the audit path when present. Failures are
        # logged, not raised, to match the message-created audit convention.
        try:
            await crud.create_audit_log(
                db,
                user=str(current_user.get("user_id")) if current_user else None,
                action="task_created",
                target_type="task",
                target_id=task_data["id"],
                details={"title": resolved_title, "status": task.status},
            )
        except Exception:
            logger.exception("create_task: audit log failed for task %s", task_data["id"])

        # Announce on the Public Notice Board for the linked site (fanning out
        # to every (study, site) board the site is on). Tasks always belong
        # to a site in practice, but we no-op cleanly if siteId is blank.
        site_ref = (
            (task.links.siteId if task.links else None)
            or task.siteId
        )
        if site_ref:
            try:
                from app.utils.system_notices import post_site_event_notice

                actor = (
                    resolved_assignee_name
                    or task.requestedBy
                    or current_user.get("name")
                    or current_user.get("email")
                    or current_user.get("user_id")
                    or "a user"
                )
                msg = f"Task '{resolved_title or 'untitled'}' was created by {actor}"
                if task.dueDate:
                    msg += f" (due {task.dueDate.isoformat()})"

                await post_site_event_notice(
                    db,
                    site_ref=site_ref,
                    study_ref=None,
                    event_type="task_created",
                    message=msg,
                    metadata={
                        "task_id": task_data["id"],
                        "title": resolved_title,
                        "status": task.status,
                        "assignee_id": resolved_assignee_id,
                        "assignee_name": resolved_assignee_name,
                    },
                )
            except Exception:
                logger.exception("create_task: notice-board hook failed for task %s", task_data["id"])

        return _task_doc_to_response(created_task)
    except Exception as e:
        print(f"Error creating task: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to create task: {str(e)}")


@router.get("/tasks", response_model=List[schemas.TaskResponse])
async def list_tasks(
    siteId: Optional[str] = Query(None),
    monitoringVisitId: Optional[str] = Query(None),
    conversationId: Optional[str] = Query(None),
    sponsorId: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """List tasks with optional filters."""
    try:
        from app.modules.operations.repositories import TaskRepository
        
        # Build filter
        filters = {}
        if siteId:
            filters["siteId"] = siteId
        if monitoringVisitId:
            filters["monitoringVisitId"] = monitoringVisitId
        if conversationId:
            filters["links.conversationId"] = conversationId
        if sponsorId:
            filters["sponsorId"] = sponsorId
        if role:
            filters["role"] = role
        if status:
            filters["status"] = status
        
        tasks = await TaskRepository.list(limit=limit, offset=offset, **filters)
        from app.modules.operations.task_display import rewrite_tasks_for_display

        display_tasks = await rewrite_tasks_for_display(db, tasks)
        return [_task_doc_to_response(t) for t in display_tasks]
    except Exception as e:
        print(f"Error listing tasks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to list tasks: {str(e)}")


@router.get("/tasks/{task_id}", response_model=schemas.TaskResponse)
async def get_task(
    task_id: str,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Get a single task by ID."""
    try:
        from app.modules.operations.repositories import TaskRepository
        
        task = await TaskRepository.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        from app.modules.operations.task_display import rewrite_tasks_for_display

        display_tasks = await rewrite_tasks_for_display(db, [task])
        return _task_doc_to_response(display_tasks[0])
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting task: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to get task: {str(e)}")


@router.put("/tasks/{task_id}", response_model=schemas.TaskResponse)
async def update_task(
    task_id: str,
    task_update: schemas.TaskUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a task. Requires an authenticated user."""
    try:
        from app.modules.operations.repositories import TaskRepository

        # Get existing task
        task = await TaskRepository.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        # If a new assignee is being set, verify they are a real user and use
        # their canonical name so the display value is trusted, not free-text.
        if task_update.assigneeId is not None and task_update.assigneeId:
            assignee_user = await crud.get_user(db, task_update.assigneeId)
            if not assignee_user:
                raise HTTPException(status_code=400, detail="Assignee is not a known user")
            canonical_name = (
                getattr(assignee_user, "name", None)
                or getattr(assignee_user, "email", None)
                or task_update.assigneeId
            )
            task_update.assigneeName = canonical_name
            task_update.assignedTo = canonical_name

        # Build update dict
        updates = {}
        if task_update.title is not None:
            updates["title"] = task_update.title
        if task_update.description is not None:
            updates["description"] = task_update.description
        if task_update.status is not None:
            updates["status"] = task_update.status
            old_status = (task.get("status") or "").strip()
            if (
                task_update.status in ("done", "cancelled")
                and task_update.status != old_status
            ):
                updates["closedDate"] = datetime.now(timezone.utc).date().isoformat()
        if task_update.assigneeId is not None:
            updates["assigneeId"] = task_update.assigneeId
        if task_update.assigneeName is not None:
            updates["assigneeName"] = task_update.assigneeName
        if task_update.requestedBy is not None:
            updates["requestedBy"] = task_update.requestedBy
        if task_update.assignedTo is not None:
            updates["assignedTo"] = task_update.assignedTo
        if task_update.sponsorId is not None:
            updates["sponsorId"] = task_update.sponsorId
        if task_update.sponsorName is not None:
            updates["sponsorName"] = task_update.sponsorName
        if task_update.role is not None:
            updates["role"] = task_update.role
        if task_update.taskMode is not None:
            updates["taskMode"] = task_update.taskMode
        if task_update.dueDate is not None:
            updates["dueDate"] = task_update.dueDate.isoformat()
        if task_update.closedDate is not None:
            updates["closedDate"] = task_update.closedDate.isoformat()
        if task_update.statusUpdate is not None:
            updates["statusUpdate"] = task_update.statusUpdate.strip()
        if task_update.links is not None:
            updates["links"] = {
                "siteId": task_update.links.siteId,
                "sponsorId": task_update.links.sponsorId,
                "monitoringVisitId": task_update.links.monitoringVisitId,
                "monitoringReportId": task_update.links.monitoringReportId,
                "conversationId": task_update.links.conversationId,
                "messageId": task_update.links.messageId,
            }

        updates["updatedAt"] = datetime.now(timezone.utc).isoformat()

        updated_task = await TaskRepository.update(task_id, updates)
        from app.modules.operations.task_display import rewrite_tasks_for_display

        display_tasks = await rewrite_tasks_for_display(db, [updated_task])
        return _task_doc_to_response(display_tasks[0])
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating task: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to update task: {str(e)}")


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a task. Requires an authenticated user."""
    try:
        from app.modules.operations.repositories import TaskRepository
        
        task = await TaskRepository.get_by_id(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        await TaskRepository.delete(task_id)
        return {"status": "deleted", "task_id": task_id}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting task: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to delete task: {str(e)}")


# ---------------------------------------------------------------------------
# Monitoring & Logistics Endpoints (Stub endpoints for Site Status)
# ---------------------------------------------------------------------------

@router.get("/monitoring/visits")
async def get_monitoring_visits(
    study_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Site Status / Control Tower — cross-study monitoring visit list (camelCase)."""
    from app.modules.monitoring.aggregator import _ensure_monitor_tables

    await _ensure_monitor_tables(db)

    filters = ["LOWER(COALESCE(v.status, '')) <> 'archived'"]
    params: dict = {}
    if study_id:
        filters.append("(v.study_id = :study_id OR CAST(v.study_id AS TEXT) = :study_id)")
        params["study_id"] = study_id
    if site_id:
        filters.append("(v.site_id = :site_id OR CAST(v.site_id AS TEXT) = :site_id)")
        params["site_id"] = site_id
    where_clause = " AND ".join(filters)

    def _map_visit_status(raw: str) -> str:
        s = (raw or "").strip().lower()
        if s in ("closed", "completed", "approved"):
            return "approved"
        if s in ("in review", "post-visit action"):
            return "report-pending"
        if s == "rejected":
            return "needs-changes"
        if s == "in progress":
            return "in-progress"
        if s == "submitted":
            return "submitted"
        return "planned"

    try:
        visits_rows = await db.execute(
            text(
                f"""
                SELECT
                    v.id,
                    v.site_id,
                    COALESCE(s.name, v.site_id, 'Unknown Site') AS site_name,
                    v.study_id,
                    v.visit_date_iso,
                    v.visit_date,
                    v.site_visit_number,
                    v.cra_name,
                    v.status,
                    COALESCE(COUNT(f.id) FILTER (
                        WHERE LOWER(COALESCE(f.status, '')) NOT IN ('resolved', 'archived')
                    ), 0) AS open_findings
                FROM monitoring_visits v
                LEFT JOIN sites s
                    ON (v.site_id IS NOT NULL
                        AND (v.site_id = s.site_id OR v.site_id = CAST(s.id AS TEXT)))
                LEFT JOIN monitoring_findings f ON f.visit_id = v.id
                WHERE {where_clause}
                GROUP BY
                    v.id, v.site_id, s.name, v.study_id, v.visit_date_iso, v.visit_date,
                    v.site_visit_number, v.cra_name, v.status
                ORDER BY COALESCE(NULLIF(v.visit_date_iso, ''), '9999-12-31T00:00:00Z') ASC
                """
            ),
            params,
        )
    except Exception:
        visits_rows = await db.execute(
            text(
                f"""
                SELECT
                    v.id,
                    v.site_id,
                    COALESCE(v.site_id, 'Unknown Site') AS site_name,
                    v.study_id,
                    v.visit_date_iso,
                    v.visit_date,
                    v.site_visit_number,
                    v.cra_name,
                    v.status,
                    0 AS open_findings
                FROM monitoring_visits v
                WHERE {where_clause}
                ORDER BY COALESCE(NULLIF(v.visit_date_iso, ''), '9999-12-31T00:00:00Z') ASC
                """
            ),
            params,
        )

    finding_links: dict[str, list[str]] = {}
    link_rows = await db.execute(
        text(
            f"""
            SELECT f.id, f.visit_id
            FROM monitoring_findings f
            INNER JOIN monitoring_visits v ON v.id = f.visit_id
            WHERE LOWER(COALESCE(f.status, '')) NOT IN ('resolved', 'archived')
              AND {where_clause}
            """
        ),
        params,
    )
    for row in link_rows.mappings().all():
        vid = str(row["visit_id"])
        finding_links.setdefault(vid, []).append(str(row["id"]))

    items = []
    for row in visits_rows.mappings().all():
        vid = str(row["id"])
        planned = row["visit_date_iso"] or row["visit_date"] or ""
        visit_num = row.get("site_visit_number")
        items.append(
            {
                "id": vid,
                "siteId": str(row["site_id"] or ""),
                "siteName": row["site_name"] or "Unknown Site",
                "visitNumber": int(visit_num) if visit_num is not None else 1,
                "plannedDate": planned,
                "craName": (row.get("cra_name") or "").strip() or None,
                "status": _map_visit_status(row.get("status") or ""),
                "linkedIssueIds": finding_links.get(vid, []),
                "openActionItemsCount": int(row.get("open_findings") or 0),
            }
        )
    return items


@router.get("/monitoring/issues")
async def get_monitoring_issues(
    study_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Site Status / Control Tower — open monitoring findings as issues (camelCase)."""
    from app.modules.monitoring.aggregator import _ensure_monitor_tables

    await _ensure_monitor_tables(db)

    filters = [
        "LOWER(COALESCE(v.status, '')) <> 'archived'",
        "LOWER(COALESCE(f.status, '')) NOT IN ('resolved', 'archived')",
    ]
    params: dict = {}
    if study_id:
        filters.append("(v.study_id = :study_id OR CAST(v.study_id AS TEXT) = :study_id)")
        params["study_id"] = study_id
    if site_id:
        filters.append("(v.site_id = :site_id OR CAST(v.site_id AS TEXT) = :site_id)")
        params["site_id"] = site_id
    where_clause = " AND ".join(filters)

    def _map_severity(sev: str) -> str:
        s = (sev or "").strip().lower()
        if s == "critical":
            return "critical"
        if s == "major":
            return "high"
        if s == "minor":
            return "low"
        return "medium"

    def _map_issue_status(st: str) -> str:
        s = (st or "").strip().lower()
        if s == "resolved":
            return "resolved"
        if s == "archived":
            return "dismissed"
        if s == "in review":
            return "in-progress"
        return "open"

    try:
        rows = await db.execute(
            text(
                f"""
                SELECT
                    f.id,
                    f.category,
                    f.description,
                    f.severity,
                    f.status,
                    f.subject_id,
                    v.site_id,
                    COALESCE(s.name, v.site_id, f.site, 'Unknown Site') AS site_name
                FROM monitoring_findings f
                INNER JOIN monitoring_visits v ON v.id = f.visit_id
                LEFT JOIN sites s
                    ON (v.site_id IS NOT NULL
                        AND (v.site_id = s.site_id OR v.site_id = CAST(s.id AS TEXT)))
                WHERE {where_clause}
                ORDER BY f.id DESC
                """
            ),
            params,
        )
    except Exception:
        rows = await db.execute(
            text(
                f"""
                SELECT
                    f.id,
                    f.category,
                    f.description,
                    f.severity,
                    f.status,
                    f.subject_id,
                    v.site_id,
                    COALESCE(v.site_id, f.site, 'Unknown Site') AS site_name
                FROM monitoring_findings f
                INNER JOIN monitoring_visits v ON v.id = f.visit_id
                WHERE {where_clause}
                ORDER BY f.id DESC
                """
            ),
            params,
        )

    items = []
    for row in rows.mappings().all():
        detected_at = datetime.now(timezone.utc).isoformat()
        subject = (row.get("subject_id") or "").strip()
        items.append(
            {
                "id": str(row["id"]),
                "siteId": str(row["site_id"] or ""),
                "siteName": row["site_name"] or "Unknown Site",
                "detectedAt": detected_at,
                "sourceSystem": "DATA_MONITORING_APP",
                "category": row.get("category") or "General",
                "description": row.get("description") or "",
                "severity": _map_severity(row.get("severity") or ""),
                "status": _map_issue_status(row.get("status") or ""),
                **({"patientId": subject} if subject else {}),
            }
        )
    return items


@router.get("/monitoring/tasks", response_model=List[schemas.TaskResponse])
async def get_monitoring_tasks(
    status: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Monitoring-scoped alias for task listing.
    Keeps backward compatibility with frontend clients that call /monitoring/tasks.
    """
    try:
        from app.modules.operations.repositories import TaskRepository

        filters = {}
        if status:
            filters["status"] = status
        if assignee_id:
            filters["assigneeId"] = assignee_id

        tasks = await TaskRepository.list(limit=limit, offset=offset, **filters)
        from app.modules.operations.task_display import rewrite_tasks_for_display

        display_tasks = await rewrite_tasks_for_display(db, tasks)
        return [_task_doc_to_response(t) for t in display_tasks]
    except Exception as e:
        print(f"Error fetching monitoring tasks: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to fetch monitoring tasks: {str(e)}")


@router.get("/logistics")
async def get_logistics(
    study_id: Optional[str] = Query(None),
    site_id: Optional[str] = Query(None),
    current_user: Optional[dict] = Depends(get_current_user_optional)
):
    """
    Get site logistics data.
    Returns empty array for now - can be extended with real data later.
    """
    # TODO: Implement real logistics data fetching from database
    return []


# ---------------------------------------------------------------------------
# Site Status Dashboard Endpoints (READ‑ONLY)
# ---------------------------------------------------------------------------



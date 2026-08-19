"""
router.py
=========

FastAPI endpoints for the workflow platform. Grouped into:

  Definitions  (the builder talks to these)
  Instances    (the runner talks to these)
  Catalog      (static metadata: available step types)

The router already carries ``prefix="/api/workflows"``, so it must be mounted in
``app.main`` WITHOUT an extra ``/api`` prefix (final paths: /api/workflows/...).

CRM integration notes
----------------------
  * Async endpoints using the shared ``get_db`` dependency (AsyncSession).
  * The ROUTE owns the transaction: every mutating endpoint wraps its service
    call in ``async with transactional(db)``. Services never commit.
  * AUTH: ``current_user`` adapts the CRM ``app.auth.get_current_user`` dict to
    the engine's ``CurrentUser``. The mapping lives in ONE small function
    (``_to_current_user``) so which roles get passed can be adjusted later.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user as _crm_get_current_user
from app.config import settings
from app.db import get_db, transactional

from . import service
from .generate import clarify_workflow, generate_workflow
from .models import WorkflowDefinitionVersion
from .schemas import (
    ActionRequest,
    AgreementResetRequest,
    AuditEntryOut,
    AvailableAction,
    ClarifyRequest,
    CurrentUser,
    DefinitionCreate,
    DefinitionOut,
    DefinitionVersionOut,
    DefinitionVersionSummary,
    DiscussionComment,
    DiscussionPost,
    GenerateRequest,
    InstanceCreate,
    InstanceOut,
    ResetRequest,
    WorkflowDefinitionBody,
)
from .service import ServiceError
from .step_types import STEP_TYPE_CATALOG

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


# Dev-only utility gate (sweeps, resets). Production runs the Celery beat and never
# enables these — 403 there. Strict role enforcement and the unified platform are
# always on (no flags); only genuinely dev-only tools sit behind this.
def _require_dev() -> None:
    if not settings.workflow_dev_sweep:
        raise HTTPException(status_code=403, detail="This dev-only endpoint is disabled.")


async def _real_iam_roles() -> list[str]:
    """Best-effort: the real IAM role vocabulary for the generator. Never blocks
    generation — returns [] if Mongo is unavailable (the model then falls back to
    descriptive role words, which the runtime still slug-matches)."""
    try:
        from app.db.mongo import get_mongo_db
        from app.integrations.iam.users import get_all_iam_roles
        return await get_all_iam_roles(await get_mongo_db())
    except Exception:  # noqa: BLE001
        logger.warning("could not load IAM role vocabulary for generation", exc_info=True)
        return []


# --- auth adapter ----------------------------------------------------------
# The CRM's get_current_user returns a dict: {"user_id", "email", "role", ...}.
# The engine only needs an id + a list of roles. Keep this mapping in ONE place
# so we can widen which roles flow through (e.g. site-scoped role assignments)
# without touching the engine or the endpoints.
def _to_current_user(user: dict) -> CurrentUser:
    user_id = str(user.get("user_id") or "")
    # Prefer the user's FULL real IAM roles (local_user_to_dict["roles"]); fall
    # back to the single legacy role. The engine slug-matches, so raw display
    # strings like "Contract Specialist" are fine here.
    real = user.get("roles")
    if isinstance(real, list) and real:
        roles = [str(r) for r in real if r]
    else:
        role = user.get("role")
        roles = [str(role)] if role else []
    return CurrentUser(id=user_id, roles=roles)


async def current_user(user: dict = Depends(_crm_get_current_user)) -> CurrentUser:
    cu = _to_current_user(user)
    # The auth dict may come from a cached SSO SESSION that only carries the
    # squashed singular `role` (e.g. hub "USER") with NO real roles list — the
    # SSO callback never reads resource_access. The workflow authorizes on the
    # user's REAL IAM roles, so resolve them at request time whenever the dict
    # didn't already carry them. Works for existing sessions (no re-login needed)
    # and is best-effort: on any Mongo error we keep whatever the dict had.
    if not user.get("roles") and cu.id:
        try:
            from app.db.mongo import get_mongo_db
            from app.integrations.iam.users import get_user_real_roles
            real = await get_user_real_roles(await get_mongo_db(), cu.id)
            if real:
                cu = CurrentUser(id=cu.id, roles=real)
        except Exception:  # noqa: BLE001 — never block a request on the role lookup
            logger.warning("current_user: real-role resolution failed for %s",
                           cu.id, exc_info=True)
    return cu


def _err(exc: ServiceError) -> HTTPException:
    msg = str(exc)
    code = 404 if "not found" in msg.lower() else 409
    return HTTPException(status_code=code, detail=msg)


# --- per-instance authorization ---------------------------------------------
async def _require_instance_access(db: AsyncSession, inst, user: CurrentUser) -> None:
    """Deny with 404 (not 403) so instance ids cannot be enumerated: an instance a
    user may not see is indistinguishable from one that does not exist."""
    if not await service.user_can_access_instance(db, inst, user):
        raise HTTPException(status_code=404, detail=f"Instance {inst.id} not found")


async def _require_create_allowed(db: AsyncSession, subject_ref: str | None,
                                  user: CurrentUser) -> None:
    """Starting a workflow requires only authentication.

    Previously reserved to the agreement owner; relaxed so any authenticated user
    can start a workflow on any agreement. Authentication is still enforced by the
    `current_user` dependency on every endpoint that calls this. Kept as a hook so
    the policy can be re-tightened in one place if needed."""
    return


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------
@router.get("/step-types")
async def list_step_types():
    """Metadata the builder palette uses to render draggable step kinds."""
    return STEP_TYPE_CATALOG


@router.get("/permits/owner")
async def permits_owner(subject_ref: str, db: AsyncSession = Depends(get_db),
                        user: CurrentUser = Depends(current_user)):
    """Permission primitive: is the current user the creator/owner of the agreement
    `subject_ref`? Read-only; modules call this for creator-owns-send/receive gating.
    Returns {is_owner, created_by, current_user_id, found}."""
    return await service.is_agreement_owner(db, subject_ref, user.id)


@router.get("/config")
async def workflow_config():
    """Read-only runner config. The unified template-driven platform is always on
    (no flag). `dev_sweep` tells the UI whether the dev-only background sweeper /
    dev controls are enabled (WORKFLOW_DEV_SWEEP); prod uses the Celery beat and
    leaves it off."""
    return {
        "dev_sweep": settings.workflow_dev_sweep,
    }


# ---------------------------------------------------------------------------
# LLM auto-create (DRAFT only — never saved, never published)
# ---------------------------------------------------------------------------
@router.post("/generate/clarify")
async def generate_clarify(req: ClarifyRequest):
    """STEP 1 (clarify): given a plain-English description, return STRUCTURED
    clarifying questions for the genuinely-ambiguous, shape-changing aspects (review
    vs signing order, signers/order, handoff, who-can-send, reject loop), or an empty
    list when the description is clear. The LLM only CLASSIFIES ambiguity here — it
    writes nothing and runs nothing. Returns {questions: [{id, question, options}], clear}."""
    return await clarify_workflow(req.description, req.mermaid)


@router.post("/generate")
async def generate(req: GenerateRequest, user: CurrentUser = Depends(current_user)):
    """STEP 2 (confirm): turn the description (+ any confirmed clarify ANSWERS) into a
    DRAFT WorkflowDefinitionBody PLUS a plain-English summary for the user to confirm.
    Validated against the SAME schema the builder uses; NOT persisted — the human
    approves/edits and publishes via the existing flow (STEP 3 = lock & run). Returns
    {body, assumptions, summary} | {needs_clarification} | {error}.

    REFINE (iterative): when the request carries `prior` (the previously generated
    definition) + `feedback` (a change request), the model MODIFIES that workflow per
    the feedback rather than restarting — the user can refine repeatedly, each round
    building on the last, before approving. Same validation/normalizer/confirm.
    """
    answers = [a.model_dump() for a in req.answers] if req.answers else None
    # The real IAM role vocabulary so the model authors role assignees that real
    # users actually hold (e.g. CONTRACT_SPECIALIST, CRA, PRINCIPAL_INVESTIGATOR).
    iam_roles = await _real_iam_roles()
    result = await generate_workflow(
        req.description, req.key, req.name, answers, req.mermaid,
        prior=req.prior, feedback=req.feedback, feedback_log=req.feedback_log,
        iam_roles=iam_roles,
    )
    if result.get("error"):
        # Could not produce a valid draft (e.g. empty input, model unavailable,
        # or still-invalid after the repair retries).
        raise HTTPException(status_code=422, detail=result["error"])
    return result


# ---------------------------------------------------------------------------
# Definitions
# ---------------------------------------------------------------------------
def _version_out(v) -> DefinitionVersionOut:
    published_by, published_at = service.publish_meta(v)
    return DefinitionVersionOut(
        id=v.id, definition_id=v.definition_id, version=v.version,
        is_published=v.is_published,
        body=WorkflowDefinitionBody.model_validate(v.body),
        created_at=v.created_at,
        published_by=published_by, published_at=published_at,
    )


@router.get("/definitions", response_model=list[DefinitionOut])
async def list_definitions(db: AsyncSession = Depends(get_db),
                           user: CurrentUser = Depends(current_user)):
    out = []
    for d in await service.list_definitions(db):
        pub = next((v for v in d.versions if v.is_published), None)
        # Default version = the published one, else the latest — its body holds the
        # description shown in the library row.
        default = pub or (max(d.versions, key=lambda v: v.version) if d.versions else None)
        published_by, published_at = service.publish_meta(pub) if pub else (None, None)
        out.append(
            DefinitionOut(
                id=d.id, key=d.key, name=d.name,
                latest_version=d.latest_version,
                published_version=d.published_version,
                created_at=d.created_at,
                description=(default.body or {}).get("description") if default else None,
                published_by=published_by, published_at=published_at,
            )
        )
    return out


@router.get("/definitions/{key}/versions", response_model=list[DefinitionVersionSummary])
async def list_definition_versions(key: str, db: AsyncSession = Depends(get_db),
                                   user: CurrentUser = Depends(current_user)):
    """Version history for one workflow — every saved version with publish metadata,
    newest first. Read-only; powers the library's History browser."""
    try:
        versions = await service.list_definition_versions(db, key)
    except ServiceError as e:
        raise _err(e)
    out = []
    for v in sorted(versions, key=lambda x: x.version, reverse=True):
        body = v.body or {}
        published_by, published_at = service.publish_meta(v)
        out.append(
            DefinitionVersionSummary(
                version=v.version, is_published=v.is_published,
                name=body.get("name") or key,
                description=body.get("description"),
                source_prompt=body.get("source_prompt"),
                created_at=v.created_at,
                published_by=published_by, published_at=published_at,
            )
        )
    return out


@router.get("/definitions/{key}", response_model=DefinitionVersionOut)
async def get_definition(key: str, version: int | None = None,
                         db: AsyncSession = Depends(get_db),
                         user: CurrentUser = Depends(current_user)):
    try:
        v = await service.get_definition_version(db, key, version)
    except ServiceError as e:
        raise _err(e)
    return _version_out(v)


@router.post("/definitions/reset")
async def reset_definition(req: ResetRequest, db: AsyncSession = Depends(get_db)):
    """DEV/test only — wipe one template's workflow (definition + versions +
    instances + audit) for `req.key` so it returns to "no workflow yet".

    DEV-ONLY (gated on WORKFLOW_DEV_SWEEP): 403 in prod — never reachable there.
    Deletes ONLY workflow-platform rows; never agreements/documents/templates.
    Idempotent."""
    _require_dev()
    async with transactional(db):
        result = await service.reset_definition(db, req.key)
    return result


@router.post("/instances/reset-agreement")
async def reset_agreement(req: AgreementResetRequest, db: AsyncSession = Depends(get_db)):
    """DEV/test only — study + site SPECIFIC reset. Deletes ONE agreement
    (`req.subject_ref`) + its workflow instance(s) + children, so that single
    (study, site, template) slot is freed and can be recreated. KEEPS the shared
    template workflow definition, the template, and every OTHER site's agreement.

    DEV-ONLY (gated on WORKFLOW_DEV_SWEEP). 403 in prod. Idempotent."""
    _require_dev()
    async with transactional(db):
        result = await service.reset_agreement(db, req.subject_ref)
    return result


@router.post("/definitions", response_model=DefinitionVersionOut, status_code=201)
async def save_definition(req: DefinitionCreate, db: AsyncSession = Depends(get_db),
                          user: CurrentUser = Depends(current_user)):
    # Publishing makes this version the type's default for future agreements, so
    # we record WHO did it (the authenticated user). Auth required for governance.
    try:
        async with transactional(db):
            v = await service.create_or_update_definition(
                db, req.body, publish=req.publish, published_by=user.id)
    except ServiceError as e:
        raise _err(e)
    return _version_out(v)


@router.post("/definitions/{key}/publish/{version}", response_model=DefinitionVersionOut)
async def publish(key: str, version: int, db: AsyncSession = Depends(get_db),
                  user: CurrentUser = Depends(current_user)):
    try:
        async with transactional(db):
            v = await service.publish_version(db, key, version, published_by=user.id)
    except ServiceError as e:
        raise _err(e)
    return _version_out(v)


# ---------------------------------------------------------------------------
# External message events (V2 Phase 5) — the event router boundary. A message
# named `name`, correlated by subject_ref, resumes any instance parked on a
# matching wait_message step. Authenticated; webhook callers use a service
# account token like any other API client.
# ---------------------------------------------------------------------------
class MessageEventRequest(BaseModel):
    name: str
    subject_ref: str
    payload: dict = {}


@router.post("/events")
async def post_message_event(req: MessageEventRequest,
                             db: AsyncSession = Depends(get_db),
                             user: CurrentUser = Depends(current_user)):
    try:
        async with transactional(db):
            return await service.deliver_message(db, req.name, req.subject_ref,
                                                 req.payload)
    except ServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Tasks (V2 Phase 3) — the worklist read-model and task lifecycle.
# ---------------------------------------------------------------------------
@router.get("/tasks")
async def my_tasks(status: str = "open", db: AsyncSession = Depends(get_db),
                   user: CurrentUser = Depends(current_user)):
    """My open steps across all instances (strict mode: tasks addressed to me by
    user / role / resolved context participant / claim)."""
    return await service.list_tasks_for_user(db, user, status=status)


@router.post("/tasks/{task_id}/claim")
async def claim_task(task_id: int, db: AsyncSession = Depends(get_db),
                     user: CurrentUser = Depends(current_user)):
    try:
        task = await service.get_task(db, task_id)
        inst = await service.get_instance(db, task.instance_id)
        await _require_instance_access(db, inst, user)
        async with transactional(db):
            return await service.claim_task(db, task_id, user)
    except ServiceError as e:
        raise _err(e)


class ReassignRequest(BaseModel):
    user_id: str


@router.post("/tasks/{task_id}/reassign")
async def reassign_task(task_id: int, req: ReassignRequest,
                        db: AsyncSession = Depends(get_db),
                        user: CurrentUser = Depends(current_user)):
    """Move one work item to a specific user. Worklist-level AND effective: the
    engine honors the reassignment in place of the definition's assignee for
    this step/slot. Audited on the instance."""
    try:
        task = await service.get_task(db, task_id)
        inst = await service.get_instance(db, task.instance_id)
        await _require_instance_access(db, inst, user)
        async with transactional(db):
            return await service.reassign_task(db, task_id, user, req.user_id)
    except ServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------
async def _instance_out(db: AsyncSession, inst) -> InstanceOut:
    """Build the response. Resolves the current step's type/name from the pinned
    version body, fetched explicitly (no lazy relationship access under async)."""
    step_type = step_name = None
    if inst.current_step:
        version = await db.get(WorkflowDefinitionVersion, inst.version_id)
        body = WorkflowDefinitionBody.model_validate(version.body)
        step = next((s for s in body.steps if s.id == inst.current_step), None)
        if step:
            step_type = step.type.value
            step_name = step.name
    return InstanceOut(
        id=inst.id, definition_key=inst.definition_key,
        definition_version=inst.definition_version, status=inst.status,
        current_step=inst.current_step, current_step_type=step_type,
        current_step_name=step_name, subject_ref=inst.subject_ref,
        context=inst.context, created_at=inst.created_at, updated_at=inst.updated_at,
    )


@router.post("/instances", response_model=InstanceOut, status_code=201)
async def create_instance(req: InstanceCreate, db: AsyncSession = Depends(get_db),
                          user: CurrentUser = Depends(current_user)):
    await _require_create_allowed(db, req.subject_ref, user)
    try:
        async with transactional(db):
            inst = await service.start_instance(
                db, req.definition_key, req.context, req.subject_ref,
                started_by=user.id,
            )
    except ServiceError as e:
        raise _err(e)
    return await _instance_out(db, inst)


@router.post("/instances/ensure", response_model=InstanceOut)
async def ensure_instance(req: InstanceCreate, db: AsyncSession = Depends(get_db),
                          user: CurrentUser = Depends(current_user)):
    """Idempotent: return the existing instance for (subject_ref, definition_key)
    or start exactly one on the published version. Used by the unified template-
    driven page (definition key 'tpl:<template_id>') so an agreement gets exactly
    one workflow instance no matter how often the page resolves it. subject_ref is
    required here (it's what we dedupe on)."""
    if not req.subject_ref:
        raise HTTPException(status_code=422, detail="subject_ref is required for ensure")
    await _require_create_allowed(db, req.subject_ref, user)
    try:
        async with transactional(db):
            inst = await service.ensure_instance(
                db, req.definition_key, req.subject_ref, req.context,
                started_by=user.id,
            )
    except ServiceError as e:
        raise _err(e)
    await _require_instance_access(db, inst, user)
    return await _instance_out(db, inst)


@router.get("/instances", response_model=InstanceOut | None)
async def find_instance(subject_ref: str, definition_key: str | None = None,
                        db: AsyncSession = Depends(get_db),
                        user: CurrentUser = Depends(current_user)):
    """Read-only: resolve the newest workflow instance for a subject (e.g. an
    agreement id), optionally scoped to a definition_key (CDA/CTA). Returns the
    instance (current_step / current_step_type / current_step_name / status /
    context) or null when none exists. Used by the read-only "Engine step" overlay
    on the real agreement screens — it observes, never advances anything."""
    inst = await service.find_instance_by_subject(db, subject_ref, definition_key)
    if inst is None:
        return None
    # Inaccessible looks exactly like nonexistent (anti-enumeration).
    if not await service.user_can_access_instance(db, inst, user):
        return None
    return await _instance_out(db, inst)


@router.get("/instances/{instance_id}", response_model=InstanceOut)
async def get_instance(instance_id: int, db: AsyncSession = Depends(get_db),
                       user: CurrentUser = Depends(current_user)):
    try:
        inst = await service.get_instance(db, instance_id)
    except ServiceError as e:
        raise _err(e)
    await _require_instance_access(db, inst, user)
    return await _instance_out(db, inst)


@router.get("/instances/{instance_id}/actions", response_model=list[AvailableAction])
async def get_actions(instance_id: int, db: AsyncSession = Depends(get_db),
                      user: CurrentUser = Depends(current_user)):
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        return await service.available_actions(db, instance_id, user)
    except ServiceError as e:
        raise _err(e)


@router.post("/instances/{instance_id}/actions", response_model=InstanceOut)
async def act(instance_id: int, req: ActionRequest, db: AsyncSession = Depends(get_db),
              user: CurrentUser = Depends(current_user)):
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        async with transactional(db):
            inst = await service.perform_action(
                db, instance_id, user, req.transition_id, req.payload, req.comment
            )
    except ServiceError as e:
        raise _err(e)
    return await _instance_out(db, inst)


@router.post("/instances/{instance_id}/cancel", response_model=InstanceOut)
async def cancel(instance_id: int, req: ActionRequest | None = None,
                 db: AsyncSession = Depends(get_db),
                 user: CurrentUser = Depends(current_user)):
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        async with transactional(db):
            inst = await service.cancel_instance(
                db, instance_id, user, comment=req.comment if req else None
            )
    except ServiceError as e:
        raise _err(e)
    return await _instance_out(db, inst)


@router.get("/instances/{instance_id}/activity")
async def get_activity(instance_id: int, db: AsyncSession = Depends(get_db),
                       user: CurrentUser = Depends(current_user)):
    """Read-only: job executions + boundary timers for this instance (the
    runner's job panel and armed-timer indicator)."""
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        return await service.list_activity(db, instance_id)
    except ServiceError as e:
        raise _err(e)


@router.post("/instances/{instance_id}/jobs/{job_id}/retry")
async def retry_job(instance_id: int, job_id: int, db: AsyncSession = Depends(get_db),
                    user: CurrentUser = Depends(current_user)):
    """Reset a FAILED automated-step job to pending; the next sweep re-runs it."""
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        async with transactional(db):
            return await service.retry_job(db, instance_id, job_id, user)
    except ServiceError as e:
        raise _err(e)


@router.post("/run-sweeps")
async def run_sweeps(db: AsyncSession = Depends(get_db),
                     user: CurrentUser = Depends(current_user)):
    """DEV-ONLY (gated on WORKFLOW_DEV_SWEEP): run the timer + job sweeps once, now.
    Dev stacks run no celery beat, so the runner triggers sweeps to make pending
    jobs and due timers visibly execute. Production runs the beat schedule (403 here)."""
    _require_dev()
    async with transactional(db):
        return await service.run_sweeps_once(db)


@router.get("/instances/{instance_id}/children")
async def get_children(instance_id: int, db: AsyncSession = Depends(get_db),
                       user: CurrentUser = Depends(current_user)):
    """Read-only: the child instances spawned by this parent's call steps
    (including cancelled children, so a stuck parent is diagnosable)."""
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        return await service.list_children(db, instance_id)
    except ServiceError as e:
        raise _err(e)


@router.get("/instances/{instance_id}/audit", response_model=list[AuditEntryOut])
async def get_audit(instance_id: int, db: AsyncSession = Depends(get_db),
                    user: CurrentUser = Depends(current_user)):
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        # get_audit_view resolves each actor to a human-readable email/name for the
        # History panel; the stored audit row keeps the canonical acting user id.
        return await service.get_audit_view(db, instance_id)
    except ServiceError as e:
        raise _err(e)


# ---------------------------------------------------------------------------
# Discussion (NEED 1) — a tracked two-party comment exchange on a discussion step.
# Reuses agreement_comments for storage; resolve is a normal /actions advance.
# Part of the unified platform — always on (instance access is still enforced).
# ---------------------------------------------------------------------------
@router.get("/instances/{instance_id}/discussion", response_model=list[DiscussionComment])
async def get_discussion(instance_id: int, db: AsyncSession = Depends(get_db),
                         user: CurrentUser = Depends(current_user)):
    """The tracked discussion thread for this instance (visible to both parties)."""
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        return await service.list_discussion(db, instance_id)
    except ServiceError as e:
        raise _err(e)


@router.post("/instances/{instance_id}/discussion", response_model=DiscussionComment, status_code=201)
async def post_discussion(instance_id: int, req: DiscussionPost,
                          db: AsyncSession = Depends(get_db),
                          user: CurrentUser = Depends(current_user)):
    """Append one comment to the discussion. Stored + visible to both + audited
    (append-only rows). Resolution advances via the normal /actions endpoint."""
    try:
        inst = await service.get_instance(db, instance_id)
        await _require_instance_access(db, inst, user)
        async with transactional(db):
            return await service.post_discussion(db, instance_id, user, req.content, req.party)
    except ServiceError as e:
        raise _err(e)

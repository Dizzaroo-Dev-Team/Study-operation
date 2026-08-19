"""
service.py
==========

Orchestration between the pure engine and the database. The router calls these
functions; they own the *query* logic but NOT the transaction boundary.

CRM integration notes
----------------------
  * Async throughout (AsyncSession). All DB calls are awaited.
  * NO commit() / refresh() here. In this repo the route owns the transaction via
    ``async with transactional(db)`` and services never commit. These functions
    ``flush()`` so generated ids / server defaults are available, then return —
    the router's ``transactional`` block commits (or rolls back) the unit of work.
  * Relationships are eager-loaded (selectinload) wherever a caller reads them,
    because lazy loading is not allowed under async sessions.

Responsibilities:
  * create / publish workflow definitions (each save -> a new immutable version)
  * start an instance against the published version of a definition
  * compute available actions for a given user
  * perform an action (delegating the rules to the engine) and record an audit row
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from . import kernel
from .engine import EngineError, WorkflowEngine, role_matches, role_slug
from .models import (
    WorkflowAuditEntry,
    WorkflowDefinition,
    WorkflowDefinitionVersion,
    WorkflowInstance,
    WorkflowJob,
    WorkflowTask,
    WorkflowTimer,
)
from .schemas import (
    Assignee,
    AssigneeType,
    AvailableAction,
    BroadcastConfig,
    CurrentUser,
    OrderedSigningConfig,
    ParallelConfig,
    WorkflowDefinitionBody,
)


logger = logging.getLogger(__name__)


class ServiceError(Exception):
    """User-facing problem (404 / 409 / 422 level)."""


# ---------------------------------------------------------------------------
# Definitions & versions
# ---------------------------------------------------------------------------
# Reserved keys stored in a version's `body` JSON to record WHO published it and
# WHEN. They are NOT part of the workflow language: WorkflowDefinitionBody ignores
# unknown keys on model_validate, so the engine/builder never see them, and no DB
# migration is needed (we reuse the existing JSON column).
_PUBLISHED_BY_KEY = "_published_by"
_PUBLISHED_AT_KEY = "_published_at"


def publish_meta(version: WorkflowDefinitionVersion) -> tuple[Optional[str], Optional[str]]:
    """(published_by, published_at) recorded on a version, if any."""
    body = version.body or {}
    return body.get(_PUBLISHED_BY_KEY), body.get(_PUBLISHED_AT_KEY)


async def create_or_update_definition(
    db: AsyncSession, body: WorkflowDefinitionBody, publish: bool = False,
    published_by: Optional[str] = None,
) -> WorkflowDefinitionVersion:
    """Save a new version of a workflow. Creating the definition the first time,
    or appending a new version to an existing key. Existing in-flight instances
    are untouched because they reference their own version row.

    When ``publish`` is True the new version becomes the type's default; we stamp
    WHO published it (``published_by``) and WHEN into the body JSON for audit.

    Mutations are flushed (not committed) — the router's ``transactional`` block
    is the commit boundary.
    """
    # Authoring guard: a wait_condition step must name a REGISTERED condition, else it
    # would hold forever at runtime. Fail the publish with a clear, actionable error
    # rather than shipping a workflow that can never advance. (Schema validation already
    # checked the WaitConfig shape + condition_met transition; this checks the name is
    # one the engine can actually evaluate.)
    from .schemas import StepType, WaitConfig
    from .waits import registered_conditions
    known = registered_conditions()
    for s in body.steps:
        if s.type == StepType.WAIT_CONDITION:
            cond = WaitConfig.model_validate((s.config or {}).get("wait") or {}).condition
            if cond not in known:
                raise ServiceError(
                    f"wait_condition step '{s.id}' uses unknown condition '{cond}'; "
                    f"registered conditions: {sorted(known)}")

    definition = await db.scalar(
        select(WorkflowDefinition).where(WorkflowDefinition.key == body.key)
    )
    if definition is None:
        definition = WorkflowDefinition(key=body.key, name=body.name)
        db.add(definition)
        await db.flush()
        next_version = 1
    else:
        definition.name = body.name
        # Compute the next version with an explicit MAX query rather than reading
        # the (lazy) versions relationship — safe under async.
        current_max = await db.scalar(
            select(func.max(WorkflowDefinitionVersion.version)).where(
                WorkflowDefinitionVersion.definition_id == definition.id
            )
        )
        next_version = (current_max or 0) + 1

    if publish:
        # Only one published version at a time per definition. A bulk UPDATE
        # avoids having to load the versions collection.
        await db.execute(
            update(WorkflowDefinitionVersion)
            .where(WorkflowDefinitionVersion.definition_id == definition.id)
            .values(is_published=False)
        )

    body_json = body.model_dump(mode="json")
    if publish:
        body_json[_PUBLISHED_BY_KEY] = published_by
        body_json[_PUBLISHED_AT_KEY] = datetime.now(timezone.utc).isoformat()

    version = WorkflowDefinitionVersion(
        definition_id=definition.id,
        version=next_version,
        is_published=publish,
        body=body_json,
    )
    db.add(version)
    await db.flush()  # populates version.id + server-default created_at (eager_defaults)
    return version


async def publish_version(
    db: AsyncSession, key: str, version_number: int, published_by: Optional[str] = None
) -> WorkflowDefinitionVersion:
    definition = await _get_definition(db, key)
    target = next((v for v in definition.versions if v.version == version_number), None)
    if target is None:
        raise ServiceError(f"Version {version_number} not found for '{key}'")
    for v in definition.versions:
        v.is_published = v.id == target.id
    # Stamp WHO/WHEN this version became the default (reassign dict so the JSON
    # column is marked dirty).
    target.body = {
        **(target.body or {}),
        _PUBLISHED_BY_KEY: published_by,
        _PUBLISHED_AT_KEY: datetime.now(timezone.utc).isoformat(),
    }
    await db.flush()
    return target


async def list_definitions(db: AsyncSession) -> list[WorkflowDefinition]:
    result = await db.scalars(
        select(WorkflowDefinition)
        .options(selectinload(WorkflowDefinition.versions))
        .order_by(WorkflowDefinition.key)
    )
    return list(result.all())


async def list_definition_versions(
    db: AsyncSession, key: str
) -> list[WorkflowDefinitionVersion]:
    """Every version of one definition, oldest first (the relationship is ordered
    by version). Read-only — powers the library's version-history browser."""
    definition = await _get_definition(db, key)
    return list(definition.versions)


async def get_definition_version(
    db: AsyncSession, key: str, version: Optional[int] = None
) -> WorkflowDefinitionVersion:
    definition = await _get_definition(db, key)
    if version is not None:
        v = next((x for x in definition.versions if x.version == version), None)
        if v is None:
            raise ServiceError(f"Version {version} not found for '{key}'")
        return v
    # default: published, else latest
    published = [x for x in definition.versions if x.is_published]
    if published:
        return max(published, key=lambda x: x.version)
    if not definition.versions:
        raise ServiceError(f"'{key}' has no versions")
    return max(definition.versions, key=lambda x: x.version)


async def _get_definition(db: AsyncSession, key: str) -> WorkflowDefinition:
    definition = await db.scalar(
        select(WorkflowDefinition)
        .options(selectinload(WorkflowDefinition.versions))
        .where(WorkflowDefinition.key == key)
    )
    if definition is None:
        raise ServiceError(f"Workflow '{key}' not found")
    return definition


# ---------------------------------------------------------------------------
# Instances
# ---------------------------------------------------------------------------
def _body_of(version: WorkflowDefinitionVersion) -> WorkflowDefinitionBody:
    return WorkflowDefinitionBody.model_validate(version.body)


def _strip_reserved_context_keys(context: Optional[dict]) -> dict:
    """Engine-owned (underscore-prefixed) keys — e.g. the _branches vote ledger —
    must never arrive from a client at instance start. Stripped (not rejected) so
    internal callers passing a previously-read context stay working."""
    clean = {k: v for k, v in (context or {}).items() if not k.startswith("_")}
    if len(clean) != len(context or {}):
        dropped = sorted(set(context or {}) - set(clean))
        logger.warning("start_instance: dropped reserved context keys %s", dropped)
    return clean


async def start_instance(
    db: AsyncSession, definition_key: str, context: dict,
    subject_ref: Optional[str] = None,
    parent_instance_id: Optional[int] = None,
    parent_step_id: Optional[str] = None,
    started_by: Optional[str] = None,
) -> WorkflowInstance:
    version = await get_definition_version(db, definition_key)  # published preferred
    body = _body_of(version)

    blank = kernel.InstanceState(status="active", current_step=None, context={})
    decision = kernel.decide(
        body, blank, kernel.StartWorkflow(context=_strip_reserved_context_keys(context)),
        enforce_roles=True,
    )

    instance = WorkflowInstance(
        version_id=version.id,
        definition_key=body.key,
        definition_version=version.version,
        status=decision.state.status,
        current_step=decision.state.current_step,
        subject_ref=subject_ref,
        parent_instance_id=parent_instance_id,
        parent_step_id=parent_step_id,
        context=decision.state.context,
    )
    db.add(instance)
    await db.flush()
    # Record who started it, so a non-owner starter keeps visibility on the
    # instance they created (user_can_access_instance grants access to anyone who
    # has acted on it — see condition #3). No-op for system/internal starts.
    if started_by:
        _log(db, instance, actor=started_by, action="started")
    await _execute_commands(db, instance, decision.commands)
    await db.flush()
    await _maybe_notify_parent(db, instance)  # a child can complete at start
    return instance


async def get_instance(db: AsyncSession, instance_id: int,
                       for_update: bool = False) -> WorkflowInstance:
    """Load one instance. ``for_update=True`` takes a row lock (SELECT ... FOR
    UPDATE) for the rest of the surrounding transaction, so concurrent actions on
    the same instance SERIALIZE instead of racing read-modify-write (a lost
    parallel-branch vote was possible before). On SQLite the clause is a no-op —
    the lock matters on Postgres, where production runs."""
    instance = await db.get(WorkflowInstance, instance_id, with_for_update=for_update)
    if instance is None:
        raise ServiceError(f"Instance {instance_id} not found")
    return instance


async def is_agreement_owner(db: AsyncSession, subject_ref: str, user_id: Optional[str]) -> dict:
    """Permission primitive for modules: is `user_id` the creator/owner of the
    agreement `subject_ref`? Reuses Agreement.created_by (the existing ownership
    field). Read-only. Returns {is_owner, created_by, current_user_id, found}.
    Modules use this for creator-owns-send/receive gating; default-deny when the
    subject can't be resolved (found=False)."""
    from app.models import Agreement

    created_by = None
    found = False
    if subject_ref:
        ag = await db.get(Agreement, subject_ref)
        if ag is not None:
            found = True
            created_by = ag.created_by
    is_owner = bool(found and user_id and created_by and str(user_id) == str(created_by))
    return {
        "is_owner": is_owner,
        "created_by": created_by,
        "current_user_id": str(user_id) if user_id else None,
        "found": found,
    }


# ---------------------------------------------------------------------------
# Per-instance access control (router-level authorization, NOT engine action
# authorization). A user may SEE an instance (state / audit / actions) when they
# are the agreement owner, match any assignee in the pinned definition (steps,
# parallel branches, signer slots, broadcast recipients), or have already acted
# on it. This is always strict — there is no open mode.
# ---------------------------------------------------------------------------
def _assignee_matches(assignee: Optional[Assignee], context: dict,
                      user: CurrentUser) -> bool:
    """Same matching rules as the engine's strict-mode user_can_act."""
    if assignee is None or assignee.value is None:
        return False
    if assignee.type == AssigneeType.ROLE:
        return role_matches(assignee.value, user.roles)
    if assignee.type == AssigneeType.USER:
        return assignee.value == user.id
    if assignee.type == AssigneeType.CONTEXT:
        return bool(user.id) and (context or {}).get(assignee.value) == user.id
    return False


def _user_matches_definition(body: WorkflowDefinitionBody, context: dict,
                             user: CurrentUser) -> bool:
    """True when the user is named anywhere in the definition: a step assignee,
    a parallel/fan-out branch, an ordered-signing slot, or a broadcast recipient.
    Configs are parsed leniently — a malformed config never blocks the check."""
    for step in body.steps:
        if _assignee_matches(step.assignee, context, user):
            return True
        try:
            if step.type.value == "parallel":
                cfg = ParallelConfig.model_validate(step.config)
                if any(_assignee_matches(b.assignee, context, user) for b in cfg.branches):
                    return True
            elif step.type.value == "ordered_signing":
                cfg = OrderedSigningConfig.model_validate(step.config)
                if any(_assignee_matches(s.assignee, context, user) for s in cfg.signers):
                    return True
            elif step.type.value == "broadcast":
                cfg = BroadcastConfig.model_validate(step.config)
                if any(_assignee_matches(r.assignee, context, user) for r in cfg.recipients):
                    return True
        except Exception:  # noqa: BLE001 — bad authoring must not block access checks
            continue
    return False


async def user_can_access_instance(db: AsyncSession, instance: WorkflowInstance,
                                   user: CurrentUser) -> bool:
    """Router-level read/see authorization for one instance. Default-deny; a user
    may only see instances they participate in (no open mode)."""
    if not user.id:
        return False
    # 1. Agreement owner (creator-owns).
    if instance.subject_ref:
        owner = await is_agreement_owner(db, instance.subject_ref, user.id)
        if owner["is_owner"]:
            return True
    # 2. Named participant in the pinned definition version.
    version = await db.get(WorkflowDefinitionVersion, instance.version_id)
    if version is not None:
        try:
            body = _body_of(version)
            if _user_matches_definition(body, instance.context or {}, user):
                return True
        except Exception:  # noqa: BLE001 — unparseable body must not grant/blow up
            logger.warning("access check: could not parse definition body for instance %s",
                           instance.id, exc_info=True)
    # 3. Someone who already acted on this instance keeps visibility.
    acted = await db.scalar(
        select(WorkflowAuditEntry.id)
        .where(WorkflowAuditEntry.instance_id == instance.id,
               WorkflowAuditEntry.actor == user.id)
        .limit(1)
    )
    return acted is not None


# Agreement child tables (FK -> agreements.id), ordered so a plain DELETE per table
# never violates an inter-child FK (OTPs before their tokens; anything that points at
# a document before agreement_documents; documents before agreements last). Used by
# the dev reset to fully tear an agreement down. Discovered from information_schema
# (every table carrying an agreement_id column).
_AGREEMENT_CHILD_TABLES = (
    "agreement_review_otps", "agreement_signing_otps",
    "agreement_review_tokens", "agreement_signing_tokens",
    "agreement_internal_signatures", "agreement_reviewer_signatures",
    "agreement_signed_documents", "agreement_document_comments",
    "agreement_inline_comments", "agreement_changes", "agreement_comments",
    "agreement_negotiation_rounds", "agreement_review_documents",
    "agreement_signers", "cta_assignments", "cta_placeholder_mappings",
    "agreement_documents",
)


async def _existing_agreement_ids(db: AsyncSession, subject_refs) -> list[str]:
    """Keep only the subject_refs that are real, existing agreement UUIDs. (Verify
    scripts use non-UUID subject_refs like "agreement-A1"; those match nothing.)"""
    from sqlalchemy import bindparam, text
    from uuid import UUID as _UUID

    valid = []
    for s in subject_refs:
        try:
            valid.append(str(_UUID(str(s))))
        except (ValueError, TypeError):
            continue
    if not valid:
        return []
    return list((await db.execute(
        text("SELECT id::text FROM agreements WHERE id::text IN :ids")
        .bindparams(bindparam("ids", expanding=True)),
        {"ids": valid},
    )).scalars().all())


async def _delete_agreements(db: AsyncSession, agreement_ids: list[str]) -> int:
    """Delete the given agreement rows + every child row (documents, comments,
    signatures, tokens, OTPs, …), child tables first (FK-safe order), agreements
    last. `agreement_ids` must already be known-existing string UUIDs. Returns the
    number of agreement rows deleted. Never touches templates."""
    from sqlalchemy import bindparam, text

    if not agreement_ids:
        return 0
    for tbl in _AGREEMENT_CHILD_TABLES:
        await db.execute(
            text(f"DELETE FROM {tbl} WHERE agreement_id::text IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": agreement_ids},
        )
    ar = await db.execute(
        text("DELETE FROM agreements WHERE id::text IN :ids")
        .bindparams(bindparam("ids", expanding=True)),
        {"ids": agreement_ids},
    )
    return ar.rowcount or 0


async def reset_definition(db: AsyncSession, key: str) -> dict:
    """DEV/test (gated to WORKFLOW_UNIFIED by the route): wipe a single template's
    WORKFLOW so it can be redefined — definition + ALL versions + ALL instances on
    this key (across every site) + their audit. Does NOT delete agreements (that
    would be the template-wide teardown the user does NOT want) and never touches
    templates. For a study+site-specific reset use ``reset_agreement``.
    Idempotent: zero counts when there is nothing to delete."""
    inst_ids = (
        await db.execute(select(WorkflowInstance.id).where(WorkflowInstance.definition_key == key))
    ).scalars().all()
    audit_deleted = 0
    if inst_ids:
        r = await db.execute(delete(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id.in_(inst_ids)))
        audit_deleted = r.rowcount or 0
    inst_r = await db.execute(delete(WorkflowInstance).where(WorkflowInstance.definition_key == key))

    definition = await db.scalar(select(WorkflowDefinition).where(WorkflowDefinition.key == key))
    versions_deleted = 0
    if definition is not None:
        vr = await db.execute(
            delete(WorkflowDefinitionVersion).where(WorkflowDefinitionVersion.definition_id == definition.id))
        versions_deleted = vr.rowcount or 0
        await db.execute(delete(WorkflowDefinition).where(WorkflowDefinition.id == definition.id))

    return {
        "key": key,
        "instances_deleted": inst_r.rowcount or 0,
        "audit_deleted": audit_deleted,
        "versions_deleted": versions_deleted,
        "definition_deleted": definition is not None,
    }


async def reset_agreement(db: AsyncSession, subject_ref: str) -> dict:
    """DEV/test (gated to WORKFLOW_UNIFIED by the route): study + site SPECIFIC reset.

    Given ONE agreement (``subject_ref`` = the agreement id, which already encodes
    study + site + template), delete:
      * that agreement's workflow instance(s) on ANY key + their audit, and
      * the agreement row itself + every child row (documents, comments, signatures,
        tokens, OTPs, …).

    KEEPS the shared template workflow DEFINITION, the TEMPLATE, and EVERY OTHER
    site's agreement + instance. This frees just THIS (study_site, type) slot so a
    fresh agreement can be created from the same template, without disturbing other
    study/site combos that share the blueprint. Idempotent."""
    aid = str(subject_ref)
    inst_ids = (
        await db.execute(select(WorkflowInstance.id).where(WorkflowInstance.subject_ref == aid))
    ).scalars().all()
    audit_deleted = 0
    if inst_ids:
        r = await db.execute(delete(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id.in_(inst_ids)))
        audit_deleted = r.rowcount or 0
    inst_r = await db.execute(delete(WorkflowInstance).where(WorkflowInstance.subject_ref == aid))

    existing = await _existing_agreement_ids(db, [aid])
    agreements_deleted = await _delete_agreements(db, existing)

    return {
        "subject_ref": aid,
        "instances_deleted": inst_r.rowcount or 0,
        "audit_deleted": audit_deleted,
        "agreements_deleted": agreements_deleted,
    }


async def reset_agreement_workflow(db: AsyncSession, subject_ref: str) -> dict:
    """Supersede helper: clear ONE agreement's workflow RUN so a fresh instance can
    start at draft — WITHOUT deleting the agreement, its documents (including signed
    history), signatures, or the main audit_logs. Removes only the engine artifacts
    for this subject: open tasks, timers, jobs, audit entries, and the instance rows.

    Used by agreement creation when it supersedes a previously-signed (or different-
    template) agreement in place: the document history is kept, but the prior engine
    run is cleared so the unified page's ensure call starts a clean draft. Idempotent."""
    aid = str(subject_ref)
    inst_ids = (
        await db.execute(select(WorkflowInstance.id).where(WorkflowInstance.subject_ref == aid))
    ).scalars().all()
    tasks_deleted = timers_deleted = jobs_deleted = audit_deleted = 0
    if inst_ids:
        tr = await db.execute(delete(WorkflowTask).where(WorkflowTask.instance_id.in_(inst_ids)))
        tasks_deleted = tr.rowcount or 0
        tmr = await db.execute(delete(WorkflowTimer).where(WorkflowTimer.instance_id.in_(inst_ids)))
        timers_deleted = tmr.rowcount or 0
        jr = await db.execute(delete(WorkflowJob).where(WorkflowJob.instance_id.in_(inst_ids)))
        jobs_deleted = jr.rowcount or 0
        ar = await db.execute(delete(WorkflowAuditEntry).where(WorkflowAuditEntry.instance_id.in_(inst_ids)))
        audit_deleted = ar.rowcount or 0
    ir = await db.execute(delete(WorkflowInstance).where(WorkflowInstance.subject_ref == aid))
    return {
        "subject_ref": aid,
        "instances_deleted": ir.rowcount or 0,
        "tasks_deleted": tasks_deleted,
        "timers_deleted": timers_deleted,
        "jobs_deleted": jobs_deleted,
        "audit_deleted": audit_deleted,
    }


async def ensure_instance(
    db: AsyncSession, definition_key: str, subject_ref: str,
    context: Optional[dict] = None, started_by: Optional[str] = None,
) -> WorkflowInstance:
    """Idempotently ensure EXACTLY ONE instance exists for (subject_ref,
    definition_key). Returns the existing newest instance if one is linked,
    otherwise starts one on the published version. This is the generic twin of the
    CDA/CTA bridges' ensure helpers — used by the unified template-driven page where
    the definition key is "tpl:<template_id>". Guarantees one instance per agreement
    + template workflow no matter how many times the page calls it."""
    existing = await find_instance_by_subject(db, subject_ref, definition_key)
    if existing is not None:
        return existing
    ctx = dict(context or {})
    # Bind the workflow OWNER to the agreement's CREATOR. Owner/drafter steps are
    # authored as {"type":"context","value":"owner_user_id"} (not a role), so the
    # person who created the agreement can always drive it regardless of their IAM
    # role name. Resolved from Agreement.created_by here.
    if subject_ref and "owner_user_id" not in ctx:
        owner = await is_agreement_owner(db, subject_ref, None)
        if owner.get("created_by"):
            ctx["owner_user_id"] = str(owner["created_by"])
    return await start_instance(db, definition_key, ctx, subject_ref=subject_ref,
                                started_by=started_by)


async def find_instance_by_subject(
    db: AsyncSession, subject_ref: str, definition_key: Optional[str] = None
) -> Optional[WorkflowInstance]:
    """Read-only lookup: the newest instance linked to a subject (e.g. an agreement
    id), optionally scoped to one definition_key. Returns None when there is none.

    This is the HTTP-exposed twin of the bridges' internal ``_find_instance`` — the
    ``subject_ref`` column is indexed (models.py), so this is a cheap point lookup.
    Used by the read-only "Engine step" overlay; it never mutates anything."""
    stmt = select(WorkflowInstance).where(WorkflowInstance.subject_ref == str(subject_ref))
    if definition_key:
        stmt = stmt.where(WorkflowInstance.definition_key == definition_key)
    return await db.scalar(stmt.order_by(WorkflowInstance.id.desc()))


async def available_actions(
    db: AsyncSession, instance_id: int, user: CurrentUser
) -> list[AvailableAction]:
    instance = await get_instance(db, instance_id)
    if instance.status != "active" or instance.current_step is None:
        return []
    engine = await _engine_for(db, instance)
    return engine.available_actions(instance.current_step, instance.context, user)


async def perform_action(
    db: AsyncSession,
    instance_id: int,
    user: CurrentUser,
    transition_id: str,
    payload: dict,
    comment: Optional[str] = None,
    trusted_payload: bool = False,
) -> WorkflowInstance:
    # Row-locked read: the instance row stays locked until the route's
    # transactional block commits, so two simultaneous actions (e.g. two branch
    # votes, or one double-clicked action) run one-after-the-other against fresh
    # state. The loser of a duplicate then fails cleanly inside the kernel
    # (double vote / unknown transition on the new step) instead of silently
    # overwriting the winner's context.
    instance = await get_instance(db, instance_id, for_update=True)
    version = await db.get(WorkflowDefinitionVersion, instance.version_id)
    body = _body_of(version)

    state = kernel.InstanceState(instance.status, instance.current_step, instance.context)
    event = kernel.ActionPerformed(user=user, transition_id=transition_id,
                                   payload=payload, comment=comment,
                                   trusted_payload=trusted_payload)
    try:
        decision = kernel.decide(body, state, event,
                                 enforce_roles=True)
    except (EngineError, kernel.KernelError) as exc:
        raise ServiceError(str(exc)) from exc

    instance.current_step = decision.state.current_step
    instance.context = decision.state.context  # includes _branches — JSON, no migration
    instance.status = decision.state.status

    await _execute_commands(db, instance, decision.commands)
    await db.flush()
    await _maybe_notify_parent(db, instance)
    await _maybe_finalize_agreement_subject(db, instance)
    return instance


async def _maybe_notify_parent(db: AsyncSession, instance: WorkflowInstance) -> None:
    """A child that reaches a TERMINAL state injects ChildCompleted at its
    parent's CALL step. Both "completed" (finished) and "cancelled" (stopped
    before finishing) are terminal arrivals — a cancelled child MUST notify the
    parent too, or an 'all' join over the children would hang forever. The parent
    may itself terminate and notify ITS parent (recursion up the chain). A stale
    parent (moved on / join already met) ignores it harmlessly."""
    if instance.status not in ("completed", "cancelled") or not instance.parent_instance_id:
        return
    try:
        await _apply_system_event(
            db, instance.parent_instance_id,
            kernel.ChildCompleted(step_id=instance.parent_step_id or "",
                                  child_ref=str(instance.id),
                                  child_terminal=instance.current_step,
                                  child_status=instance.status))
    except (ServiceError, kernel.KernelError, EngineError) as exc:
        logger.info("parent %s ignored terminal child %s (%s): %s",
                    instance.parent_instance_id, instance.id, instance.status, exc)


async def _maybe_finalize_agreement_subject(db: AsyncSession, instance: WorkflowInstance) -> None:
    """Workflow-completion → site-readiness bridge (THE documented engine↔site-readiness
    integration point). When an agreement-backed instance reaches a COMPLETED terminal
    state, run the agreements site-readiness integration so site activation gating stays
    in sync with engine-driven agreements (e.g. a CDA completing marks its
    SiteWorkflowStep.CDA_EXECUTION milestone — exactly what the legacy per-type signing
    path did). General: lazily delegates to the shared bridge, which is a safe no-op when
    the subject isn't an agreement or the type has no site milestone. A bridge failure is
    logged and swallowed — it must never roll back engine completion."""
    if instance.status != "completed" or not instance.subject_ref:
        return
    try:
        from app.models import Agreement
        agreement = await db.get(Agreement, instance.subject_ref)
        if agreement is None:
            return  # subject_ref isn't an agreement (e.g. a verify-script ref) — no-op
        from app.modules.agreements.services.site_readiness_bridge import (
            complete_site_milestone_for_executed_agreement,
        )
        await complete_site_milestone_for_executed_agreement(db, agreement, completed_by="engine")
    except Exception:  # noqa: BLE001 — the bridge must never break engine completion
        logger.exception(
            "agreement finalize bridge failed for instance %s (subject %s)",
            instance.id, instance.subject_ref,
        )


async def _execute_commands(db: AsyncSession, instance: WorkflowInstance,
                            commands: list) -> None:
    """Materialize the kernel's commands inside the CURRENT transaction. Audit
    rows are the event log — they commit (or roll back) atomically with the
    state change they record."""
    for cmd in commands:
        if isinstance(cmd, kernel.AppendAudit):
            _log(db, instance, actor=cmd.actor, action=cmd.action,
                 transition_id=cmd.transition_id, from_step=cmd.from_step,
                 to_step=cmd.to_step, comment=cmd.comment, payload=dict(cmd.payload))
        elif isinstance(cmd, kernel.PersistDeclineReason):
            await _persist_decline_reason(
                db, instance, {"branch_id": cmd.branch_id, "reason": cmd.reason}, None)
        elif isinstance(cmd, kernel.CreateTask):
            # Store a ROLE assignee_value in canonical slug form so the worklist
            # query (which compares against the user's slugged roles) matches
            # regardless of the IAM role's casing/spacing. user/context values
            # (ids/keys) are stored verbatim.
            stored_value = (role_slug(cmd.assignee_value)
                            if cmd.assignee_type == "role" else cmd.assignee_value)
            db.add(WorkflowTask(
                instance_id=instance.id, step_id=cmd.step_id, slot_id=cmd.slot_id,
                name=cmd.name, assignee_type=cmd.assignee_type,
                assignee_value=stored_value,
                resolved_user_id=cmd.resolved_user_id, status="open",
            ))
        elif isinstance(cmd, kernel.CompleteTask):
            await _close_task(db, instance.id, cmd.step_id, cmd.slot_id,
                              "completed", actor=cmd.actor)
        elif isinstance(cmd, kernel.CancelTask):
            await _close_task(db, instance.id, cmd.step_id, cmd.slot_id, "cancelled")
        elif isinstance(cmd, kernel.ArmTimer):
            # The CLOCK lives here, at the boundary — never in the kernel.
            from datetime import timedelta
            db.add(WorkflowTimer(
                instance_id=instance.id, step_id=cmd.step_id, action=cmd.action,
                fire_at=datetime.now(timezone.utc) + timedelta(seconds=cmd.seconds),
                status="pending",
            ))
        elif isinstance(cmd, kernel.CancelTimer):
            await db.execute(
                update(WorkflowTimer)
                .where(WorkflowTimer.instance_id == instance.id,
                       WorkflowTimer.step_id == cmd.step_id,
                       WorkflowTimer.status == "pending")
                .values(status="cancelled"))
        elif isinstance(cmd, kernel.InvokeJob):
            db.add(WorkflowJob(
                instance_id=instance.id, step_id=cmd.step_id, kind=cmd.kind,
                params=dict(cmd.params), status="pending",
                attempts=0, max_attempts=cmd.max_attempts,
            ))
        elif isinstance(cmd, kernel.CancelJob):
            await db.execute(
                update(WorkflowJob)
                .where(WorkflowJob.instance_id == instance.id,
                       WorkflowJob.step_id == cmd.step_id,
                       WorkflowJob.status.in_(("pending", "running")))
                .values(status="cancelled"))
        elif isinstance(cmd, kernel.SpawnChild):
            if cmd.definition_key == instance.definition_key:
                raise ServiceError(
                    f"Call step '{cmd.step_id}': a workflow cannot call itself")
            await start_instance(
                db, cmd.definition_key, dict(cmd.context),
                subject_ref=instance.subject_ref,
                parent_instance_id=instance.id, parent_step_id=cmd.step_id)
        elif isinstance(cmd, kernel.CancelChildren):
            stragglers = (await db.scalars(
                select(WorkflowInstance)
                .where(WorkflowInstance.parent_instance_id == instance.id,
                       WorkflowInstance.parent_step_id == cmd.step_id,
                       WorkflowInstance.status == "active")
            )).all()
            for child in stragglers:
                child.status = "cancelled"
                _log(db, child, actor=None, action="cancelled",
                     from_step=child.current_step, to_step=child.current_step,
                     comment="parent call step join met")
        else:  # pragma: no cover — a new command type missing its executor
            raise ServiceError(f"No executor for command {type(cmd).__name__}")


async def _close_task(db: AsyncSession, instance_id: int, step_id: str,
                      slot_id: str, status: str, actor: Optional[str] = None) -> None:
    values = {"status": status}
    if status == "completed":
        values["completed_by"] = actor
    await db.execute(
        update(WorkflowTask)
        .where(WorkflowTask.instance_id == instance_id,
               WorkflowTask.step_id == step_id,
               WorkflowTask.slot_id == slot_id,
               WorkflowTask.status.in_(("open", "claimed")))
        .values(**values)
    )


async def _persist_decline_reason(db: AsyncSession, instance: WorkflowInstance,
                                  vote: dict, comment: Optional[str]) -> None:
    """Store a signer's rejection reason WITH the agreement document, by reusing the
    existing system-comment writer (agreement_comments). Reason precedence: the
    engine-recorded vote reason, else the action comment. Best-effort: no-op when the
    subject isn't a real agreement or there's no reason — never blocks the
    (already-audited) state change."""
    reason = (vote.get("reason") or (comment or "")).strip()
    subject = instance.subject_ref
    if not reason or not subject:
        return
    from uuid import UUID as _UUID
    try:
        agreement_id = _UUID(str(subject))
    except (ValueError, TypeError):
        return  # sandbox / non-agreement subject_ref — audit row already captured it
    signer = vote.get("branch_id") or "signer"
    try:
        from app.modules.agreements.routes.crud import create_agreement_system_comment
        await create_agreement_system_comment(
            db, agreement_id, None,
            f"[SIGNATURE DECLINED] {signer} declined to sign. Reason: {reason}",
        )
    except Exception:  # noqa: BLE001 — never fail the workflow advance over the comment
        logger.warning("could not persist decline reason for instance %s", instance.id, exc_info=True)


# ---------------------------------------------------------------------------
# Discussion (NEED 1) — a tracked two-party comment exchange on a workflow step,
# stored by REUSING agreement_comments (AgreementComment). The instance's
# subject_ref IS the agreement id, so the discussion is scoped to that agreement
# and visible to both parties; rows are append-only, so they are the audit trail.
# Resolve = the normal engine advance (perform_action on the step's resolve
# transition), so the engine stays unchanged.
# ---------------------------------------------------------------------------
_PARTY_BY_COMMENT_TYPE = {"INTERNAL": "internal", "EXTERNAL": "external", "SYSTEM": "system"}


def _agreement_id_of(instance: WorkflowInstance):
    """The agreement UUID a discussion is scoped to (the instance subject_ref), or
    None when the subject isn't a real agreement (sandbox)."""
    from uuid import UUID as _UUID
    if not instance.subject_ref:
        return None
    try:
        return _UUID(str(instance.subject_ref))
    except (ValueError, TypeError):
        return None


async def list_discussion(db: AsyncSession, instance_id: int) -> list[dict]:
    """The discussion thread for an instance: the agreement's human comments
    (internal/external), oldest first, visible to BOTH parties. Read-only."""
    from app.models import AgreementComment

    instance = await get_instance(db, instance_id)
    agreement_id = _agreement_id_of(instance)
    if agreement_id is None:
        return []
    rows = (await db.scalars(
        select(AgreementComment)
        .where(AgreementComment.agreement_id == agreement_id)
        .order_by(AgreementComment.created_at, AgreementComment.id)
    )).all()
    out = []
    for c in rows:
        ctype = getattr(c.comment_type, "value", c.comment_type)
        party = _PARTY_BY_COMMENT_TYPE.get(str(ctype).upper(), "internal")
        if party == "system":
            continue  # system/audit comments aren't part of the human exchange
        out.append({"id": str(c.id), "party": party, "author": c.created_by,
                    "content": c.content, "created_at": c.created_at})
    return out


async def post_discussion(db: AsyncSession, instance_id: int, user: CurrentUser,
                          content: str, party: str = "internal") -> dict:
    """Append one comment to the discussion (reusing AgreementComment). The author is
    the current user's id; the party tags which side posted. Flushed, not committed —
    the route's transactional block commits."""
    from app.models import AgreementComment, CommentType

    if not (content and content.strip()):
        raise ServiceError("A comment is required")
    instance = await get_instance(db, instance_id)
    agreement_id = _agreement_id_of(instance)
    if agreement_id is None:
        raise ServiceError("This workflow has no agreement to attach the discussion to")
    ctype = CommentType.EXTERNAL if party == "external" else CommentType.INTERNAL
    comment = AgreementComment(
        agreement_id=agreement_id, version_id=None, comment_type=ctype,
        content=content.strip(), created_by=user.id or None,
    )
    db.add(comment)
    await db.flush()
    return {"id": str(comment.id), "party": party, "author": comment.created_by,
            "content": comment.content, "created_at": comment.created_at}


async def cancel_instance(db: AsyncSession, instance_id: int, user: CurrentUser,
                          comment: Optional[str] = None) -> WorkflowInstance:
    # Same row lock as perform_action: cancel must not race a concurrent action.
    instance = await get_instance(db, instance_id, for_update=True)
    version = await db.get(WorkflowDefinitionVersion, instance.version_id)
    state = kernel.InstanceState(instance.status, instance.current_step, instance.context)
    try:
        decision = kernel.decide(_body_of(version), state,
                                 kernel.CancelRequested(user=user, comment=comment),
                                 enforce_roles=True)
    except kernel.KernelError as exc:
        raise ServiceError(str(exc)) from exc
    instance.status = decision.state.status
    await _execute_commands(db, instance, decision.commands)
    await db.flush()
    # Cancelling a CHILD instance must resolve its parent's children-join (a
    # cancelled child is a terminal arrival), otherwise an 'all' join hangs.
    await _maybe_notify_parent(db, instance)
    return instance


# ---------------------------------------------------------------------------
# Tasks (V2 Phase 3) — the worklist read-model + lifecycle.
# Creation/completion/cancellation are kernel commands (see _execute_commands);
# claim and reassign are direct user operations, audited on the instance.
# ---------------------------------------------------------------------------
def _task_view(t: WorkflowTask, inst: WorkflowInstance) -> dict:
    return {
        "id": t.id, "instance_id": t.instance_id,
        "definition_key": inst.definition_key, "subject_ref": inst.subject_ref,
        "step_id": t.step_id, "slot_id": t.slot_id, "name": t.name,
        "status": t.status, "assignee_type": t.assignee_type,
        "assignee_value": t.assignee_value, "resolved_user_id": t.resolved_user_id,
        "claimed_by": t.claimed_by, "due_at": t.due_at, "created_at": t.created_at,
    }


def _user_is_eligible(task: WorkflowTask, user: CurrentUser) -> bool:
    if task.resolved_user_id and task.resolved_user_id == user.id:
        return True
    if task.assignee_type == "user" and task.assignee_value == user.id:
        return True
    if task.assignee_type == "role" and role_matches(task.assignee_value, user.roles):
        return True
    return False


async def list_tasks_for_user(db: AsyncSession, user: CurrentUser,
                              status: str = "open") -> list[dict]:
    """'My open steps across instances' — tasks addressed to me (direct, resolved,
    my role, or claimed by me). Always strict: a user only ever sees their own
    tasks."""
    from sqlalchemy import and_, or_

    stmt = (
        select(WorkflowTask, WorkflowInstance)
        .join(WorkflowInstance, WorkflowTask.instance_id == WorkflowInstance.id)
        .order_by(WorkflowTask.created_at, WorkflowTask.id)
    )
    if status == "open":
        stmt = stmt.where(WorkflowTask.status.in_(("open", "claimed")))
    else:
        stmt = stmt.where(WorkflowTask.status == status)
    stmt = stmt.where(or_(
        WorkflowTask.resolved_user_id == user.id,
        and_(WorkflowTask.assignee_type == "user",
             WorkflowTask.assignee_value == user.id),
        and_(WorkflowTask.assignee_type == "role",
             WorkflowTask.assignee_value.in_(
                 [role_slug(r) for r in (user.roles or [])] or [""])),
        WorkflowTask.claimed_by == user.id,
    ))
    rows = (await db.execute(stmt)).all()
    return [_task_view(t, inst) for t, inst in rows]


async def get_task(db: AsyncSession, task_id: int) -> WorkflowTask:
    task = await db.get(WorkflowTask, task_id)
    if task is None:
        raise ServiceError(f"Task {task_id} not found")
    return task


async def claim_task(db: AsyncSession, task_id: int, user: CurrentUser) -> dict:
    task = await get_task(db, task_id)
    if task.status != "open":
        raise ServiceError(f"Task is {task.status}; only open tasks can be claimed")
    if not _user_is_eligible(task, user):
        raise ServiceError("You are not eligible to claim this task")
    task.status = "claimed"
    task.claimed_by = user.id
    inst = await get_instance(db, task.instance_id)
    _log(db, inst, actor=user.id, action="task_claimed",
         from_step=task.step_id, to_step=task.step_id,
         payload={"task_id": task.id, "slot_id": task.slot_id})
    await db.flush()
    return _task_view(task, inst)


async def reassign_task(db: AsyncSession, task_id: int, user: CurrentUser,
                        new_user_id: str) -> dict:
    if not (new_user_id and new_user_id.strip()):
        raise ServiceError("A target user id is required to reassign")
    task = await get_task(db, task_id)
    if task.status not in ("open", "claimed"):
        raise ServiceError(f"Task is {task.status}; only open/claimed tasks can be reassigned")
    previous = task.resolved_user_id or task.assignee_value
    task.assignee_type = "user"
    task.assignee_value = new_user_id.strip()
    task.resolved_user_id = new_user_id.strip()
    task.status = "open"
    task.claimed_by = None
    # Make the reassignment EFFECTIVE: the engine's strict-mode authorization
    # honors context["_task_overrides"]["<step>:<slot>"] in place of the
    # definition's assignee for this one work item. Row lock — a reassign must
    # not race a concurrent action on the same instance.
    inst = await get_instance(db, task.instance_id, for_update=True)
    overrides = dict((inst.context or {}).get("_task_overrides") or {})
    overrides[f"{task.step_id}:{task.slot_id}"] = new_user_id.strip()
    inst.context = {**(inst.context or {}), "_task_overrides": overrides}
    _log(db, inst, actor=user.id, action="task_reassigned",
         from_step=task.step_id, to_step=task.step_id,
         payload={"task_id": task.id, "slot_id": task.slot_id,
                  "from": previous, "to": new_user_id.strip()})
    await db.flush()
    return _task_view(task, inst)


# ---------------------------------------------------------------------------
# Timers + Jobs (V2 Phase 4) — the scheduler and the job executor. Celery (or a
# test) calls these sweeps; each due timer / pending job becomes a system event
# routed through the same kernel.decide as every human action. The caller owns
# the commit.
# ---------------------------------------------------------------------------
async def _apply_system_event(db: AsyncSession, instance_id: int,
                              event) -> WorkflowInstance:
    """Row-locked decide/apply for system events (TimerFired / JobCompleted /
    JobFailed / message events) — the exact pipeline perform_action uses."""
    instance = await get_instance(db, instance_id, for_update=True)
    version = await db.get(WorkflowDefinitionVersion, instance.version_id)
    state = kernel.InstanceState(instance.status, instance.current_step, instance.context)
    decision = kernel.decide(_body_of(version), state, event,
                             enforce_roles=True)
    instance.current_step = decision.state.current_step
    instance.context = decision.state.context
    instance.status = decision.state.status
    await _execute_commands(db, instance, decision.commands)
    await db.flush()
    await _maybe_notify_parent(db, instance)
    await _maybe_finalize_agreement_subject(db, instance)
    return instance


async def deliver_message(db: AsyncSession, name: str, subject_ref: str,
                          payload: dict) -> dict:
    """The event router: deliver an external message to every active instance
    correlated by subject_ref that is parked on a wait_message step expecting
    this message name. Returns {"delivered": n}."""
    from .schemas import MessageConfig, StepType

    instances = (await db.scalars(
        select(WorkflowInstance)
        .where(WorkflowInstance.subject_ref == str(subject_ref),
               WorkflowInstance.status == "active")
        .order_by(WorkflowInstance.id)
    )).all()
    delivered = 0
    for inst in instances:
        version = await db.get(WorkflowDefinitionVersion, inst.version_id)
        body = _body_of(version)
        engine = WorkflowEngine(body, enforce_roles=True)
        for sid in engine.parked_steps(inst.current_step, inst.context):
            step = engine.step(sid)
            if step.type != StepType.WAIT_MESSAGE:
                continue
            cfg = MessageConfig.model_validate((step.config or {}).get("message") or {})
            if cfg.name != name:
                continue
            try:
                await _apply_system_event(
                    db, inst.id,
                    kernel.MessageReceived(step_id=sid, name=name, payload=payload))
                delivered += 1
            except (ServiceError, kernel.KernelError, EngineError) as exc:
                logger.info("message '%s' not deliverable to instance %s: %s",
                            name, inst.id, exc)
            break  # at most one delivery per instance per call
    return {"delivered": delivered}


async def run_due_timers(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """Fire every pending timer whose fire_at has passed. A timer whose step has
    already been left is marked cancelled (stale), never crashes the sweep."""
    now = now or datetime.now(timezone.utc)
    due = (await db.scalars(
        select(WorkflowTimer)
        .where(WorkflowTimer.status == "pending", WorkflowTimer.fire_at <= now)
        .order_by(WorkflowTimer.id)
    )).all()
    fired = 0
    for timer in due:
        try:
            await _apply_system_event(
                db, timer.instance_id,
                kernel.TimerFired(step_id=timer.step_id, action=timer.action))
            timer.status = "fired"
            fired += 1
        except (ServiceError, kernel.KernelError, EngineError) as exc:
            timer.status = "cancelled"
            logger.info("stale timer %s on instance %s: %s", timer.id,
                        timer.instance_id, exc)
    await db.flush()
    return fired


async def run_pending_jobs(db: AsyncSession) -> int:
    """Execute every pending job via its registered handler. Success injects
    JobCompleted (output mapped into context by the kernel); a failing handler
    retries until max_attempts, then JobFailed routes the error transition."""
    from .jobs import get_job_handler

    pending = (await db.scalars(
        select(WorkflowJob).where(WorkflowJob.status == "pending")
        .order_by(WorkflowJob.id)
    )).all()
    processed = 0
    from .jobs import KIND_NOOP

    for job in pending:
        handler = get_job_handler(job.kind)
        if handler is None:
            # Unknown/placeholder kind -> fall back to the safe noop handler so the
            # step completes harmlessly (logs + advances) instead of dead-ending the
            # whole workflow. Authored kinds are mapped to real handlers at author
            # time (generate.normalize_draft); this is the runtime safety net for
            # anything that slips through (e.g. builder-authored or legacy defs).
            handler = get_job_handler(KIND_NOOP)
            logger.warning(
                "workflow job: no handler for kind %r (instance=%s step=%s); "
                "using noop fallback", job.kind, job.instance_id, job.step_id)
        if handler is None:
            # noop somehow not registered — preserve the original permanent-fail.
            job.error = f"no handler registered for kind '{job.kind}'"
            job.attempts = job.max_attempts
            failed = True
            result: Optional[dict] = None
        else:
            job.attempts += 1
            try:
                instance = await get_instance(db, job.instance_id)
                result = await handler(dict(job.params or {}),
                                       dict(instance.context or {}))
                failed = False
            except Exception as exc:  # noqa: BLE001 — handler failures are data
                job.error = str(exc)
                failed = True
                result = None

        if not failed:
            try:
                await _apply_system_event(
                    db, job.instance_id,
                    kernel.JobCompleted(step_id=job.step_id, result=result or {}))
                job.status = "completed"
                job.result = result or {}
                processed += 1
            except (ServiceError, kernel.KernelError, EngineError) as exc:
                job.status = "cancelled"
                job.error = f"stale: {exc}"
        elif job.attempts >= job.max_attempts:
            job.status = "failed"
            try:
                await _apply_system_event(
                    db, job.instance_id,
                    kernel.JobFailed(step_id=job.step_id,
                                     error=job.error or "job failed"))
            except (ServiceError, kernel.KernelError, EngineError):
                pass  # stale; the job row carries the error
            processed += 1
        # else: stays pending — retried on the next sweep
    await db.flush()
    return processed


async def _wait_subject(db: AsyncSession, subject_ref):
    """Load the workflow subject (an Agreement) for a wait-condition checker, or None
    (non-agreement / unknown subject — checkers handle None)."""
    if not subject_ref:
        return None
    from app.models import Agreement
    try:
        return await db.get(Agreement, subject_ref)
    except Exception:  # noqa: BLE001 — non-UUID/test subject_refs match no agreement
        return None


async def run_pending_waits(db: AsyncSession) -> int:
    """Re-check every PARKED wait_condition step against its registered checker and
    release the ones whose condition is now true (auto-resume). Mirrors run_due_timers,
    but the 'is it due?' predicate is a PLUGGABLE checker (waits._WAIT_CONDITIONS)
    evaluated against live data — so a workflow holds until e.g. the budget is finalized,
    then continues automatically on the sweep.

    Safety: a checker that raises, or a condition with NO registered checker, leaves the
    step PARKED (never a silent advance) and logs — it does not crash the sweep. An
    unknown condition is an ERROR-level log (a misconfiguration to fix); the workflow
    holds rather than sailing through an unverifiable gate."""
    from .schemas import StepType, WaitConfig
    from .waits import get_condition_checker

    insts = (await db.scalars(
        select(WorkflowInstance).where(WorkflowInstance.status == "active")
    )).all()
    advanced = 0
    body_cache: dict = {}
    for inst in insts:
        if not inst.current_step:
            continue
        body = body_cache.get(inst.version_id)
        if body is None:
            version = await db.get(WorkflowDefinitionVersion, inst.version_id)
            if version is None:
                continue
            body = _body_of(version)
            body_cache[inst.version_id] = body
        steps_by_id = {s.id: s for s in body.steps}
        engine = WorkflowEngine(body, enforce_roles=True)
        for sid in engine.parked_steps(inst.current_step, inst.context or {}):
            step = steps_by_id.get(sid)
            if step is None or step.type != StepType.WAIT_CONDITION:
                continue
            wc = WaitConfig.model_validate((step.config or {}).get("wait") or {})
            checker = get_condition_checker(wc.condition)
            if checker is None:
                logger.error("run_pending_waits: wait_condition step '%s' (instance %s) uses "
                             "UNKNOWN condition %r — holding (register it or fix the definition)",
                             sid, inst.id, wc.condition)
                continue
            subject = await _wait_subject(db, inst.subject_ref)
            try:
                ready = bool(await checker(subject, dict(wc.params or {}), db))
            except Exception:  # noqa: BLE001 — a checker error must not crash the sweep
                logger.exception("run_pending_waits: condition %r raised (instance %s) — holding",
                                 wc.condition, inst.id)
                ready = False
            if not ready:
                continue
            try:
                await _apply_system_event(db, inst.id, kernel.ConditionMet(step_id=sid))
                advanced += 1
            except (ServiceError, kernel.KernelError, EngineError) as exc:
                logger.info("run_pending_waits: instance %s step %s not advanced (%s)",
                            inst.id, sid, exc)
    await db.flush()
    return advanced


async def run_sweeps_once(db: AsyncSession) -> dict:
    """Run the timer + job + wait-condition sweeps once. The single entry point shared
    by the dev /run-sweeps endpoint AND the dev background sweeper loop, so both behave
    identically. Production uses the Celery beat tasks instead."""
    fired = await run_due_timers(db)
    processed = await run_pending_jobs(db)
    waits = await run_pending_waits(db)
    return {"timers_fired": fired, "jobs_processed": processed, "waits_advanced": waits}


# ---------------------------------------------------------------------------
# Read models for the runner UI (V2): job/timer activity + child instances.
# ---------------------------------------------------------------------------
def _job_view(j: WorkflowJob) -> dict:
    # `result` is included so the job panel can distinguish a genuine completion
    # from a DEGRADED one (e.g. generate_document with no PDF backend returns
    # {generated: False, reason: ...}); the panel surfaces that instead of a
    # silent "completed".
    return {"id": j.id, "step_id": j.step_id, "kind": j.kind, "status": j.status,
            "attempts": j.attempts, "max_attempts": j.max_attempts, "error": j.error,
            "result": j.result if isinstance(j.result, dict) else None,
            "created_at": j.created_at, "updated_at": j.updated_at}


async def list_activity(db: AsyncSession, instance_id: int) -> dict:
    """Read-only: this instance's job executions + boundary timers (the runner's
    job panel and armed-timer indicator)."""
    await get_instance(db, instance_id)  # clean 404 for unknown ids
    jobs = (await db.scalars(
        select(WorkflowJob).where(WorkflowJob.instance_id == instance_id)
        .order_by(WorkflowJob.id))).all()
    timers = (await db.scalars(
        select(WorkflowTimer).where(WorkflowTimer.instance_id == instance_id)
        .order_by(WorkflowTimer.id))).all()
    return {
        "jobs": [_job_view(j) for j in jobs],
        "timers": [{"id": t.id, "step_id": t.step_id, "action": t.action,
                    "fire_at": t.fire_at, "status": t.status} for t in timers],
    }


async def retry_job(db: AsyncSession, instance_id: int, job_id: int,
                    user: CurrentUser) -> dict:
    """Reset a FAILED job to pending so the next sweep re-runs it. Audited."""
    job = await db.get(WorkflowJob, job_id)
    if job is None or job.instance_id != instance_id:
        raise ServiceError(f"Job {job_id} not found")
    if job.status != "failed":
        raise ServiceError(f"Job is {job.status}; only failed jobs can be retried")
    job.status = "pending"
    job.attempts = 0
    job.error = None
    inst = await get_instance(db, instance_id)
    _log(db, inst, actor=user.id, action="job_retry",
         from_step=job.step_id, to_step=job.step_id, payload={"job_id": job.id})
    await db.flush()
    return _job_view(job)


async def list_children(db: AsyncSession, instance_id: int) -> list[dict]:
    """Read-only: the child instances this parent's call steps spawned —
    including cancelled ones, so a stuck parent is diagnosable."""
    await get_instance(db, instance_id)
    children = (await db.scalars(
        select(WorkflowInstance)
        .where(WorkflowInstance.parent_instance_id == instance_id)
        .order_by(WorkflowInstance.id))).all()
    return [{"id": c.id, "definition_key": c.definition_key, "status": c.status,
             "current_step": c.current_step, "parent_step_id": c.parent_step_id,
             "created_at": c.created_at} for c in children]


async def get_audit_entries(db: AsyncSession, instance_id: int) -> list[WorkflowAuditEntry]:
    """Full audit trail for an instance, oldest first. Explicit query so we never
    touch the (lazy) ``instance.audit_entries`` relationship under async."""
    # Validate the instance exists so callers get a clean 404.
    await get_instance(db, instance_id)
    result = await db.scalars(
        select(WorkflowAuditEntry)
        .where(WorkflowAuditEntry.instance_id == instance_id)
        .order_by(WorkflowAuditEntry.created_at, WorkflowAuditEntry.id)
    )
    return list(result.all())


async def _actor_display_map(db: AsyncSession, actors: set[Optional[str]]) -> dict[str, str]:
    """Map a stored audit actor (an external user_id / local user id) to a
    human-readable email or name. Actors that are already an email — or None
    (system) — are left for the caller to handle. Looks the id up by BOTH
    users.user_id (the IAM id we store as the actor) and users.id (defensive).
    Read-only; the stored audit value is never changed."""
    ids = {a for a in actors if a and "@" not in a}
    if not ids:
        return {}
    from sqlalchemy import bindparam, text

    rows = (await db.execute(
        text("SELECT user_id::text AS uid, id::text AS lid, email, name FROM users "
             "WHERE user_id::text IN :ids OR id::text IN :ids2")
        .bindparams(bindparam("ids", expanding=True), bindparam("ids2", expanding=True)),
        {"ids": list(ids), "ids2": list(ids)},
    )).mappings().all()
    out: dict[str, str] = {}
    for r in rows:
        display = r["email"] or r["name"]
        if not display:
            continue
        if r["uid"]:
            out[r["uid"]] = display
        if r["lid"]:
            out[r["lid"]] = display
    return out


async def get_audit_view(db: AsyncSession, instance_id: int) -> list[dict]:
    """Audit trail for display: same rows as get_audit_entries, but each `actor`
    resolved to a human-readable email/name (the stored DB value — the canonical
    acting user id, retained for 21 CFR — is untouched). Actors already stored as an
    email pass through; None stays None so the UI renders 'system'. An id that can't be
    resolved is left as-is (never invented)."""
    entries = await get_audit_entries(db, instance_id)
    display = await _actor_display_map(db, {e.actor for e in entries})
    view: list[dict] = []
    for e in entries:
        actor = e.actor
        if actor and "@" not in actor:
            actor = display.get(actor, actor)
        view.append({
            "id": e.id, "actor": actor, "action": e.action,
            "from_step": e.from_step, "to_step": e.to_step,
            "comment": e.comment, "created_at": e.created_at,
        })
    return view


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
async def _engine_for(db: AsyncSession, instance: WorkflowInstance) -> WorkflowEngine:
    version = await db.get(WorkflowDefinitionVersion, instance.version_id)
    return WorkflowEngine(_body_of(version), enforce_roles=True)


def _log(db: AsyncSession, instance: WorkflowInstance, *, actor, action,
         transition_id=None, from_step=None, to_step=None, comment=None, payload=None):
    """Stage an audit row. ``db.add`` is synchronous even on an AsyncSession;
    the surrounding flush/commit persists it."""
    db.add(
        WorkflowAuditEntry(
            instance_id=instance.id,
            actor=actor,
            action=action,
            transition_id=transition_id,
            from_step=from_step,
            to_step=to_step,
            comment=comment,
            payload=payload or {},
        )
    )

"""
unified_review.py — the UNIFIED review/comment module backend (behind WORKFLOW_UNIFIED).

Drives the review cycle on the generic engine:
  owner sends to a reviewer -> reviewer reviews + comments in OnlyOffice ->
  reviewer APPROVES (engine takes the forward exit) or SENDS BACK (engine loops to
  the edit/draft step) -> owner revises + re-sends -> repeat until approved.

HARVEST (reuse, not reinvent):
  * dispatch = call the EXISTING send_agreement_for_review route fn (token + review
    copy + email + UNDER_REVIEW) verbatim — no replication, no edit to it;
  * reviewer reviews/comments via the EXISTING public review page + comment endpoints;
  * the ENGINE owns the rework loop (approval step: approve -> forward, send_back ->
    edit). This service advances the step ONLY on the reviewer's real recorded
    response (approve / send_back), never a bare owner button.

The live review path (send-for-review / submit-review / changes) is untouched and
remains the fallback. Reachable only when WORKFLOW_UNIFIED is on (routes enforce it).
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Agreement, AgreementReviewToken, AgreementReviewDocument, AgreementDocument

logger = logging.getLogger(__name__)

_APPROVE_ACTIONS = {"approve"}
_SEND_BACK_ACTIONS = {"send_back", "reject"}

# Parallel review: reviewers are the step's ACTION branches. Reviews carry no DB
# branch column, so the per-branch email + token->branch mapping lives in the
# instance context (JSON, no migration), mirroring signing's _SIGNER_EMAILS_KEY.
_REVIEW_EMAILS_KEY = "_reviewer_emails"        # {branch_id: email}
_REVIEW_TOKEN_BRANCH_KEY = "_review_token_branch"  # {token: branch_id}
_REVIEW_TOKEN_TTL_DAYS = 14

# Engine reassignment override. Mirrors app.modules.workflows.engine._OVERRIDES_KEY
# and _reassigned_to's "<step_id>:<slot_id>" slot key. An external reviewer is
# authenticated by their review TOKEN, not by an IAM role, so the engine's strict
# (always-on) role check rejects them on an approval step whose assignee is a role
# (or None). Binding that step's work item to the reviewer's email via this override
# makes BOTH the action lookup and perform_action admit the token-authenticated
# reviewer — without weakening role enforcement for anyone else.
_TASK_OVERRIDES_KEY = "_task_overrides"


def _override_slot(step_id: str, slot_id: str = "") -> str:
    return f"{step_id}:{slot_id or ''}"


def _bind_reviewer_override(instance, step_id: str, reviewer_email: str,
                            slot_id: str = "") -> bool:
    """Reassign one approval work item (a step, or step+branch for parallel) to the
    reviewer's email so the engine's strict authorization admits them. Returns True
    when the override changed (the caller flushes / commits)."""
    email = (reviewer_email or "").strip()
    if not email:
        return False
    overrides = dict((instance.context or {}).get(_TASK_OVERRIDES_KEY) or {})
    slot = _override_slot(step_id, slot_id)
    if overrides.get(slot) == email:
        return False
    overrides[slot] = email
    instance.context = {**(instance.context or {}), _TASK_OVERRIDES_KEY: overrides}
    return True


def _approval_capabilities(step, context: dict) -> tuple[bool, bool]:
    """(can_approve, can_send_back) read straight off an approval step's declared
    transitions. Token-gated callers don't pass through role-filtered
    available_actions, so we mirror the engine's _step_available_actions filtering
    here: skip 'auto' transitions and respect transition conditions."""
    from app.modules.workflows.conditions import evaluate_condition
    approve = send_back = False
    for t in (getattr(step, "transitions", None) or []):
        if t.action == "auto":
            continue
        if not evaluate_condition(getattr(t, "condition", None), context):
            continue
        if t.action in _APPROVE_ACTIONS:
            approve = True
        elif t.action in _SEND_BACK_ACTIONS:
            send_back = True
    return approve, send_back


# ---------------------------------------------------------------------------
# DISPATCH (owner): reuse the existing send-for-review verbatim.
# ---------------------------------------------------------------------------
async def dispatch(db: AsyncSession, agreement_id: str, recipient_email: str,
                   message: Optional[str], current_user: dict) -> dict:
    """Owner action (creator-owns): send the document to a reviewer. Delegates to the
    proven send_agreement_for_review (token + review copy + email + status) — full reuse."""
    from app.modules.agreements.routes.signing import send_agreement_for_review

    result = await send_agreement_for_review(
        agreement_id,  # type: ignore[arg-type]
        recipient_email=recipient_email,
        message=message,
        current_user=current_user,
        db=db,
        origin=None,
        referer=None,
    )
    return {"status": "sent", "review": result}


# ---------------------------------------------------------------------------
# Engine glue — find the review (approval) step + its approve/send_back actions.
# ---------------------------------------------------------------------------
def _pick(acts, names: set[str]):
    return next((a for a in acts if a.action in names), None)


async def _active_review_token(db: AsyncSession, agreement_id, token: str) -> AgreementReviewToken:
    row = await db.scalar(
        select(AgreementReviewToken)
        .where(AgreementReviewToken.agreement_id == agreement_id)
        .where(AgreementReviewToken.token == token)
        .where(AgreementReviewToken.is_active == "true")
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive review link.")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Review link expired.")
    return row


# ===========================================================================
# PARALLEL multi-reviewer review (type=parallel, module=review). Mirrors the
# unified signing module's per-slot model: each ACTION branch is one reviewer; the
# owner dispatches a secure review link per reviewer; each reviewer approves or
# sends-back on that link; the ENGINE advances on quorum (all approve) or loops to
# edit on a send-back (quorum_failed). Single-reviewer review is unchanged.
# ===========================================================================
async def _instance_step(db: AsyncSession, agreement_id: str):
    """Resolve (instance, current Step) for an agreement, or (None, None)."""
    from app.modules.workflows import service as wf
    from app.modules.workflows.models import WorkflowDefinitionVersion
    from app.modules.workflows.schemas import WorkflowDefinitionBody

    inst = await wf.find_instance_by_subject(db, str(agreement_id))
    if inst is None or not inst.current_step:
        return None, None
    version = await db.get(WorkflowDefinitionVersion, inst.version_id)
    body = WorkflowDefinitionBody.model_validate(version.body)
    step = next((s for s in body.steps if s.id == inst.current_step), None)
    return inst, step


def _is_parallel_review_step(step) -> bool:
    return step is not None and getattr(step.type, "value", str(step.type)) == "parallel"


def _action_branches(step) -> list[dict]:
    """Reviewer branches = the parallel step's kind='action' branches (notify-only
    branches are informational, never reviewers)."""
    cfg = step.config or {}
    out = []
    for b in cfg.get("branches") or []:
        if (b.get("kind") or "action") != "action":
            continue
        out.append({"id": str(b.get("id")), "name": str(b.get("name") or b.get("id"))})
    return out


def _branch_decisions(instance, step_id: str) -> dict:
    """{branch_id: 'approve'|'reject'} recorded by the engine for this step."""
    branches = (instance.context or {}).get("_branches") or {}
    votes = branches.get(step_id) or {}
    return {bid: (v or {}).get("decision") for bid, v in votes.items()}


def _open_action_branches(step, instance) -> list[dict]:
    decided = set(_branch_decisions(instance, step.id).keys())
    return [b for b in _action_branches(step) if b["id"] not in decided]


def _branch_for_token(instance, token: str) -> Optional[str]:
    return ((instance.context or {}).get(_REVIEW_TOKEN_BRANCH_KEY) or {}).get(token)


async def _email_review_link(agreement: Agreement, email: str, token: str, reviewer_name: str) -> None:
    base = (settings.frontend_base_url or "").rstrip("/")
    link = f"{base}/agreement/review/{agreement.id}?token={token}"
    from app.integrations.smtp_service import enqueue_email
    try:
        enqueue_email(
            to=email,
            subject=f"Review requested: {agreement.title}",
            body=(f"You are requested to review '{agreement.title}' as {reviewer_name}.\n\n"
                  f"Open the secure review page: {link}\n\n"
                  f"You can comment, then Approve or Send back for edits."),
            from_email=getattr(settings, "smtp_user", "noreply@crm.local"),
            from_name="Clinical Trials CRM",
        )
    except Exception:  # noqa: BLE001 — email is best-effort, never block dispatch
        logger.exception("unified_review: failed to enqueue review link for %s", email)


async def parallel_status(db: AsyncSession, agreement_id: str) -> dict:
    """Per-reviewer status for a parallel review step (owner panel). Returns
    {step, type, quorum, reviewers:[{id,name,state,email}]}. `active` is False when
    the current step is not a parallel review step (the FE then uses the single UI)."""
    inst, step = await _instance_step(db, str(agreement_id))
    if not _is_parallel_review_step(step):
        return {"active": False, "reviewers": []}
    decisions = _branch_decisions(inst, step.id)
    open_ids = {b["id"] for b in _open_action_branches(step, inst)}
    emails = (inst.context or {}).get(_REVIEW_EMAILS_KEY) or {}
    reviewers = []
    for b in _action_branches(step):
        d = decisions.get(b["id"])
        state = "approved" if d == "approve" else ("sent_back" if d == "reject" else
                ("open" if b["id"] in open_ids else "pending"))
        reviewers.append({"id": b["id"], "name": b["name"], "state": state, "email": emails.get(b["id"])})
    quorum = (step.config or {}).get("quorum") or {"mode": "all"}
    return {"active": True, "step": step.id, "type": "parallel", "quorum": quorum, "reviewers": reviewers}


async def parallel_dispatch(db: AsyncSession, agreement: Agreement, recipients: dict,
                            current_user: Optional[dict] = None) -> dict:
    """Owner action: dispatch the secure review link to each OPEN reviewer branch.

    For each branch we REUSE the proven ``send_agreement_for_review`` (the same one the
    single-reviewer path uses) so each reviewer gets the full, page-compatible review:
    the agreement is moved to UNDER_REVIEW and a per-token review COPY
    (AgreementReviewDocument) is created — without which the public review page rejects
    the link as "no longer available for review". We map each returned token to its
    branch in the instance context so the reviewer's response advances only THAT branch.
    `recipients` = {branch_id: email}. send_agreement_for_review allows re-sends from
    DRAFT or UNDER_REVIEW and does not deactivate other branches' tokens."""
    from app.modules.agreements.routes.signing import send_agreement_for_review

    inst, step = await _instance_step(db, str(agreement.id))
    if not _is_parallel_review_step(step):
        raise HTTPException(status_code=409, detail="Agreement is not at a parallel review step.")
    current_user = current_user or {}

    ctx = dict(inst.context or {})
    emails = dict(ctx.get(_REVIEW_EMAILS_KEY) or {})
    tok_branch = dict(ctx.get(_REVIEW_TOKEN_BRANCH_KEY) or {})
    overrides = dict(ctx.get(_TASK_OVERRIDES_KEY) or {})
    emails.update({str(k): str(v).strip() for k, v in (recipients or {}).items() if v})

    # branches that already have an ACTIVE, unexpired mapped token -> don't re-dispatch
    active_branches = set()
    for tok, bid in tok_branch.items():
        row = await db.scalar(
            select(AgreementReviewToken)
            .where(AgreementReviewToken.agreement_id == agreement.id)
            .where(AgreementReviewToken.token == tok)
            .where(AgreementReviewToken.is_active == "true")
            .where(AgreementReviewToken.expires_at > datetime.now(timezone.utc))
        )
        if row is not None:
            active_branches.add(bid)

    dispatched = []
    for branch_id, b in {bb["id"]: bb for bb in _open_action_branches(step, inst)}.items():
        email = emails.get(branch_id)
        if not email:
            continue
        # Bind this branch's work item to its reviewer so strict authorization admits
        # the token reviewer when they approve / send-back on their secure link.
        overrides[_override_slot(step.id, branch_id)] = email
        if branch_id in active_branches:
            dispatched.append({"branch": branch_id, "email": email, "status": "already_sent"})
            continue
        # Reuse the full single-review dispatch (sets UNDER_REVIEW + makes the review
        # copy + token + email). It manages its own commit.
        result = await send_agreement_for_review(
            agreement.id, recipient_email=email, message=None,
            current_user=current_user, db=db, origin=None, referer=None)
        token_value = (result or {}).get("token")
        if token_value:
            tok_branch[token_value] = branch_id
        dispatched.append({"branch": branch_id, "email": email, "status": "sent"})

    # Persist the branch<->email + token<->branch maps on the instance. (Own commit —
    # send_agreement_for_review already committed each branch; this saves the maps.)
    ctx[_REVIEW_EMAILS_KEY] = emails
    ctx[_REVIEW_TOKEN_BRANCH_KEY] = tok_branch
    ctx[_TASK_OVERRIDES_KEY] = overrides
    inst.context = ctx
    await db.commit()
    return {"dispatched": dispatched}


# ---------------------------------------------------------------------------
# CONTEXT (reviewer, token): does the unified review apply here + what's allowed?
# ---------------------------------------------------------------------------
async def context(db: AsyncSession, agreement_id: str, token: str) -> dict:
    """Token-gated: tells the reused review page whether to show the unified
    Approve / Send-back actions. Works for BOTH single review (approval step) and
    PARALLEL review (this token's branch must still be open)."""
    try:
        tok = await _active_review_token(db, agreement_id, token)
    except HTTPException:
        return {"active": False}

    inst, step = await _instance_step(db, agreement_id)
    if _is_parallel_review_step(step):
        # Parallel: this reviewer may act only on THEIR branch, and only if it's open.
        branch_id = _branch_for_token(inst, token)
        open_ids = {b["id"] for b in _open_action_branches(step, inst)}
        active = bool(branch_id and branch_id in open_ids)
        return {"active": active, "can_approve": active, "can_send_back": active}

    # SINGLE review: the reviewer holds a valid review TOKEN (validated above) but
    # no IAM role, so authorize the read straight off the current approval step's
    # declared transitions rather than the role-filtered available_actions — which
    # would hide the actions and make the Approve / Send-back buttons disappear.
    # respond() binds the step to this reviewer when they actually act.
    if inst is None or step is None:
        return {"active": False}
    can_approve, can_send_back = _approval_capabilities(step, inst.context or {})
    return {"active": can_approve or can_send_back,
            "can_approve": can_approve, "can_send_back": can_send_back}


# ---------------------------------------------------------------------------
# RESPOND (reviewer, token): the real recorded response advances the engine.
# ---------------------------------------------------------------------------
async def respond(db: AsyncSession, agreement_id: str, token: str, decision: str) -> dict:
    """Reviewer's real response: 'approve' -> engine forward exit; 'send_back' ->
    engine loop-to-edit exit. Advances the engine ONLY here (never an owner button).
    Deactivates the review token so a new round gets a fresh link on re-dispatch."""
    from app.modules.workflows import service as wf
    from app.modules.workflows.schemas import CurrentUser

    agreement = await db.get(Agreement, agreement_id)
    if agreement is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    tok = await _active_review_token(db, agreement.id, token)

    decision = (decision or "").lower()
    if decision not in ("approve", "send_back"):
        raise HTTPException(status_code=400, detail="decision must be 'approve' or 'send_back'.")

    inst, step = await _instance_step(db, str(agreement.id))
    if inst is None:
        raise HTTPException(status_code=409, detail="No active workflow instance for this agreement.")

    if _is_parallel_review_step(step):
        # PARALLEL: act ONLY on this token's own branch (a reviewer can't vote another
        # reviewer's branch). The engine records the branch vote and settles quorum
        # (all approve -> advance; any send-back -> quorum_failed -> back to edit).
        branch_id = _branch_for_token(inst, token)
        if not branch_id:
            raise HTTPException(status_code=409, detail="This review link is not active for the current step.")
        # Bind THIS reviewer to THIS branch (self-heals reviews dispatched before the
        # override was written) so strict authorization admits the token reviewer.
        _bind_reviewer_override(inst, step.id, tok.recipient_email, slot_id=branch_id)
        await db.flush()
        acts = await wf.available_actions(db, inst.id, CurrentUser(id=tok.recipient_email, roles=[]))
        want = _APPROVE_ACTIONS if decision == "approve" else _SEND_BACK_ACTIONS
        action = next((a for a in acts if a.transition_id.startswith(f"{branch_id}:") and a.action in want), None)
        if action is None:
            raise HTTPException(status_code=409, detail="This reviewer has already responded, or the step has moved on.")
    else:
        # SINGLE review: bind this approval step to the token reviewer (strict role
        # enforcement has no IAM role to match for an external reviewer), then
        # resolve the approve / send_back transition the engine now offers.
        if step is None:
            raise HTTPException(status_code=409, detail="No active review step for this agreement.")
        _bind_reviewer_override(inst, step.id, tok.recipient_email)
        await db.flush()
        acts = await wf.available_actions(db, inst.id, CurrentUser(id=tok.recipient_email, roles=[]))
        action = _pick(acts, _APPROVE_ACTIONS if decision == "approve" else _SEND_BACK_ACTIONS)
        if action is None:
            raise HTTPException(status_code=409, detail=f"No '{decision}' transition available on this step.")

    # AUTHORITATIVE comment persistence (no longer a client-side race). The reviewer's
    # substantive feedback lives in the OnlyOffice document comments. Previously this
    # relied on a fire-and-forget save + a 4s client timer firing BEFORE this call, so a
    # send_back/approve could flip workflow status while the comments were silently
    # dropped (OO status=4 / slow callback). Now we force-save the OO session and upsert
    # the comments HERE, in THIS transaction, so comments + the status change commit
    # atomically below. General across review types and reviewer counts.
    review_doc = (await db.execute(
        select(AgreementReviewDocument)
        .where(AgreementReviewDocument.review_token_id == tok.id)
        .where(AgreementReviewDocument.is_submitted == "false")
        .order_by(AgreementReviewDocument.created_at.desc())
    )).scalars().first()
    if review_doc is not None:
        from app.modules.agreements.routes.signing import persist_review_comments_now
        await persist_review_comments_now(db, agreement, review_doc, commit=False)
    else:
        logger.info("respond(): no active review document for token %s — no document "
                    "comments to persist for this round", tok.id)

    # SEND BACK -> promote the reviewed copy (which now carries the reviewer's OnlyOffice
    # comments) to a NEW main document version. The owner's editor serves the latest main
    # document, so it now opens WITH the comments shown natively in OnlyOffice — where the
    # owner Accepts (edit + resolve) or Rejects (reply with a reason). Comments are no
    # longer stripped on re-send, so those reasons travel back to the reviewer next round.
    # (Comment-only review changes no text, so the promoted version == base content + the
    # comment thread.) Best-effort: a promotion failure must not block the send-back.
    if decision == "send_back" and review_doc is not None:
        try:
            await _promote_reviewed_copy_to_version(db, agreement, review_doc, by=tok.recipient_email)
        except Exception:  # noqa: BLE001
            logger.exception("respond(): failed to promote reviewed copy with comments for %s", agreement.id)

    # Supply a transition comment so the engine's `requires_comment` gate on a
    # send_back/approve transition is satisfied — without it, a review step authored
    # with requires_comment=True (the generator default for send_back) would reject the
    # action with "A comment is required for this action".
    engine_comment = ("Returned for revision with the reviewer's document comments."
                      if decision == "send_back"
                      else "Approved by the reviewer.")
    await wf.perform_action(
        db, inst.id, CurrentUser(id=tok.recipient_email, roles=[]),
        action.transition_id, {"reviewer": tok.recipient_email, "decision": decision},
        comment=engine_comment,
        trusted_payload=True,  # internal bookkeeping keys, not client input
    )
    tok.is_active = "false"  # round consumed; re-dispatch issues a fresh link
    await db.commit()
    return {"status": decision, "transition": action.transition_id}


async def _promote_reviewed_copy_to_version(db, agreement, review_doc, by=None):
    """Create a new main AgreementDocument version FROM the reviewed copy (which carries
    the reviewer's OnlyOffice comment thread), so the owner's editor — which serves the
    latest main document — opens the doc WITH the comments. Copies the reviewed DOCX to a
    versioned ``agreements/.../_vNNN_`` blob so _latest_agreement_document ranks it latest.
    Reuses document_versioning + the blob helpers; flushes (the caller owns the commit).
    Avoids lazy relationship access (async-session safe) by querying by id."""
    import io
    from pathlib import Path as _Path
    from app.models import Study, Site
    from app.modules.agreements.services import document_versioning
    from app.modules.agreements.blob_names import _build_pretty_document_blob_name
    from app.utils.azure_storage import get_document_storage

    rfp = review_doc.review_file_path or ""
    storage = get_document_storage()
    data = None
    if storage and rfp.startswith("agreement_reviews/"):
        data = await storage.download_file(rfp)
    elif rfp and _Path(rfp).exists():
        data = _Path(rfp).read_bytes()
    if not data:
        logger.warning("respond(): no reviewed-copy bytes to promote (path=%r)", rfp)
        return

    next_ver = await document_versioning.next_version_number(db, agreement.id)
    study = await db.get(Study, agreement.study_id) if agreement.study_id else None
    site = await db.get(Site, agreement.site_id) if agreement.site_id else None
    file_path, file_url = rfp, None
    if storage:
        blob = _build_pretty_document_blob_name(
            study_name=(study.name if study else str(agreement.study_id)),
            site_name=((site.name or site.site_id) if site else str(agreement.site_id)),
            agreement_title=agreement.title, seq=next_ver,
        )
        file_url = await storage.upload_file(
            io.BytesIO(data), blob,
            content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            overwrite=False,
        )
        file_path = blob

    template_id = None
    if review_doc.base_version_id:
        base = await db.get(AgreementDocument, review_doc.base_version_id)
        template_id = getattr(base, "created_from_template_id", None) if base else None

    await document_versioning.add_document_version(
        db, agreement.id, file_path, created_by=by, document_file_url=file_url, template_id=template_id,
    )
    logger.info("respond(): promoted reviewed copy (with comments) to v%s for agreement %s",
                next_ver, agreement.id)


# ---------------------------------------------------------------------------
# STATUS (owner panel): current step + whether a review is out + the reviewer.
# ---------------------------------------------------------------------------
async def status(db: AsyncSession, agreement_id: str) -> dict:
    from app.modules.workflows import service as wf

    inst = await wf.find_instance_by_subject(db, str(agreement_id))
    current_step = inst.current_step if inst else None
    active = await db.scalar(
        select(AgreementReviewToken)
        .where(AgreementReviewToken.agreement_id == agreement_id)
        .where(AgreementReviewToken.is_active == "true")
        .order_by(AgreementReviewToken.created_at.desc())
    )
    return {
        "current_step": current_step,
        "review_out": bool(active and active.expires_at > datetime.now(timezone.utc)),
        "reviewer_email": active.recipient_email if active else None,
    }

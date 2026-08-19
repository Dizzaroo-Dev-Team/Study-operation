"""
unified_signing.py — the UNIFIED signing module's backend (Phase 2).

ONE compliant signing path any document uses, behind WORKFLOW_UNIFIED. It HARVESTS
the proven pieces (it does not reinvent them) and fixes the 21 CFR Part 11 gaps the
inventory found so they can't recur:

  * OTP core reused from otp.py: hashed OTP, 5-min expiry, **5-attempt lockout (429)**,
    constant-time compare, resend cooldown, prior-OTP invalidation.
  * Manifestation reused from signature_image + pdf_export: every signer's
    name/date/meaning is RENDERED onto the final PDF (fixes the CTA §11.50 gap —
    typed-name signers get a visible block too).
  * Hash of the FINAL produced artifact bytes (not the pre-sign source; no synthetic
    fallback) -> AgreementInternalSignature.document_hash.
  * EVERY failed OTP attempt audited (AuditLog SIGN_OTP_FAILED).
  * Signer-affirmed meaning captured and persisted.
  * Order / quorum / handoff owned by the ENGINE (ordered_signing / parallel); this
    service advances the slot ONLY on a real recorded signature.

The live CDA (otp.py) and CTA (cta/routes.py) signing paths are NOT touched — they
remain the fallback. All functions here are reachable only when WORKFLOW_UNIFIED is
on (the routes enforce that).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import (
    Agreement,
    AgreementDocument,
    AgreementInternalSignature,
    AgreementSignedDocument,
    AgreementSigningOtp,
    AgreementSigningToken,
    AuditLog,
)
# Shared document-capability services (the DOCUMENT batch) — same proven logic,
# factored out so signing and other flows share it.
from app.modules.agreements.services import doc_convert, document_versioning, signature_render

logger = logging.getLogger(__name__)

# Reuse the compliant OTP constants from the proven path.
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 30

DEFAULT_MEANING = "Signed & Approved"
_SIGNER_EMAILS_KEY = "_signer_emails"  # reserved context key: {slot_id: email}

# Engine reassignment override (mirrors app.modules.workflows.engine._OVERRIDES_KEY
# and _reassigned_to's "<step_id>:<slot_id>" slot key). A signer is authenticated by
# their signing TOKEN, not an IAM role, so the engine's strict (always-on) check
# rejects them on a slot whose assignee is a role (or None). Binding that slot's work
# item to the signer's email admits the token signer — same pattern as unified_review.
_TASK_OVERRIDES_KEY = "_task_overrides"


def _make_named_tempfile(suffix: str, data: Optional[bytes] = None):
    """Create a NamedTemporaryFile(delete=False) with ``suffix``, optionally
    write ``data`` into it, and return the (closed) tempfile object — callers
    rely on its full-path ``.name``. Sync on purpose — call via
    ``asyncio.to_thread`` from async code so the blocking file I/O stays off
    the event loop."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        if data is not None:
            tmp.write(data)
    finally:
        tmp.close()
    return tmp


def _bind_signer_override(instance, step_id: str, slot_id: str, signer_email: str) -> bool:
    """Reassign one signing slot's work item to the signer's email so strict
    authorization admits the token signer. Returns True when the override changed
    (the caller flushes / commits)."""
    email = (signer_email or "").strip()
    if not email:
        return False
    overrides = dict((instance.context or {}).get(_TASK_OVERRIDES_KEY) or {})
    slot = f"{step_id}:{slot_id}"
    if overrides.get(slot) == email:
        return False
    overrides[slot] = email
    instance.context = {**(instance.context or {}), _TASK_OVERRIDES_KEY: overrides}
    return True


def _hash_otp_value(otp: str) -> str:
    """Harvested from otp.py: SHA-256 hex of the OTP (stored, never the plaintext)."""
    return hashlib.sha256((otp or "").strip().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Engine glue — the engine owns order/quorum; we read slots + advance one slot.
# ---------------------------------------------------------------------------
async def _instance_and_step(db: AsyncSession, agreement_id: str):
    """Resolve the agreement's workflow instance and its CURRENT signing step
    (must be ordered_signing | parallel). Returns (instance, body, step) or raises."""
    from app.modules.workflows import service as wf
    from app.modules.workflows.models import WorkflowDefinitionVersion
    from app.modules.workflows.schemas import WorkflowDefinitionBody

    inst = await wf.find_instance_by_subject(db, str(agreement_id))
    if inst is None or not inst.current_step:
        raise HTTPException(status_code=409, detail="No active workflow instance for this agreement.")
    version = await db.get(WorkflowDefinitionVersion, inst.version_id)
    body = WorkflowDefinitionBody.model_validate(version.body)
    step = next((s for s in body.steps if s.id == inst.current_step), None)
    if step is None or step.type not in ("ordered_signing", "parallel"):
        raise HTTPException(status_code=409, detail="Agreement is not at a signing step.")
    return inst, body, step


def _signers(step) -> list[dict]:
    cfg = step.config or {}
    raw = cfg.get("signers") if step.type == "ordered_signing" else cfg.get("branches")
    out = []
    for b in raw or []:
        out.append({"id": str(b.get("id")), "name": str(b.get("name") or b.get("id"))})
    return out


def _signed_slot_ids(instance, step_id: str) -> set[str]:
    branches = (instance.context or {}).get("_branches") or {}
    return set((branches.get(step_id) or {}).keys())


def _ordered(step) -> bool:
    return step.type == "ordered_signing"


def _handoff(step) -> str:
    # #8: sequential signing auto-advances by DEFAULT (DocuSign-style, no manual poke
    # between signers). A workflow may still opt into manual hand-off by explicitly
    # setting config.handoff="owner_gated". General — applies to any ordered_signing step.
    return str((step.config or {}).get("handoff") or "auto").lower()


def _open_slots(step, instance) -> list[dict]:
    """Slots eligible to sign now: ordered -> the first unsigned; parallel -> all unsigned."""
    signers = _signers(step)
    signed = _signed_slot_ids(instance, step.id)
    pending = [s for s in signers if s["id"] not in signed]
    if not pending:
        return []
    return [pending[0]] if _ordered(step) else pending


async def _require_open_slot(db: AsyncSession, agreement_id, slot_id: str) -> None:
    """THE GATE — the ENGINE authorizes signing, not the UI button or the token.

    Refuse unless the agreement's workflow instance is CURRENTLY AT the signing step
    AND `slot_id` is open right now (ordered: the next unsigned slot; parallel: any
    unsigned slot). Raises 409 — and the caller therefore records NOTHING and writes
    NO artifact — when the engine is anywhere else (e.g. still at REVIEW), when this
    isn't this signer's turn, or when the slot is already signed.

    Must be called BEFORE issuing an OTP or doing any signing work, so a token that
    is valid but out-of-step (lingering across a rework loop, or presented while the
    engine is at an earlier step) cannot drive a signature through."""
    inst, _body, step = await _instance_and_step(db, str(agreement_id))  # 409 if not a signing step
    open_ids = {s["id"] for s in _open_slots(step, inst)}
    if slot_id not in open_ids:
        raise HTTPException(
            status_code=409,
            detail="This signature is not open at the current workflow step.",
        )


# ---------------------------------------------------------------------------
# UP-FRONT signer-contact resolution (DocuSign-style auto-dispatch).
# A signer slot's contact is resolved from its assignee using the SAME DB resolution
# that auto-fills PI/site/sponsor placeholders (resolve_field_value), so when the
# workflow reaches signing each slot already knows who signs — no manual email entry.
# Unresolvable slots return None and fall back to the manual "send for signature" box.
# ---------------------------------------------------------------------------

# role (lower) -> the placeholder field that holds that signer's contact email.
_ROLE_TO_CONTACT_SOURCE = {
    "pi": "site_profile.pi_email",
    "investigator": "site_profile.pi_email",
    "principal_investigator": "site_profile.pi_email",
    "site_director": "site_profile.authorized_signatory_email",
    "authorized_signatory": "site_profile.authorized_signatory_email",
    "site": "site_profile.authorized_signatory_email",
    "site_coordinator": "site_profile.site_coordinator_email",
    "coordinator": "site_profile.site_coordinator_email",
}


def _slot_assignee(step, slot_id: str):
    """The raw assignee dict ({type,value}) for a signer slot, or None."""
    cfg = step.config or {}
    raw = cfg.get("signers") if step.type == "ordered_signing" else cfg.get("branches")
    for b in raw or []:
        if str(b.get("id")) == str(slot_id):
            return b.get("assignee")
    return None


async def resolve_signer_email(db: AsyncSession, agreement: Agreement, assignee, context: dict) -> Optional[str]:
    """Resolve a signer slot's contact email UP FRONT from its assignee. Reuses the same
    role/DB resolution as placeholder auto-fill (resolve_field_value). Returns an email or
    None (None -> manual fallback). General — any role/number of signers, not CTA-specific.
      role 'pi'/'site_director'/'sponsor'/... -> the matching contact field (or settings
      for sponsor); user -> the user's email; context -> context[value] when it's an email."""
    if not assignee:
        return None
    a_type = assignee.get("type") if isinstance(assignee, dict) else getattr(assignee, "type", None)
    a_type = getattr(a_type, "value", a_type)
    val = assignee.get("value") if isinstance(assignee, dict) else getattr(assignee, "value", None)
    if not a_type or not val:
        return None
    a_type = str(a_type).lower()

    if a_type == "context":
        cv = (context or {}).get(str(val))
        return str(cv).strip() if cv and "@" in str(cv) else None
    if a_type == "user":
        if "@" in str(val):
            return str(val).strip()
        from app.models import User
        u = await db.scalar(select(User).where(User.user_id == str(val)))
        return u.email if (u and u.email) else None
    if a_type == "role":
        role = str(val).strip().lower()
        if "sponsor" in role:
            return settings.sponsor_signatory_email or None
        source = _ROLE_TO_CONTACT_SOURCE.get(role)
        if source:
            from app.modules.agreements.services.placeholder_fill import resolve_field_value
            v = await resolve_field_value(source, agreement, db)
            return v if (v and "@" in str(v)) else None
    return None


# ---------------------------------------------------------------------------
# DISPATCH (owner-gated OR auto): create signing tokens + email the secure link.
# ---------------------------------------------------------------------------
async def dispatch(db: AsyncSession, agreement: Agreement, recipients: dict, created_by: Optional[str]) -> dict:
    """For each OPEN slot with a provided recipient email and no active token, create
    an AgreementSigningToken and email the secure signer link. `recipients` = {slot_id: email}
    (merged into instance context so auto-handoff can reach later slots). Owner action."""
    inst, _body, step = await _instance_and_step(db, str(agreement.id))

    # Study context for the external signing email (fetched once; degrades to None).
    study = None
    if agreement.study_id:
        from app.models import Study as _Study
        study = await db.scalar(select(_Study).where(_Study.id == agreement.study_id))

    # Merge provided recipient emails into the instance context (for auto-handoff).
    ctx = dict(inst.context or {})
    emails = dict(ctx.get(_SIGNER_EMAILS_KEY) or {})
    emails.update({str(k): str(v).strip() for k, v in (recipients or {}).items() if v})
    # AUTO-RESOLVE up front: for every OPEN slot the owner didn't give an email for, try
    # to resolve the signer's contact from the slot's assignee (role/user/context) — the
    # same DB resolution as placeholder auto-fill. Resolved slots auto-dispatch below;
    # unresolved ones are simply skipped (manual fallback). Hands-off when assignees are set.
    for _slot in _open_slots(step, inst):
        if not emails.get(_slot["id"]):
            _resolved = await resolve_signer_email(db, agreement, _slot_assignee(step, _slot["id"]), ctx)
            if _resolved:
                emails[_slot["id"]] = _resolved
    ctx[_SIGNER_EMAILS_KEY] = emails
    # Bind each open slot's engine work item to its signer's email so strict role
    # enforcement admits the token signer when they later record their signature.
    overrides = dict(ctx.get(_TASK_OVERRIDES_KEY) or {})
    for _slot in _open_slots(step, inst):
        _em = emails.get(_slot["id"])
        if _em:
            overrides[f"{step.id}:{_slot['id']}"] = _em
    ctx[_TASK_OVERRIDES_KEY] = overrides
    inst.context = ctx
    await db.flush()

    dispatched = []
    for slot in _open_slots(step, inst):
        email = emails.get(slot["id"])
        if not email:
            continue
        # Skip if an active, unexpired token already exists for this slot.
        existing = await db.scalar(
            select(AgreementSigningToken)
            .where(AgreementSigningToken.agreement_id == agreement.id)
            .where(AgreementSigningToken.role == slot["id"])
            .where(AgreementSigningToken.is_active == "true")
            .where(AgreementSigningToken.expires_at > datetime.now(timezone.utc))
        )
        if existing:
            dispatched.append({"slot": slot["id"], "email": email, "status": "already_sent"})
            continue
        token_value = secrets.token_urlsafe(32)
        db.add(AgreementSigningToken(
            agreement_id=agreement.id, token=token_value, role=slot["id"],
            recipient_email=email, expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            created_by=created_by, is_active="true",
        ))
        await _email_signing_link(agreement, email, token_value, slot["name"], study=study)
        dispatched.append({"slot": slot["id"], "email": email, "status": "sent"})
    return {"dispatched": dispatched}


async def _email_signing_link(agreement: Agreement, email: str, token: str, slot_name: str,
                              study=None) -> None:
    """Reuse send_mail. Link points at the REUSED AgreementSignPage in unified mode.
    Context-rich EXTERNAL body (Study Title, Protocol #, Document, action) so the
    external signer has context, not just a bare link. Populated generically — any
    signer slot, any number of signers."""
    base = (settings.frontend_base_url or "").rstrip("/")
    link = f"{base}/agreement/sign/{agreement.id}?token={token}&flow=unified"
    from app.integrations.smtp_service import enqueue_email
    from app.modules.agreements.notifications import build_external_email
    subject, body = build_external_email(
        agreement=agreement,
        study=study,
        action_label=f"Sign as {slot_name}",
        link=link,
        link_label="Open the secure signing page",
        expires_note="You will verify a one-time code sent to this email before signing.",
    )
    try:
        enqueue_email(
            to=email,
            subject=subject,
            body=body,
            from_email=getattr(settings, "smtp_user", "noreply@crm.local"),
            from_name="Clinical Trials CRM",
        )
    except Exception:  # noqa: BLE001 — email is best-effort, never block dispatch
        logger.exception("unified_signing: failed to enqueue signing link for %s", email)


async def _active_token(db: AsyncSession, agreement_id, token: str) -> AgreementSigningToken:
    row = await db.scalar(
        select(AgreementSigningToken)
        .where(AgreementSigningToken.agreement_id == agreement_id)
        .where(AgreementSigningToken.token == token)
        .where(AgreementSigningToken.is_active == "true")
    )
    if row is None:
        raise HTTPException(status_code=401, detail="Invalid or inactive signing link.")
    if row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Signing link expired.")
    return row


async def _latest_doc(db: AsyncSession, agreement_id) -> AgreementDocument:
    rows = (await db.execute(
        select(AgreementDocument).where(AgreementDocument.agreement_id == agreement_id)
    )).scalars().all()
    if not rows:
        raise HTTPException(status_code=404, detail="No document to sign.")
    return max(rows, key=lambda d: d.version_number or 0)


async def _resolve_doc_path(doc: AgreementDocument) -> Optional[str]:
    """Return a LOCAL filesystem path to the document bytes for signing (downloads the
    Azure blob first when the doc is Azure-stored). Delegates to the SHARED resolver in
    doc_convert so signing, append_document, CTA conversion, etc. all resolve identically.
    Returns None when the bytes can't be obtained."""
    return await doc_convert.resolve_local_path(
        doc.document_file_path, getattr(doc, "document_file_url", None))


async def _persist_signed_pdf(agreement: Agreement, signed_pdf: str, version: int,
                              when: datetime) -> tuple[str, Optional[str]]:
    """Persist the freshly-stamped signed PDF to the DURABLE document store (so the
    executed artifact never lives in /tmp). Mirrors create_agreement's v1 persistence,
    reusing the SAME storage helper — no new pipeline:
      * Azure on  -> upload via get_document_storage().upload_file to a stable blob
                     `agreements/{id}/signed_v{NNN}_{ts}.pdf`; returns (blob_name, url).
      * Azure off -> copy into `{upload_dir}/agreements/{id}/signed_v{NNN}_{ts}.pdf`;
                     returns (absolute_path, None).
    Returns (document_file_path, document_file_url) for the AgreementDocument row."""
    from app.utils.azure_storage import get_document_storage

    ts = when.strftime("%Y-%m-%d_%H-%M")
    fname = f"signed_v{version:03d}_{ts}.pdf"
    storage = get_document_storage()
    if storage:
        blob_name = f"agreements/{agreement.id}/{fname}"
        async with aiofiles.open(signed_pdf, "rb") as f:
            pdf_bytes = await f.read()
        url = await storage.upload_file(pdf_bytes, blob_name, content_type="application/pdf")
        logger.info("unified_signing: signed PDF uploaded to Azure blob %s", blob_name)
        return blob_name, url
    dest_dir = Path(settings.upload_dir) / "agreements" / str(agreement.id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / fname
    shutil.copy2(signed_pdf, dest)
    logger.info("unified_signing: storage off — signed PDF saved locally at %s", dest)
    return str(dest.resolve()), None


# ---------------------------------------------------------------------------
# REQUEST OTP (signer): harvested otp.py core — hashed, expiry, cooldown, invalidate.
# ---------------------------------------------------------------------------
async def request_otp(db: AsyncSession, agreement_id: str, token: str) -> dict:
    agreement = await db.get(Agreement, agreement_id)
    if agreement is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    tok = await _active_token(db, agreement.id, token)
    # GATE: don't even mint/email a code unless the engine is at the signing step
    # and this slot is open — the OTP is only meaningful when a signature is allowed.
    await _require_open_slot(db, agreement.id, tok.role)
    doc = await _latest_doc(db, agreement.id)
    now = datetime.now(timezone.utc)

    latest = await db.scalar(
        select(AgreementSigningOtp)
        .where(AgreementSigningOtp.agreement_id == agreement.id)
        .where(AgreementSigningOtp.role == tok.role)
        .where(AgreementSigningOtp.email == tok.recipient_email)
        .order_by(AgreementSigningOtp.created_at.desc())
    )
    if latest and latest.last_sent_at and latest.last_sent_at > now - timedelta(seconds=OTP_RESEND_COOLDOWN_SECONDS):
        wait = OTP_RESEND_COOLDOWN_SECONDS - int((now - latest.last_sent_at).total_seconds())
        raise HTTPException(status_code=429, detail=f"Please wait {max(wait, 1)}s before requesting a new code.")

    # Invalidate older active OTPs (don't widen the brute-force window).
    await db.execute(
        update(AgreementSigningOtp)
        .where(AgreementSigningOtp.agreement_id == agreement.id)
        .where(AgreementSigningOtp.role == tok.role)
        .where(AgreementSigningOtp.email == tok.recipient_email)
        .where(AgreementSigningOtp.is_active == "true")
        .values(is_active="false")
    )
    otp_value = f"{secrets.randbelow(1_000_000):06d}"
    db.add(AgreementSigningOtp(
        agreement_id=agreement.id, document_id=doc.id, role=tok.role, email=tok.recipient_email,
        otp_hash=_hash_otp_value(otp_value), expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES),
        attempts=0, last_sent_at=now, is_active="true",
    ))
    from app.integrations.smtp_service import smtp_service
    result = await smtp_service.send_email_async(
        to=tok.recipient_email,
        subject=f"Your code to sign {agreement.title}",
        body=(f"Your one-time code to sign '{agreement.title}' is {otp_value}.\n\n"
              f"It expires in {OTP_EXPIRY_MINUTES} minutes."),
        from_email=getattr(settings, "smtp_user", "noreply@crm.local"),
        from_name="Clinical Trials CRM",
    )
    if not result.get("success"):
        await db.rollback()
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send code."))
    await db.commit()
    return {"status": "sent", "email": tok.recipient_email, "expires_in_seconds": OTP_EXPIRY_MINUTES * 60}


# ---------------------------------------------------------------------------
# SUBMIT (signer): verify (lockout + failed-attempt audit) then record signature.
# ---------------------------------------------------------------------------
async def submit(db: AsyncSession, agreement_id: str, token: str, otp: str,
                 signer_name: str, signer_title: Optional[str], meaning: Optional[str],
                 request_ip: Optional[str]) -> dict:
    agreement = await db.get(Agreement, agreement_id)
    if agreement is None:
        raise HTTPException(status_code=404, detail="Agreement not found.")
    tok = await _active_token(db, agreement.id, token)
    # GATE: refuse out-of-step BEFORE verifying / consuming the OTP. Nothing is
    # recorded and no artifact is produced unless the engine is at the signing step.
    await _require_open_slot(db, agreement.id, tok.role)
    now = datetime.now(timezone.utc)

    otp_row = await db.scalar(
        select(AgreementSigningOtp)
        .where(AgreementSigningOtp.agreement_id == agreement.id)
        .where(AgreementSigningOtp.role == tok.role)
        .where(AgreementSigningOtp.email == tok.recipient_email)
        .where(AgreementSigningOtp.is_active == "true")
        .where(AgreementSigningOtp.consumed_at.is_(None))
        .order_by(AgreementSigningOtp.created_at.desc())
    )
    if otp_row is None:
        raise HTTPException(status_code=404, detail="No active code — request a new one.")
    if otp_row.expires_at < now:
        otp_row.is_active = "false"
        await db.commit()
        raise HTTPException(status_code=403, detail="Code expired — request a new one.")
    # COMPLIANCE: 5-attempt lockout on ALL signing (fixes the CTA gap).
    if (otp_row.attempts or 0) >= OTP_MAX_ATTEMPTS:
        otp_row.is_active = "false"
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many invalid attempts.")

    submitted = (otp or "").strip()
    if not submitted:
        raise HTTPException(status_code=400, detail="Code is required.")

    import hmac
    if not hmac.compare_digest(otp_row.otp_hash, _hash_otp_value(submitted)):
        otp_row.attempts = (otp_row.attempts or 0) + 1
        # COMPLIANCE: audit EVERY failed attempt.
        db.add(AuditLog(
            user=tok.recipient_email, action="SIGN_OTP_FAILED", target_type="agreement",
            target_id=str(agreement.id),
            details={"role": tok.role, "attempt": otp_row.attempts, "ip": request_ip,
                     "at": now.isoformat()},
        ))
        if otp_row.attempts >= OTP_MAX_ATTEMPTS:
            otp_row.is_active = "false"
        await db.commit()
        raise HTTPException(status_code=400, detail="Invalid code.")

    # OTP good — record the real, manifested signature.
    if not (signer_name or "").strip():
        raise HTTPException(status_code=400, detail="Your full name is required to sign.")
    affirmed_meaning = (meaning or "").strip() or DEFAULT_MEANING
    record = await record_signature(
        db, agreement, slot_id=tok.role, signer_email=tok.recipient_email,
        signer_name=signer_name.strip(), signer_title=(signer_title or "").strip() or None,
        meaning=affirmed_meaning, request_ip=request_ip,
    )
    otp_row.consumed_at = now
    otp_row.is_active = "false"
    tok.is_active = "false"
    await db.commit()
    return record


async def record_signature(db: AsyncSession, agreement: Agreement, *, slot_id: str,
                           signer_email: str, signer_name: str, signer_title: Optional[str],
                           meaning: str, request_ip: Optional[str]) -> dict:
    """The compliant core: manifest the signature onto the FINAL PDF artifact, hash
    that produced artifact, persist the audit signature + signed-document record, and
    advance the engine slot. Reuses render_signature_png_bytes + embed_signature_into_pdf."""
    # GATE (authoritative, defense-in-depth): no PDF is stamped and no row is written
    # unless the engine is at the signing step with this slot open. This is the single
    # precondition that guarantees nothing is recorded out-of-step, regardless of caller.
    await _require_open_slot(db, agreement.id, slot_id)
    doc = await _latest_doc(db, agreement.id)
    src = await _resolve_doc_path(doc)
    if not src or not Path(src).exists():
        raise HTTPException(status_code=404, detail="Document file is not available.")

    # Final artifact MUST be a PDF; edits are DOCX -> convert once (doc_convert module).
    try:
        pdf_path = await doc_convert.to_pdf(src)
    except Exception as exc:  # noqa: BLE001
        logger.exception("unified_signing: DOCX->PDF failed")
        raise HTTPException(status_code=503, detail="Could not prepare the PDF artifact.") from exc

    now = datetime.now(timezone.utc)

    # PLACEMENT: stamp at this role's labeled signature line, stacking when several
    # signers share one block (e.g. site director + PI + remaining all under "For
    # Site"). stack_offset = how many signatures already landed in the SAME block
    # family, so each new mark sits just below the previous one. Engine/compliance
    # are untouched — only the (x, y) of the visible mark changes.
    from app.modules.agreements.utils.pdf_export import _block_family
    my_family = _block_family(slot_id)
    prior_roles = (await db.execute(
        select(AgreementInternalSignature.role)
        .where(AgreementInternalSignature.agreement_id == agreement.id)
    )).scalars().all()
    stack_offset = sum(1 for r in prior_roles if _block_family(r) == my_family)

    # MANIFESTATION via the shared signature_render service (render name -> stamp on
    # PDF). Same logic as before, now factored out so it is shared. (§11.50 fix.)
    # FAIL LOUD: if the signature cannot be placed (no matching placeholder/label, or
    # the placement probe/dependency failed), refuse the signing with a clear 422
    # INSTEAD of stamping nothing and advancing the workflow. This runs BEFORE any
    # signature row, signed-document row, audit row or engine advance — so a failure
    # here abandons the whole transaction (nothing is committed) and the workflow can
    # never report "signed" with an empty placeholder. General across roles/templates.
    from app.modules.agreements.utils.pdf_export import SignaturePlacementError
    try:
        signed_pdf = await signature_render.stamp_on_pdf(
            pdf_path, signer_name, signer_title,
            role=slot_id, stack_offset=stack_offset, signed_on=now.strftime("%Y-%m-%d"),
        )
    except SignaturePlacementError as exc:
        logger.exception("unified_signing: signature placement failed for slot=%s: %s", slot_id, exc)
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # HASH the FINAL produced artifact bytes (not the source; no synthetic fallback).
    final_bytes = Path(signed_pdf).read_bytes()
    final_hash = hashlib.sha256(final_bytes).hexdigest()

    # DURABLE PERSISTENCE — the executed (21 CFR-binding) PDF must NOT live in /tmp.
    # Persist it to the document store the SAME way create_agreement persists v1
    # (reuse get_document_storage()/upload_file for Azure, else copy into upload_dir).
    # The signed AgreementDocument version + AgreementSignedDocument point at the
    # DURABLE location. document_hash above is the hash of these exact bytes — unchanged.
    version = await document_versioning.next_version_number(db, agreement.id)
    durable_path, durable_url = await _persist_signed_pdf(agreement, signed_pdf, version, now)

    # New signed version via the shared document_versioning helper (durable location).
    new_doc = await document_versioning.add_document_version(
        db, agreement.id, durable_path, is_signed=True, created_by=signer_email,
        template_id=doc.created_from_template_id, document_file_url=durable_url)
    new_version = new_doc.version_number

    db.add(AgreementInternalSignature(
        agreement_id=agreement.id, document_id=new_doc.id, role=slot_id, email=signer_email,
        meaning=meaning, auth_method="otp", version=new_version, ip_address=request_ip,
        document_hash=final_hash,
    ))
    db.add(AgreementSignedDocument(agreement_id=agreement.id, file_path=durable_path, signed_at=now))
    db.add(AuditLog(
        user=signer_email, action="SIGNED_WITH_OTP", target_type="agreement",
        target_id=str(agreement.id),
        details={"role": slot_id, "meaning": meaning, "version": new_version,
                 "document_hash": final_hash, "ip": request_ip, "at": now.isoformat()},
    ))
    await db.flush()

    advanced = await _advance_engine_slot(db, agreement, slot_id, signer_email)
    return {"status": "signed", "slot": slot_id, "version": new_version,
            "document_hash": final_hash, "meaning": meaning, "engine": advanced}


async def _advance_engine_slot(db: AsyncSession, agreement: Agreement, slot_id: str, signer_email: str) -> dict:
    """Advance ONLY this slot in the engine (the engine owns order/quorum/all_signed).
    Matches the slot's available action (ordered: {slot}:sign, parallel: {slot}:approve)
    and performs it. Then, for ordered + auto handoff, dispatch the next slot."""
    from app.modules.workflows import service as wf
    from app.modules.workflows.schemas import CurrentUser

    inst = await wf.find_instance_by_subject(db, str(agreement.id))
    if inst is None:
        return {"advanced": False, "reason": "no instance"}
    # Bind THIS slot to THIS signer (self-heals slots dispatched before the override
    # was written, e.g. auto-handoff) so strict authorization admits the token signer.
    if inst.current_step:
        _bind_signer_override(inst, inst.current_step, slot_id, signer_email)
        await db.flush()
    signer = CurrentUser(id=signer_email, roles=[])
    acts = await wf.available_actions(db, inst.id, signer)
    action = next((a for a in acts if a.transition_id.startswith(f"{slot_id}:")
                   and a.action not in ("decline", "reject")), None)
    if action is None:
        # Not this slot's turn (ordered) or already recorded — engine is source of truth.
        raise HTTPException(status_code=409, detail="It is not this signer's turn yet.")
    await wf.perform_action(db, inst.id, signer, action.transition_id,
                            {"signed_by": signer_email}, trusted_payload=True)
    await db.flush()

    # Auto-handoff: ordered + handoff=auto -> dispatch the now-current slot. If the
    # step just completed (all signed -> moved past the signing step), there is
    # nothing to hand off — _instance_and_step raises 409, which we swallow.
    out = {"advanced": True, "transition": action.transition_id}
    try:
        _i2, _b, step = await _instance_and_step(db, str(agreement.id))
        if _ordered(step) and _handoff(step) == "auto":
            inst2 = await wf.find_instance_by_subject(db, str(agreement.id))
            emails = (inst2.context or {}).get(_SIGNER_EMAILS_KEY) or {}
            disp = await dispatch(db, agreement, emails, created_by="system:auto-handoff")
            out["auto_dispatch"] = disp["dispatched"]
    except HTTPException:
        pass  # step completed / not a signing step — nothing to hand off
    return out


# ---------------------------------------------------------------------------
# ATTACH EXECUTED (offline-signed) — GENERAL alternative to OTP e-signing.
# ---------------------------------------------------------------------------
async def attach_executed(db: AsyncSession, agreement: Agreement, file_bytes: bytes,
                          filename: Optional[str], by: Optional[str] = None) -> dict:
    """The agreement was signed OUTSIDE the system (paper / external e-sign). Persist the
    uploaded executed document as the signed version, record an audit signature, and
    COMPLETE the engine's signing step (mark every open signer slot signed, offline) so
    the workflow advances to terminal — firing the SAME completion bridge as OTP signing
    (e.g. CDA -> SiteWorkflowStep.CDA_EXECUTION via _maybe_finalize_agreement_subject).
    General: any agreement type, any signing step (ordered or parallel). Owner action."""
    import os
    from app.modules.workflows import service as wf
    from app.modules.workflows.schemas import CurrentUser

    # GATE: must be at a signing step (409 otherwise) — same precondition as OTP signing.
    inst, _body, step = await _instance_and_step(db, str(agreement.id))
    now = datetime.now(timezone.utc)

    # Persist the uploaded executed file as a new signed version (durable store; reuse the
    # signed-PDF persister by writing the bytes to a temp file first).
    suffix = Path(filename).suffix if (filename and Path(filename).suffix) else ".pdf"
    tmp = await asyncio.to_thread(_make_named_tempfile, suffix, file_bytes)
    try:
        version = await document_versioning.next_version_number(db, agreement.id)
        durable_path, durable_url = await _persist_signed_pdf(agreement, tmp.name, version, now)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    final_hash = hashlib.sha256(file_bytes).hexdigest()
    new_doc = await document_versioning.add_document_version(
        db, agreement.id, durable_path, is_signed=True, created_by=by, document_file_url=durable_url)
    db.add(AgreementInternalSignature(
        agreement_id=agreement.id, document_id=new_doc.id, role="executed", email=(by or "system"),
        meaning="Executed document attached (signed offline)", auth_method="offline_attached",
        version=new_doc.version_number, ip_address=None, document_hash=final_hash))
    db.add(AgreementSignedDocument(agreement_id=agreement.id, file_path=durable_path, signed_at=now))
    db.add(AuditLog(
        user=(by or "system"), action="EXECUTED_DOC_ATTACHED", target_type="agreement",
        target_id=str(agreement.id),
        details={"version": new_doc.version_number, "document_hash": final_hash, "filename": filename}))
    await db.flush()

    # Complete the signing step offline: the attached document covers every signer, so mark
    # each OPEN slot signed (no email/OTP) until the engine leaves the signing step -> the
    # instance reaches terminal -> the completion bridge fires.
    actor = CurrentUser(id=(by or "system:offline"), roles=[])
    for _ in range(50):  # bound: never loop forever even on a malformed definition
        try:
            _i, _b2, cur = await _instance_and_step(db, str(agreement.id))
        except HTTPException:
            break  # no longer at a signing step — done
        opens = _open_slots(cur, _i)
        if not opens:
            break
        sid = opens[0]["id"]
        if _i.current_step:
            _bind_signer_override(_i, _i.current_step, sid, actor.id)
            await db.flush()
        acts = await wf.available_actions(db, _i.id, actor)
        action = next((a for a in acts if a.transition_id.startswith(f"{sid}:")
                       and a.action not in ("decline", "reject")), None)
        if action is None:
            break
        await wf.perform_action(db, _i.id, actor, action.transition_id,
                                {"signed_by": actor.id, "offline_attached": True}, trusted_payload=True)
        await db.flush()

    inst2 = await wf.find_instance_by_subject(db, str(agreement.id))
    return {"status": "executed", "version": new_doc.version_number, "document_hash": final_hash,
            "engine": {"current_step": inst2.current_step if inst2 else None,
                       "status": inst2.status if inst2 else None}}


# ---------------------------------------------------------------------------
# STATUS (panel): slots + who's signed + current open slot.
# ---------------------------------------------------------------------------
async def status(db: AsyncSession, agreement_id: str) -> dict:
    inst, _body, step = await _instance_and_step(db, str(agreement_id))
    signed = _signed_slot_ids(inst, step.id)
    open_ids = {s["id"] for s in _open_slots(step, inst)}
    ctx = inst.context or {}
    emails = ctx.get(_SIGNER_EMAILS_KEY) or {}
    agreement = await db.get(Agreement, agreement_id)
    # Which slots already have an active signing link (so the UI shows "link sent").
    active_roles = set((await db.execute(
        select(AgreementSigningToken.role)
        .where(AgreementSigningToken.agreement_id == agreement_id)
        .where(AgreementSigningToken.is_active == "true")
        .where(AgreementSigningToken.expires_at > datetime.now(timezone.utc))
    )).scalars().all())

    slots = []
    for s in _signers(step):
        sid = s["id"]
        state = "signed" if sid in signed else ("open" if sid in open_ids else "pending")
        # The resolved up-front contact: a stored email, else (for an OPEN slot) what the
        # assignee resolves to. `auto` tells the UI to auto-dispatch (no manual box); a
        # falsey `auto` on an open slot means the contact is unresolvable -> manual fallback.
        contact = emails.get(sid)
        if state == "open" and not contact and agreement is not None:
            contact = await resolve_signer_email(db, agreement, _slot_assignee(step, sid), ctx)
        slots.append({
            "id": sid, "name": s["name"], "state": state,
            "email": emails.get(sid),
            "contact": contact,
            "auto": bool(contact),
            "sent": sid in active_roles,
        })
    return {"step": step.id, "type": step.type, "ordered": _ordered(step),
            "handoff": _handoff(step), "slots": slots}

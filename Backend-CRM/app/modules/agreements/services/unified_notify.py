"""
unified_notify.py — backend for the NOTIFY and BROADCAST_DELIVER modules
(behind WORKFLOW_UNIFIED).

  * notify    — fire a real in-app notification, reusing the EXISTING
                create_agreement_notice (Notice Board) (agreement_service.py:551).
  * broadcast — REAL per-recipient delivery (the inventory flagged the engine only
                RECORDS recipients): loop the recipient list and enqueue_email
                (smtp_service.enqueue_email:369), optionally attaching the final
                document. Per-recipient success is tracked and returned.

Best-effort by design (mirrors existing side-effect code); callers don't assume a
send happened — the result reports what fired. Live paths untouched.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Agreement

logger = logging.getLogger(__name__)


async def notify(db: AsyncSession, agreement: Agreement, message: str,
                 metadata: Optional[dict] = None) -> dict:
    """Fire an in-app notification for this agreement (reuses create_agreement_notice).
    Returns {fired: bool}. Best-effort: a failure never blocks the workflow."""
    try:
        from app.modules.agreements.services.agreement_service import create_agreement_notice
        await create_agreement_notice(db, agreement, "WORKFLOW_NOTIFY", message, metadata or {})
        await db.commit()
        return {"fired": True}
    except Exception:  # noqa: BLE001
        logger.exception("unified_notify.notify: failed for agreement %s", getattr(agreement, "id", "?"))
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {"fired": False}


async def broadcast(db: AsyncSession, agreement: Agreement, recipients: list[dict],
                    attach_document: bool = False, message: Optional[str] = None) -> dict:
    """Distribute the final copy: email EACH recipient (reuse enqueue_email),
    optionally attaching the final document. Returns per-recipient results so the
    caller can report exactly who was reached. `recipients` = [{email, name?}]."""
    from app.integrations.smtp_service import enqueue_email

    attachments: Optional[list[str]] = None
    attached = False
    if attach_document:
        from app.modules.agreements.services import document_versioning
        from pathlib import Path
        latest = await document_versioning.latest_document(db, agreement.id)
        path = latest.document_file_path if latest else None
        if path and not str(path).startswith("agreements/") and Path(path).exists():
            attachments = [path]
            attached = True  # local file attachable; Azure-keyed docs go as a link instead

    body_base = (message or
                 f"The final executed copy of '{agreement.title}' is ready.")
    if not attached:
        body_base += "\n\n(Access the final document in the CRM.)"

    results = []
    for r in recipients or []:
        email = (r.get("email") or "").strip()
        name = r.get("name") or email
        if not email:
            results.append({"recipient": name, "email": None, "sent": False, "reason": "no email"})
            continue
        try:
            task_id = enqueue_email(
                to=email,
                subject=f"Final copy: {agreement.title}",
                body=f"Hello {name},\n\n{body_base}",
                from_email=getattr(settings, "smtp_user", "noreply@crm.local"),
                from_name="Clinical Trials CRM",
                attachments=attachments,
            )
            results.append({"recipient": name, "email": email, "sent": True, "task_id": task_id})
        except Exception as exc:  # noqa: BLE001
            logger.exception("unified_notify.broadcast: send failed for %s", email)
            results.append({"recipient": name, "email": email, "sent": False, "reason": str(exc)})

    sent = sum(1 for x in results if x["sent"])
    return {"attached": attached, "sent_count": sent, "total": len(results), "results": results}

"""Best-effort audit writes for the Communications module (Job D STEP 3).

Reuses the app's existing audit mechanism (``crud.create_audit_log`` → the
``AuditLog`` model), wrapped exactly like the conversation message handler
already isolates its audit: bounded by a timeout, never raised into the request,
but logged at error level on failure so a missing audit row is visible.
Threads/attachments/conversation-create all write an audit row here.

`details` must be PII-safe — pass ids / counts / status, never raw participant
emails or message bodies.
"""
import asyncio
import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app import crud

logger = logging.getLogger(__name__)


async def best_effort_audit(
    db: AsyncSession,
    *,
    user: Optional[str],
    action: str,
    target_type: str,
    target_id: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    """Write an AuditLog row best-effort.

    Never raises: a DB/timeout failure is logged at error level (an un-audited
    mutation is a compliance concern) but the user's action is never blocked.
    """
    try:
        await asyncio.wait_for(
            crud.create_audit_log(
                db,
                user=str(user) if user else None,
                action=action,
                target_type=target_type,
                target_id=str(target_id),
                details=details or {},
            ),
            timeout=5.0,
        )
    except asyncio.TimeoutError:
        logger.exception(
            "audit timed out: action=%s target=%s/%s user=%s", action, target_type, target_id, user
        )
    except Exception:
        logger.error(
            "audit failed: action=%s target=%s/%s user=%s",
            action, target_type, target_id, user, exc_info=True,
        )

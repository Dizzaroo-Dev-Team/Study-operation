"""
Mailgun email service helper.

This module provides a thin async wrapper around the Mailgun HTTP API and is
intended to be reused by any feature that needs to send emails via Mailgun.

Configuration is read from environment variables so we don't duplicate config
in Pydantic settings:
- MAILGUN_API_KEY
- MAILGUN_DOMAIN
- MAILGUN_BASE_URL (optional, defaults to https://api.mailgun.net/v3/{domain})
- MAILGUN_FROM_EMAIL (optional, defaults to noreply@{domain})
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


MAILGUN_API_KEY = os.getenv("MAILGUN_API_KEY")
MAILGUN_DOMAIN = os.getenv("MAILGUN_DOMAIN")
MAILGUN_BASE_URL = os.getenv("MAILGUN_BASE_URL") or (
    f"https://api.mailgun.net/v3/{MAILGUN_DOMAIN}" if MAILGUN_DOMAIN else None
)
MAILGUN_FROM_EMAIL = os.getenv("MAILGUN_FROM_EMAIL") or (
    f"noreply@{MAILGUN_DOMAIN}" if MAILGUN_DOMAIN else None
)


async def send_mail(
    *,
    to: Union[str, List[str]],
    subject: str,
    text: str,
    attachments: Optional[List[Dict[str, Any]]] = None,
    from_email: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send an email via Mailgun.

    Args:
        to: Single recipient or list of recipients.
        subject: Email subject.
        text: Plain-text body.
        attachments: Optional list of attachment dicts:
            { "filename": str, "content": bytes, "content_type": str }
        from_email: Optional override for From address.

    Returns:
        Dict with { success: bool, ... } describing result.
    """
    if not MAILGUN_API_KEY or not MAILGUN_DOMAIN or not MAILGUN_BASE_URL:
        logger.error("Mailgun configuration is missing. Skipping send.")
        return {
            "success": False,
            "error": "Mailgun not configured",
            "method": "mailgun",
        }

    if isinstance(to, str):
        recipients = [to]
    else:
        recipients = [addr for addr in to if addr]

    if not recipients:
        return {
            "success": False,
            "error": "No recipients provided",
            "method": "mailgun",
        }

    sender = from_email or MAILGUN_FROM_EMAIL
    if not sender:
        logger.error("MAILGUN_FROM_EMAIL is not set and no from_email override supplied.")
        return {
            "success": False,
            "error": "Mailgun from email not configured",
            "method": "mailgun",
        }

    data = {
        "from": sender,
        "to": recipients,
        "subject": subject,
        "text": text,
    }

    files: Optional[List[Any]] = None
    if attachments:
        files = []
        for att in attachments:
            filename = att.get("filename") or "attachment"
            content = att.get("content") or b""
            content_type = att.get("content_type") or "application/octet-stream"
            files.append(("attachment", (filename, content, content_type)))

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{MAILGUN_BASE_URL}/messages",
                auth=("api", MAILGUN_API_KEY),
                data=data,
                files=files,
            )
            resp.raise_for_status()

        payload = resp.json()
        logger.info("Mailgun send_mail success: id=%s message=%s", payload.get("id"), payload.get("message"))
        return {
            "success": True,
            "id": payload.get("id"),
            "message": payload.get("message"),
            "method": "mailgun",
        }
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.error("Mailgun send_mail failed: %s", exc, exc_info=True)
        return {
            "success": False,
            "error": str(exc),
            "method": "mailgun",
        }


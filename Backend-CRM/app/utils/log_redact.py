"""Tiny PII redaction helpers for log lines.

Keep debugging context (counts, masked forms) without emitting raw PII —
participant emails or message bodies must never reach plaintext logs/stdout.
"""
from typing import Iterable, List, Optional


def mask_email(email: Optional[str]) -> str:
    """`alice@example.com` -> `a***@example.com`. Empty/invalid -> `***`."""
    s = str(email or "").strip()
    if not s:
        return ""
    if "@" not in s:
        return "***"
    local, _, domain = s.partition("@")
    head = local[0] if local else ""
    return f"{head}***@{domain}"


def mask_emails(emails: Optional[Iterable[str]]) -> List[str]:
    return [mask_email(e) for e in (emails or []) if e]


def body_preview(body: Optional[str]) -> str:
    """Never log a message body; report its length only."""
    return f"<{len(body or '')} chars>"

"""notifications.py — reusable EXTERNAL reviewer/signer email body builder.

External recipients are reached by one-time token links (review / signing) and have no
in-app context, so a bare "here is a link" email gets ignored. This builds a
context-rich body — Study Title, Protocol Number, Document Name, and the required
action — that populates GENERICALLY from study/agreement metadata: any agreement type,
any action, any number of recipients.

Internal participants are notified IN-APP (the worklist), NOT through the token-dispatch
send-sites that use this helper — so applying it on the external path leaves internal
notifications untouched (they stay plain), exactly as required.

Every metadata field is optional and degrades gracefully (a missing study simply omits
those lines); the builder never raises on absent data.
"""
from __future__ import annotations

from typing import Optional, Tuple


def study_protocol_number(study) -> Optional[str]:
    """Protocol number for a Study. Reuses the established convention (cta/service.py):
    a dedicated ``protocol_number`` column when present, else the external study
    identifier ``study_id``. Returns None when no study/identifier is available."""
    if not study:
        return None
    return getattr(study, "protocol_number", None) or getattr(study, "study_id", None)


def build_external_email(
    *,
    agreement,
    study,
    action_label: str,
    link: str,
    link_label: str = "Open the secure link",
    message: Optional[str] = None,
    expires_note: Optional[str] = "This link will expire in 30 days.",
) -> Tuple[str, str]:
    """Build ``(subject, body)`` for an external recipient.

    ``action_label`` is the required-action text (e.g. "Review and respond" / "Sign").
    All other context is pulled generically from ``agreement`` + ``study`` and any
    missing piece is simply omitted.
    """
    doc_name = getattr(agreement, "title", None) or "Agreement document"
    title = getattr(study, "name", None) if study else None
    protocol = study_protocol_number(study)

    subject = f"Action required: {action_label} — {doc_name}"

    lines = [
        f"You have been asked to complete the following action: {action_label}.",
        "",
    ]
    if title:
        lines.append(f"Study Title:      {title}")
    if protocol:
        lines.append(f"Protocol Number:  {protocol}")
    lines.append(f"Document:         {doc_name}")
    lines.append(f"Required action:  {action_label}")
    lines.append("")
    lines.append(f"{link_label}:")
    lines.append(link)
    if message:
        lines.extend(["", "Message from the sender:", message])
    if expires_note:
        lines.extend(["", expires_note])

    return subject, "\n".join(lines)

"""Helpers for the email-alias routing scheme used by conversations and threads.

Outbound emails send `From: <local_part>@<domain>`.
Inbound webhook resolves `<local_part>` back to the originating doc.

Local-part rules:
    Conversation: clean(study_id) + clean(site_id) + 'c' + <6hex of conv.id>
    Thread:       clean(related_study_id) + clean(site_id) + 't' + <8hex of thread.id>

`clean()` lowercases and strips every non-[a-z0-9] character.
The `c<6hex>` / `t<8hex>` suffix disambiguates between multiple
conversations or threads that share the same (study, site).

Conversations and threads created before this scheme existed may have no
`email_alias` field at all; the inbound webhook falls back to a scan + rebuild
that reproduces the same logic.
"""
from __future__ import annotations

import re
from typing import Optional
from uuid import UUID

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_NON_HEX = re.compile(r"[^0-9a-f]")


def _norm(value) -> str:
    """Lowercase + strip every non-[a-z0-9] character."""
    return _NON_ALNUM.sub("", str(value or "").lower())


def _hex_prefix(value, length: int) -> str:
    """Return the leading `length` hex chars of an id (UUID or string)."""
    return _NON_HEX.sub("", str(value or "").lower())[:length]


def alias_base(study_id: Optional[str], site_id: Optional[str]) -> Optional[str]:
    """Return just the `clean(study)+clean(site)` portion of an alias, no
    disambiguator. Stamped on every doc so the inbound webhook can resolve a
    recipient even when the trailing `c<6hex>` / `t<8hex>` is missing or has
    been mangled by an external mail client."""
    if not study_id or not site_id:
        return None
    base = f"{_norm(study_id)}{_norm(site_id)}"
    return base or None


def build_conversation_alias(
    study_id: Optional[str],
    site_id: Optional[str],
    conversation_id,
    conversation_number: Optional[int] = None,
) -> Optional[str]:
    """Build the canonical email-alias local-part for a conversation.

    Preferred form (when `conversation_number` is supplied): ``<study><site>c<n>``,
    where ``n`` is the per-(study,site) sequential number. Produces short,
    human-readable aliases like ``studyxsite009c1`` once the caller resolves
    `study_id` / `site_id` to their friendly external codes.

    Legacy form (no `conversation_number`): ``<study><site>c<6hex_of_uuid>``,
    kept only for backwards compatibility with docs that pre-date the counter.
    """
    base = alias_base(study_id, site_id)
    if not base:
        return None
    if conversation_number is not None:
        return f"{base}c{int(conversation_number)}"
    suffix = _hex_prefix(conversation_id, 6)
    return f"{base}c{suffix}" if suffix else base


def build_thread_alias(
    related_study_id: Optional[str],
    site_id: Optional[str],
    thread_id,
    thread_number: Optional[int] = None,
) -> Optional[str]:
    """Build the canonical email-alias local-part for a thread.

    Numbered form: ``<study><site>t<n>``. Legacy form: ``<study><site>t<8hex>``.
    """
    base = alias_base(related_study_id, site_id)
    if not base:
        return None
    if thread_number is not None:
        return f"{base}t{int(thread_number)}"
    suffix = _hex_prefix(thread_id, 8)
    return f"{base}t{suffix}" if suffix else base


def format_display_alias(
    study_friendly: Optional[str],
    site_friendly: Optional[str],
    kind: str,
    number: Optional[int],
) -> Optional[str]:
    """Return the dash-separated, human-readable form of an alias for use as
    an outbound ``From:`` local-part — e.g. ``studyx-site009-c1``.

    ``kind`` is ``"c"`` for conversations and ``"t"`` for threads.

    The display form contains dashes; inbound matching normalises them away,
    so this stays compatible with the stored ``email_alias``.
    """
    if not study_friendly or not site_friendly or number is None:
        return None
    s = _NON_ALNUM.sub("-", str(study_friendly).lower()).strip("-")
    t = _NON_ALNUM.sub("-", str(site_friendly).lower()).strip("-")
    if not s or not t:
        return None
    marker = "t" if kind == "t" else "c"
    return f"{s}-{t}-{marker}{int(number)}"


def normalize_alias(local_part: str) -> str:
    """Normalise an inbound recipient local-part for comparison."""
    return _norm(local_part)


def iter_prefixes(local_part_norm: str, min_length: int = 4) -> list[str]:
    """Return every non-empty prefix of `local_part_norm` from longest to
    shortest, down to `min_length`. Used to look up a stored `email_alias_base`
    via an indexed `$in` query when the inbound recipient doesn't match the
    full alias exactly (suffix mangled / dropped)."""
    if not local_part_norm:
        return []
    n = len(local_part_norm)
    floor = max(min_length, 1)
    return [local_part_norm[:i] for i in range(n, floor - 1, -1)]

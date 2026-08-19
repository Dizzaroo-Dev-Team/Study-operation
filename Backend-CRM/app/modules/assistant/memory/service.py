"""Load + shape derived memory for Orbit's prompt and the welcome-back UI.

Two consumers:
  * ``build_prompt_block(user_id)`` — a compact "what you remember about this
    user" block injected into the agent's system prompt each turn (one read).
  * ``build_welcome_back(...)`` — the greeting payload for session open: a memory
    recap + last-session line. The "what needs attention" number is NOT here —
    that is fetched live/guarded by the caller, never remembered.

Entitlement safety: ``context`` items carrying a study reference are re-validated
against the user's CURRENT entitled studies before they are ever surfaced, so a
study the user lost access to is silently dropped.
"""
from __future__ import annotations

import logging
from typing import Iterable, Optional

from app.modules.assistant.memory import phi_filter, repository as repo
from app.modules.assistant.memory.models import AssistantMemory

logger = logging.getLogger(__name__)


def _entitled_reference(item: AssistantMemory, entitled_codes: Optional[set[str]]) -> bool:
    """A context item with a study reference is only usable if that study is in
    the user's current entitled set. Items with no reference are always fine."""
    if item.type != "context" or not item.ref_study_id:
        return True
    if entitled_codes is None:  # entitlement set unknown → be safe, drop the ref
        return False
    return item.ref_study_id in entitled_codes


def _filter_items(
    items: Iterable[AssistantMemory], entitled_codes: Optional[set[str]]
) -> list[AssistantMemory]:
    out: list[AssistantMemory] = []
    for it in items:
        if it.excluded:
            continue
        # Defence-in-depth: never surface an item that somehow reads as PHI.
        if not phi_filter.is_safe_memory(it.text):
            continue
        if not _entitled_reference(it, entitled_codes):
            continue
        out.append(it)
    return out


async def build_prompt_block(
    user_id: str, entitled_codes: Optional[set[str]] = None
) -> str:
    """Compact memory block for the system prompt. Empty string when nothing to
    say (fresh user → no block → no fake 'welcome back')."""
    items = _filter_items(await repo.load_memory(user_id), entitled_codes)
    if not items:
        return ""
    lines = [f"- ({it.type}) {it.text}" for it in items]
    return (
        "\n# WHAT YOU REMEMBER ABOUT THIS USER (derived, non-sensitive)\n"
        "Use these to adapt tone and anticipate needs. They are preferences and "
        "working patterns, NOT facts to state back verbatim and NOT record data. "
        "Never claim you 'profiled' the user.\n" + "\n".join(lines)
    )


async def build_welcome_back(
    user_id: str, entitled_codes: Optional[set[str]] = None
) -> dict:
    """Greeting payload for session open. Returns:
        {returning: bool, memories: [{id,type,text}], last: {text} | None}

    ``last`` is PHI-guarded before it leaves here. A fresh user → returning=False
    with empty memories (caller shows a normal cold open)."""
    items = _filter_items(await repo.load_memory(user_id), entitled_codes)
    memories = [{"id": str(it.id), "type": it.type, "text": it.text} for it in items[:8]]

    last_line = None
    recap = await repo.last_session_recap(user_id)
    if recap and phi_filter.is_safe_memory(recap["text"]):
        # Only a short, safe paraphraseable hint — never the full raw turn.
        last_line = recap["text"][:120]

    return {
        "returning": bool(memories or last_line),
        "memories": memories,
        "last": {"text": last_line} if last_line else None,
    }

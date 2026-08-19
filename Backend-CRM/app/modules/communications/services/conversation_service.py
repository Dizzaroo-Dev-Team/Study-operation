"""
Conversation service helpers.
"""
from typing import Dict, Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.communications.repositories import ConversationRepository


async def ensure_public_notice_board(site_id: str, study_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Ensure a pinned Public Notice Board conversation exists for a site and study (study-specific).
    Each study+site combination has its own notice board.

    Uses the atomic `find_or_create_pinned_notice_board` repository helper so
    concurrent calls from multiple tabs / routes can't both create a duplicate
    board. The old `get + if-not-found -> create` pattern had a race window;
    when two tabs of the same inbox hit `/conversations` at the same moment,
    both saw "no board" and both inserted. That race produced the duplicate
    "Public Notice Board" entries the user observed in the inbox sidebar.
    """
    return await ConversationRepository.find_or_create_pinned_notice_board(site_id, study_id)


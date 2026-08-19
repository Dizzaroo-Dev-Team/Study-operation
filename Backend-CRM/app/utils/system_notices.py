"""
System notice message helper.
Creates public notice board messages in Conversations for system events.
"""
import logging
from typing import Optional, Dict, Any, List
from uuid import UUID
from app import crud
from app.schemas import MessageCreate
from app.models import MessageDirection, MessageChannel
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.communications.services.conversation_service import ensure_public_notice_board

logger = logging.getLogger(__name__)


async def create_system_notice_message(
    db: AsyncSession,
    site_id: str,
    message: str,
    created_by: Optional[str] = None,
    study_id: Optional[str] = None,
    attachment_url: Optional[str] = None,
    attachment_name: Optional[str] = None,
    attachment_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_type: Optional[str] = None,
) -> dict:
    """
    Create a system notice message in the public Conversations feed.
    
    This creates a Conversation entry (public notice board) for system events like:
    - CDA sent
    - CDA signed
    - Status updated
    - Document filed
    
    Args:
        db: Database session
        site_id: Site ID for the notice
        message: The notice message text
        created_by: User who triggered the notice (optional)
        study_id: Study ID (optional)
        
    Returns:
        Public notice board conversation dict
    """
    # Ensure one pinned Public Notice Board exists for this study+site, then append the system message there.
    conversation = await ensure_public_notice_board(site_id, study_id)
    conv_id = conversation.get("id") if isinstance(conversation, dict) else conversation.id
    notice_metadata: Dict[str, Any] = {"origin": "system"}
    if study_id:
        notice_metadata["study_id"] = study_id
    if attachment_url:
        notice_metadata["attachment_url"] = attachment_url
    if attachment_name:
        notice_metadata["attachment_name"] = attachment_name
    if attachment_type:
        notice_metadata["attachment_type"] = attachment_type
    if event_type:
        notice_metadata["event_type"] = event_type
    if metadata:
        notice_metadata.update(metadata)
    
    # Create the notice message (no email sending - just a notice)
    msg_create = MessageCreate(
        channel=MessageChannel.EMAIL,  # Use EMAIL channel but won't send
        body=message,
        metadata=notice_metadata,
    )
    
    # Create message with no email mentions (so no email is sent)
    # Pass origin, event_type, and is_activity_event as separate parameters for MongoDB storage
    await crud.create_message(
        db=db,
        conv_id=conv_id,
        msg=msg_create,
        direction=MessageDirection.OUTBOUND,
        author_id=created_by or "system",
        author_name="System",
        origin="system",
        event_type=event_type,
        is_activity_event=True  # System notices are activity events
    )
    
    return conversation


async def post_site_event_notice(
    db: AsyncSession,
    *,
    site_ref: Any,
    study_ref: Optional[Any] = None,
    message: str,
    event_type: str,
    created_by: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    """High-level helper used by domain events that don't already have an
    agreement-specific path (site created, site status changed, task created,
    monitoring visit created, feasibility sent / submitted, user thread
    started, ...).

    Resolves a Site reference (UUID, friendly ``site.site_id`` string, or a
    Site ORM instance) to the canonical key the Public Notice Board uses
    (``site.site_id`` for site, ``str(study.id)`` for study — same convention
    as ``create_agreement_notice``, which is what the frontend reads from
    ``GET /conversations?study_id=...&site_id=...``).

    If ``study_ref`` is ``None`` the helper fans out to every study the site
    is mapped to via ``StudySite`` — so site-wide events (status, profile,
    new visit) land on whichever notice board the operator happens to be
    viewing. Failures are logged and swallowed: a notice-board write must
    never roll back the primary domain action.
    """
    from sqlalchemy import select
    from app.models import Site, Study, StudySite

    if site_ref is None:
        return

    site = None
    if hasattr(site_ref, "site_id") and hasattr(site_ref, "id"):
        # Already a Site ORM instance.
        site = site_ref
    else:
        site_str = str(site_ref).strip()
        if not site_str:
            return
        try:
            uid = UUID(site_str)
            site = (
                await db.execute(select(Site).where(Site.id == uid))
            ).scalar_one_or_none()
        except (ValueError, TypeError):
            site = None
        if site is None:
            site = (
                await db.execute(select(Site).where(Site.site_id == site_str))
            ).scalar_one_or_none()

    if site is None:
        logger.debug(
            "post_site_event_notice: site not resolved for ref=%r event=%s — skipping",
            site_ref, event_type,
        )
        return

    site_key = site.site_id or str(site.id)

    study_ids: List[Optional[str]] = []
    if study_ref is not None:
        if hasattr(study_ref, "id"):
            study_ids.append(str(study_ref.id))
        else:
            study_str = str(study_ref).strip()
            if study_str:
                resolved = None
                try:
                    uid = UUID(study_str)
                    resolved = (
                        await db.execute(select(Study).where(Study.id == uid))
                    ).scalar_one_or_none()
                except (ValueError, TypeError):
                    resolved = None
                if resolved is None:
                    resolved = (
                        await db.execute(select(Study).where(Study.study_id == study_str))
                    ).scalar_one_or_none()
                if resolved is not None:
                    study_ids.append(str(resolved.id))
                else:
                    # Caller passed a non-empty study ref we can't resolve — keep
                    # it as-is so an unusual hub-side identifier still ends up
                    # on *some* board rather than getting dropped silently.
                    study_ids.append(study_str)
    else:
        result = await db.execute(
            select(StudySite.study_id).where(StudySite.site_id == site.id)
        )
        for row in result.all():
            sid = row[0]
            if sid is not None:
                study_ids.append(str(sid))

    if not study_ids:
        # No study mapping yet: fall back to the site-only board so the event
        # is not lost entirely.
        study_ids = [None]

    for sid in study_ids:
        try:
            await create_system_notice_message(
                db=db,
                site_id=site_key,
                study_id=sid,
                message=message,
                created_by=created_by,
                metadata=metadata,
                event_type=event_type,
            )
        except Exception:
            logger.exception(
                "post_site_event_notice: failed for site=%s study=%s event=%s",
                site_key, sid, event_type,
            )


async def createSystemNoticeMessage(
    db: AsyncSession,
    site_id: str,
    message: str,
    created_by: Optional[str] = None,
    study_id: Optional[str] = None,
    attachment_url: Optional[str] = None,
    attachment_name: Optional[str] = None,
    attachment_type: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    event_type: Optional[str] = None,
) -> dict:
    """CamelCase alias required by product spec."""
    return await create_system_notice_message(
        db=db,
        site_id=site_id,
        message=message,
        created_by=created_by,
        study_id=study_id,
        attachment_url=attachment_url,
        attachment_name=attachment_name,
        attachment_type=attachment_type,
        metadata=metadata,
        event_type=event_type,
    )

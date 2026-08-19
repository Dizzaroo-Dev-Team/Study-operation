"""
Agreement Workflow Service

Centralized service for managing agreement status transitions with strict workflow rules.
"""

from typing import Optional, Dict, List, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from app.models import Agreement, AgreementStatus, AgreementComment, CommentType, UserRole, UserRoleAssignment, AgreementDocument, AgreementInternalSignature, Site, Study, StudySite
from app.utils.system_notices import create_system_notice_message
import logging

logger = logging.getLogger(__name__)

# Define allowed transitions - no backward transitions, no skipping states
#
# CRM UI maps these to four linear stages (see Frontend agreementWorkflow.ts):
#   PREPARATION (DRAFT) → REVIEW (UNDER_REVIEW / UNDER_NEGOTIATION) →
#   SIGNATURE (READY_FOR_SIGNATURE / SENT_FOR_SIGNATURE) → COMPLETED (EXECUTED / CLOSED)
#
# Target lifecycle:
#   DRAFT → UNDER_REVIEW → READY_FOR_SIGNATURE → SENT_FOR_SIGNATURE → EXECUTED
#
# UNDER_NEGOTIATION is kept for backward-compatibility with any existing rows
# that carry that status, but it is no longer an active step in the UI workflow.
# UNDER_REVIEW is allowed to transition directly to READY_FOR_SIGNATURE so that
# the Review→Signature hand-off works without an intermediate state change.
ALLOWED_TRANSITIONS: Dict[AgreementStatus, List[AgreementStatus]] = {
    AgreementStatus.DRAFT: [
        AgreementStatus.UNDER_REVIEW,
        AgreementStatus.AWAITING_INTERNAL_REVIEW,  # CTA: DRAFT → AWAITING_INTERNAL_REVIEW
    ],
    AgreementStatus.UNDER_REVIEW: [
        AgreementStatus.REVIEWED_AND_SIGNED,
        AgreementStatus.READY_FOR_SIGNATURE,   # primary path (Review → Signature)
        AgreementStatus.UNDER_NEGOTIATION,     # legacy / backward-compat only
    ],
    AgreementStatus.UNDER_NEGOTIATION: [
        AgreementStatus.REVIEWED_AND_SIGNED,
        AgreementStatus.READY_FOR_SIGNATURE,
    ],
    AgreementStatus.REVIEWED_AND_SIGNED: [AgreementStatus.READY_FOR_SIGNATURE],
    AgreementStatus.FULLY_SIGNED: [AgreementStatus.READY_FOR_SIGNATURE],
    AgreementStatus.READY_FOR_SIGNATURE: [AgreementStatus.SENT_FOR_SIGNATURE],
    AgreementStatus.SENT_FOR_SIGNATURE: [
        AgreementStatus.EXECUTED,
        AgreementStatus.AWAITING_SPONSOR_SIGNATURE,  # CTA: SENT_FOR_SIGNATURE → AWAITING_SPONSOR_SIGNATURE
    ],
    # CTA-only states
    AgreementStatus.AWAITING_INTERNAL_REVIEW: [AgreementStatus.INTERNAL_REVIEW_APPROVED],
    AgreementStatus.INTERNAL_REVIEW_APPROVED: [AgreementStatus.SENT_FOR_SIGNATURE],
    AgreementStatus.AWAITING_SPONSOR_SIGNATURE: [AgreementStatus.EXECUTED],
    AgreementStatus.EXECUTED: [AgreementStatus.CLOSED],
    AgreementStatus.CLOSED: [],  # No transitions allowed from CLOSED
}

def is_transition_allowed(current_status: AgreementStatus, new_status: AgreementStatus) -> bool:
    """
    Check if a status transition is allowed.
    
    Args:
        current_status: Current agreement status
        new_status: Desired new status
        
    Returns:
        True if transition is allowed, False otherwise
    """
    allowed_next_statuses = ALLOWED_TRANSITIONS.get(current_status, [])
    return new_status in allowed_next_statuses


def get_next_allowed_status(current_status: AgreementStatus) -> Optional[AgreementStatus]:
    """
    Get the next allowed status in the workflow.
    
    Args:
        current_status: Current agreement status
        
    Returns:
        Next allowed status, or None if no transitions allowed
    """
    allowed_next = ALLOWED_TRANSITIONS.get(current_status, [])
    return allowed_next[0] if allowed_next else None


def check_can_upload_new_version(
    current_status: AgreementStatus,
    has_signed_version: bool = False
) -> bool:
    """
    Backward-compatibility stub – legacy file-based version uploads are no longer supported.
    Always returns False.
    """
    return False


def filter_versions_by_role(
    versions,
    is_internal: bool = True
) -> list:
    """
    Backward-compatibility stub – legacy file-based version filtering removed.
    Always returns an empty list.
    """
    return []


def can_change_status(current_status: AgreementStatus) -> tuple[bool, str]:
    """
    Check if status change is allowed for current status.
    Status change rules are governed directly by ALLOWED_TRANSITIONS.
    This helper remains for backward compatibility.
    """
    return True, ""


def is_user_internal(user_id: Optional[str], db: AsyncSession) -> bool:
    """
    Determine if a user is internal or external based on their role assignments.
    
    Internal users: Users with roles like CRA, STUDY_MANAGER, MEDICAL_MONITOR
    External users: Users without these roles (e.g., site coordinators, participants)
    
    Args:
        user_id: User ID to check
        db: Database session
        
    Returns:
        True if user is internal, False if external or None
    """
    if not user_id:
        return False  # Anonymous users are treated as external
    
    # For now, default to True (internal) - can be enhanced with actual role checking
    # TODO: Implement actual role checking based on UserRoleAssignment
    return True


def can_create_comment_type(user_id: Optional[str], comment_type: CommentType, db: AsyncSession) -> tuple[bool, str]:
    """
    Check if user can create a comment of the specified type.
    
    Args:
        user_id: User ID
        comment_type: Comment type to create
        db: Database session
        
    Returns:
        Tuple of (is_allowed, error_message)
    """
    # SYSTEM comments cannot be created manually
    if comment_type == CommentType.SYSTEM:
        return False, "SYSTEM comments cannot be created manually. They are generated automatically."
    
    is_internal = is_user_internal(user_id, db)
    
    # INTERNAL users can create INTERNAL and EXTERNAL comments
    if is_internal:
        if comment_type in [CommentType.INTERNAL, CommentType.EXTERNAL]:
            return True, ""
        return False, f"Invalid comment type for internal user: {comment_type.value}"
    
    # EXTERNAL users can only create EXTERNAL comments
    if comment_type == CommentType.EXTERNAL:
        return True, ""
    
    return False, f"EXTERNAL users cannot create {comment_type.value} comments. Only EXTERNAL comments are allowed."


def filter_comments_by_role(
    comments: List[AgreementComment],
    is_internal: bool = True
) -> List[AgreementComment]:
    """
    Filter comments based on user role.
    
    Args:
        comments: List of agreement comments
        is_internal: True if user is internal, False if external
        
    Returns:
        Filtered list of comments sorted by created_at ASC
    """
    if is_internal:
        # Internal users can see all comments
        filtered = comments
    else:
        # External users can only see EXTERNAL and SYSTEM comments
        filtered = [c for c in comments if c.comment_type in [CommentType.EXTERNAL, CommentType.SYSTEM]]
    
    # Sort by created_at ASC (chronological timeline)
    return sorted(filtered, key=lambda c: c.created_at)


def get_editor_permissions(
    agreement: Agreement,
    is_internal: bool = True
) -> tuple[bool, bool]:
    """
    Determine editor permissions based on agreement status and user role.
    
    Args:
        agreement: Agreement object
        is_internal: Whether user is internal
        
    Returns:
        Tuple of (can_edit, can_comment)
    """
    status = agreement.status
    
    # Check if any document is signed
    has_signed_document = False
    if hasattr(agreement, 'documents') and agreement.documents:
        has_signed_document = any(d.is_signed_version == 'true' for d in agreement.documents)
    
    if has_signed_document:
        return False, False  # Signed documents cannot be edited or commented
    
    # Status-based rules
    if status == AgreementStatus.DRAFT:
        # DRAFT: editable for internal only
        return is_internal, is_internal
    
    elif status == AgreementStatus.UNDER_REVIEW:
        # UNDER_REVIEW: editable for internal only
        return is_internal, is_internal
    
    elif status == AgreementStatus.UNDER_NEGOTIATION:
        # UNDER_NEGOTIATION: legacy status — treat same as UNDER_REVIEW
        # (negotiation now happens entirely within UNDER_REVIEW)
        return is_internal, is_internal

    elif status in [AgreementStatus.FULLY_SIGNED, AgreementStatus.REVIEWED_AND_SIGNED, AgreementStatus.READY_FOR_SIGNATURE, AgreementStatus.SENT_FOR_SIGNATURE, AgreementStatus.EXECUTED, AgreementStatus.CLOSED]:
        # All locked statuses: read-only
        return False, False
    
    # Default: no permissions
    return False, False


async def build_agreement_response(
    db: AsyncSession,
    agreement: Agreement,
    is_internal: bool = True,
    user_id: Optional[str] = None
) -> dict:
    """
    Helper function to build agreement response with role-based filtering and can_upload_new_version.

    GENERAL across agreement types — lifted here (next to its filter_comments_by_role /
    get_editor_permissions / get_agreement_permissions helpers) out of the legacy CDA
    routes so shared code no longer imports from a type module.

    Args:
        db: Database session
        agreement: Agreement object with loaded relationships
        is_internal: Whether user is internal (default True)
        user_id: Optional user ID for permission checks

    Returns:
        Dictionary ready for AgreementResponse schema
    """
    # Get documents (template-based)
    documents = list(agreement.documents) if hasattr(agreement, 'documents') and agreement.documents else []

    # Legacy file-based version system is no longer exposed at runtime; rely solely on documents.
    effective_is_legacy = agreement.is_legacy

    # No new legacy file uploads allowed
    can_upload = False

    # Filter comments by role and sort chronologically
    filtered_comments = filter_comments_by_role(list(agreement.comments), is_internal)

    # Get editor permissions (for backward compatibility)
    can_edit, can_comment = get_editor_permissions(agreement, is_internal)

    # Get comprehensive permission flags
    permissions = get_agreement_permissions(agreement, is_internal)

    # Get current document version number (latest version)
    current_document_version_number = None
    if documents:
        current_document_version_number = max(doc.version_number for doc in documents)

    signature_source = getattr(agreement.signature_source, "value", agreement.signature_source)
    signature_counts = await db.execute(
        select(
            AgreementInternalSignature.role,
            func.count(AgreementInternalSignature.id)
        )
        .where(AgreementInternalSignature.agreement_id == agreement.id)
        .group_by(AgreementInternalSignature.role)
    )
    counts_by_role = {role: count for role, count in signature_counts.all()}
    reviewer_signed = (counts_by_role.get("reviewer") or 0) > 0
    site_signed = (counts_by_role.get("site") or 0) > 0

    return {
        "id": agreement.id,
        "site_id": agreement.site_id,
        "title": agreement.title,
        "status": agreement.status.value,
        "created_by": agreement.created_by,
        "created_at": agreement.created_at,
        "updated_at": agreement.updated_at,
        "is_legacy": effective_is_legacy,
        "documents": [
            {
                "id": doc.id,
                "agreement_id": doc.agreement_id,
                "version_number": doc.version_number,
                "document_content": doc.document_content if hasattr(doc, 'document_content') and doc.document_content else {"type": "doc", "content": []},
                "document_file_path": doc.document_file_path if hasattr(doc, 'document_file_path') else None,
                "created_from_template_id": doc.created_from_template_id,
                "created_by": doc.created_by,
                "created_at": doc.created_at,
                "is_signed_version": doc.is_signed_version,
            }
            for doc in documents
        ],
        "comments": [
            {
                "id": comment.id,
                "agreement_id": comment.agreement_id,
                "version_id": comment.version_id,
                "comment_type": comment.comment_type.value,
                "content": comment.content,
                "created_by": comment.created_by,
                "created_at": comment.created_at,
            }
            for comment in filtered_comments
        ],
        "can_upload_new_version": can_upload,
        "can_edit": permissions["can_edit"],  # Use comprehensive permissions
        "can_comment": can_comment,
        "can_save": permissions["can_save"],
        "can_move_status": permissions["can_move_status"],
        "is_locked": permissions["is_locked"],
        "current_document_version_number": current_document_version_number,
        "zoho_request_id": agreement.zoho_request_id,
        "signature_status": agreement.signature_status,
        "signature_source": signature_source,
        "signing_stage": (
            "FULLY_SIGNED" if agreement.status == AgreementStatus.FULLY_SIGNED
            else "REVIEWED_AND_SIGNED" if agreement.status == AgreementStatus.REVIEWED_AND_SIGNED
            else "REVIEW_PENDING"
        ),
        "signing_progress": {
            "reviewerSigned": reviewer_signed,
            "siteSigned": site_signed,
        },
        "signed_documents": [
            {
                "id": doc.id,
                "agreement_id": doc.agreement_id,
                "file_path": doc.file_path,
                "signed_at": doc.signed_at,
                "downloaded_from_zoho_at": doc.downloaded_from_zoho_at,
                "zoho_request_id": doc.zoho_request_id,
            }
            for doc in (agreement.signed_documents if hasattr(agreement, 'signed_documents') and agreement.signed_documents else [])
        ],
    }


def get_agreement_permissions(
    agreement: Agreement,
    is_internal: bool = True
) -> dict:
    """
    Get comprehensive permission flags for an agreement based on status and user role.
    
    Args:
        agreement: Agreement object
        is_internal: Whether user is internal
        
    Returns:
        Dictionary with permission flags:
        - can_edit: Can edit document content
        - can_save: Can save document (create new version)
        - can_move_status: Can transition to next status
        - is_locked: Agreement is fully locked (no changes allowed)
    """
    status = agreement.status
    
    # Check if any document is signed
    has_signed_document = False
    if hasattr(agreement, 'documents') and agreement.documents:
        has_signed_document = any(d.is_signed_version == 'true' for d in agreement.documents)
    
    # "Locked" in the UI/permissions sense means "no further document edits/saves".
    # Status transitions may still be allowed even when the document is locked
    # (e.g. REVIEWED_AND_SIGNED → READY_FOR_SIGNATURE).
    locked_for_edit_statuses = {
        AgreementStatus.FULLY_SIGNED,
        AgreementStatus.REVIEWED_AND_SIGNED,
        AgreementStatus.READY_FOR_SIGNATURE,
        AgreementStatus.SENT_FOR_SIGNATURE,
        AgreementStatus.EXECUTED,
        AgreementStatus.CLOSED,
    }
    is_locked_for_edit = status in locked_for_edit_statuses or has_signed_document
    
    # Initialize permissions
    can_edit = False
    can_save = False
    can_move_status = False
    
    # Status-based rules
    if status == AgreementStatus.DRAFT:
        # DRAFT: editable for internal only
        can_edit = is_internal
        can_save = is_internal
        can_move_status = True  # Can move to UNDER_REVIEW
    
    elif status in (AgreementStatus.UNDER_REVIEW, AgreementStatus.UNDER_NEGOTIATION):
        # UNDER_REVIEW (and legacy UNDER_NEGOTIATION): editable for internal only.
        # Negotiation rounds happen entirely within this stage.
        # Allowed next status: READY_FOR_SIGNATURE (direct path to signature).
        can_edit = is_internal
        can_save = is_internal
        can_move_status = True  # Can move to READY_FOR_SIGNATURE
    
    elif status == AgreementStatus.FULLY_SIGNED:
        can_edit = False
        can_save = False
        can_move_status = True  # Can move to READY_FOR_SIGNATURE

    elif status == AgreementStatus.REVIEWED_AND_SIGNED:
        # REVIEWED_AND_SIGNED: locked after external reviewer approval
        can_edit = False
        can_save = False
        can_move_status = True  # Can move to READY_FOR_SIGNATURE

    elif status == AgreementStatus.READY_FOR_SIGNATURE:
        # READY_FOR_SIGNATURE: locked
        can_edit = False
        can_save = False
        can_move_status = True  # Can move to SENT_FOR_SIGNATURE
    
    elif status == AgreementStatus.SENT_FOR_SIGNATURE:
        # SENT_FOR_SIGNATURE: locked
        can_edit = False
        can_save = False
        can_move_status = False  # Final signature happens via OTP link; do not allow manual EXECUTED transition
    
    elif status == AgreementStatus.EXECUTED:
        # EXECUTED: permanently locked, no further changes or status transitions allowed
        can_edit = False
        can_save = False
        can_move_status = False  # Permanent lock - no status transitions allowed
    
    elif status == AgreementStatus.CLOSED:
        # CLOSED: fully locked, no transitions
        can_edit = False
        can_save = False
        can_move_status = False
    
    return {
        "can_edit": can_edit,
        "can_save": can_save,
        "can_move_status": can_move_status,
        "is_locked": is_locked_for_edit,
    }


async def change_agreement_status(
    db: AsyncSession,
    agreement_id: str,
    new_status: AgreementStatus,
    user_id: Optional[str] = None
) -> Agreement:
    """
    Centralized function to change agreement status with strict workflow validation.
    
    This function:
    1. Validates current status
    2. Checks if transition is allowed
    3. Enforces locking rules
    4. Updates status
    5. Creates SYSTEM comment
    
    Args:
        db: Database session
        agreement_id: Agreement UUID
        new_status: Desired new status
        user_id: User ID making the change (optional)
        
    Returns:
        Updated Agreement object
        
    Raises:
        ValueError: If transition is invalid or locked
    """
    # Get agreement with current status. selectinload(.documents) so the
    # downstream permission helpers (get_editor_permissions /
    # get_agreement_permissions) can iterate `.documents` to detect signed
    # versions without firing a lazy-load round-trip per call. Cheap to include
    # — typical agreements have a handful of documents.
    agreement_result = await db.execute(
        select(Agreement)
        .options(selectinload(Agreement.documents))
        .where(Agreement.id == agreement_id)
    )
    agreement = agreement_result.scalar_one_or_none()
    
    if not agreement:
        raise ValueError(f"Agreement {agreement_id} not found")
    
    logger.info(
        "Agreement %s loaded via study_site_id=%s (study=%s, site=%s)",
        agreement_id,
        getattr(agreement, "study_site_id", None),
        getattr(agreement, "study_id", None),
        getattr(agreement, "site_id", None),
    )
    
    current_status = agreement.status
    
    # Check if status change is allowed at all
    can_change, error_msg = can_change_status(current_status)
    if not can_change:
        raise ValueError(error_msg)
    
    # Validate transition
    if not is_transition_allowed(current_status, new_status):
        allowed_next = ALLOWED_TRANSITIONS.get(current_status, [])
        allowed_str = ", ".join([s.value for s in allowed_next]) if allowed_next else "none"
        raise ValueError(
            f"Invalid status transition: Cannot change from {current_status.value} to {new_status.value}. "
            f"Allowed transitions from {current_status.value}: {allowed_str}"
        )
    
    # Special locking rules for SENT_FOR_SIGNATURE.
    # Permitted onward transitions: EXECUTED (single-signer completion, e.g. CDA)
    # and AWAITING_SPONSOR_SIGNATURE (CTA's two-external-signers → sponsor step).
    # Both are already sanctioned by ALLOWED_TRANSITIONS and the CTA descriptor;
    # AWAITING_SPONSOR_SIGNATURE was previously (incorrectly) rejected here, which
    # broke CTA's second-external-signer commit. CDA/other types never request
    # AWAITING_SPONSOR_SIGNATURE, so this widening is inert for them.
    _SENT_ALLOWED = {AgreementStatus.EXECUTED, AgreementStatus.AWAITING_SPONSOR_SIGNATURE}
    if current_status == AgreementStatus.SENT_FOR_SIGNATURE:
        if new_status not in _SENT_ALLOWED:
            raise ValueError(
                f"Cannot change status from {current_status.value} to {new_status.value}. "
                f"Only transition to EXECUTED or AWAITING_SPONSOR_SIGNATURE is allowed."
            )
    
    # Store old status for comment
    old_status = current_status.value
    
    # Update status
    agreement.status = new_status
    await db.flush()
    
    # Create system comment for status change
    user_info = f" by {user_id}" if user_id else ""
    comment_content = f"Status changed from {old_status} to {new_status.value}{user_info}"
    
    comment = AgreementComment(
        agreement_id=agreement.id,
        version_id=None,  # version_id is None for status changes
        comment_type=CommentType.SYSTEM,
        content=comment_content,
        created_by=None  # System comments have no creator
    )
    db.add(comment)
    await db.flush()

    # Dispatch to the registered AgreementType handler (CDA, CTA, ...). Each
    # type's on_status_change hook runs inside the same transaction so its
    # side-effects (e.g. CDA's SiteWorkflowStep.CDA_EXECUTION completion) are
    # atomic with the status update. A hook crash is logged and swallowed —
    # one broken type must never roll back a generic status change. See
    # app/modules/agreements/registry.py for the hook contract.
    try:
        # Lazy import: app.modules.agreements.registry is populated by
        # aggregator.py at boot, so by the time a request reaches us the
        # type descriptors are already registered. The local import keeps
        # this service free of registry coupling at module load time.
        from app.modules.agreements.registry import get as _get_agreement_type

        agreement_type_code = getattr(agreement, "agreement_type", None)
        agreement_type_code = (
            agreement_type_code.value
            if hasattr(agreement_type_code, "value")
            else (str(agreement_type_code) if agreement_type_code else None)
        )
        descriptor = _get_agreement_type(agreement_type_code) if agreement_type_code else None
        if descriptor and descriptor.on_status_change:
            try:
                await descriptor.on_status_change(agreement, old_status, new_status, db)
                await db.flush()
            except Exception:  # noqa: BLE001 — see comment above
                logger.exception(
                    "AgreementType %s on_status_change hook failed for agreement %s",
                    descriptor.code,
                    agreement_id,
                )
    except Exception:  # noqa: BLE001 — registry lookup itself must never break status change
        logger.exception("Agreement type registry dispatch failed for agreement %s", agreement_id)

    # (The legacy per-type workflow-engine status mirror — gated on the removed
    # WORKFLOW_DRIVES_CDA/_CTA flags — was deleted. The unified path advances its
    # workflow instance via the engine directly, not by mirroring agreement status.)

    await db.commit()
    await db.refresh(agreement)

    # Surface the status change on the per-(study, site) Public Notice Board.
    # Mirrors the existing `create_agreement_notice` call sites at create /
    # signing / review time so the activity feed isn't blank between those
    # bookend events. Wrapped in try because a notice-board failure must
    # never undo the committed status update.
    try:
        agreement_type_code = getattr(agreement, "agreement_type", None)
        agreement_type_code = (
            agreement_type_code.value
            if hasattr(agreement_type_code, "value")
            else (str(agreement_type_code) if agreement_type_code else "agreement")
        )
        notice_msg = (
            f"{agreement_type_code.upper()} '{agreement.title or agreement.id}' "
            f"status changed from {old_status} to {new_status.value}"
        )
        if user_id:
            notice_msg += f" by {user_id}"
        await create_agreement_notice(
            db,
            agreement,
            event_type="agreement_status_changed",
            message=notice_msg,
            metadata={
                "agreement_id": str(agreement.id),
                "agreement_type": agreement_type_code,
                "old_status": old_status,
                "new_status": new_status.value,
            },
        )
    except Exception:
        logger.exception(
            "change_agreement_status: notice-board hook failed for agreement %s",
            agreement_id,
        )

    logger.info(
        f"Agreement {agreement_id} status changed from {old_status} to {new_status.value} "
        f"(user: {user_id or 'system'})"
    )

    return agreement


async def create_agreement_notice(
    db: AsyncSession,
    agreement: Agreement,
    event_type: str,
    message: str,
    metadata: Optional[Dict] = None,
) -> None:
    """
    Central helper to create Public Notice Board entries for agreement events.

    Resolves Study + Site context and calls create_system_notice_message.
    """
    # Resolve site
    site_result = await db.execute(select(Site).where(Site.id == agreement.site_id))
    site = site_result.scalar_one_or_none()
    if not site:
        logger.warning("create_agreement_notice: site not found for agreement %s", agreement.id)
        return

    site_id_str = site.site_id if hasattr(site, "site_id") else str(site.id)

    # Resolve study via Agreement or StudySite
    study_id_str: Optional[str] = None
    if getattr(agreement, "study_id", None):
        study_result = await db.execute(select(Study).where(Study.id == agreement.study_id))
        study = study_result.scalar_one_or_none()
        if study:
            study_id_str = str(study.id)
    elif getattr(agreement, "study_site_id", None):
        study_site_result = await db.execute(
            select(StudySite).where(StudySite.id == agreement.study_site_id)
        )
        study_site = study_site_result.scalar_one_or_none()
        if study_site:
            study_result = await db.execute(select(Study).where(Study.id == study_site.study_id))
            study = study_result.scalar_one_or_none()
            if study:
                study_id_str = str(study.id)

    try:
        await create_system_notice_message(
            db=db,
            site_id=site_id_str,
            study_id=study_id_str,
            message=message,
            created_by=None,
            metadata=metadata or {},
            event_type=event_type,
        )
        logger.info(
            "Created agreement notice: agreement_id=%s, site_id=%s, study_id=%s, event_type=%s",
            str(agreement.id),
            site_id_str,
            study_id_str,
            event_type,
        )
    except Exception as e:
        logger.error(
            "Failed to create agreement notice for agreement_id=%s: %s",
            str(agreement.id),
            e,
            exc_info=True,
        )

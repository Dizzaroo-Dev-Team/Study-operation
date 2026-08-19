"""
Agreement Document Comments API
================================
REST endpoints for the review-comment workflow.

Site users add comments directly inside OnlyOffice (comment-only mode).
Comments are extracted from the saved DOCX when the OnlyOffice callback fires
and stored in the agreement_document_comments table.

Internal users call these endpoints to:
  - GET  /agreements/{id}/comments              – list all comments + replies
  - POST /agreements/{id}/comments/{cid}/reply  – add an internal reply
  - PUT  /agreements/{id}/comments/{cid}/status – set accepted/rejected/modified
  - GET  /agreements/{id}/comments/{cid}        – fetch a single comment

These endpoints do NOT touch any existing table (agreements, agreement_documents,
agreement_review_tokens, agreement_review_documents, agreement_changes).

IMPORTANT — CORS / exception safety
-------------------------------------
Every endpoint wraps its DB work in a try/except and always returns a JSONResponse
(never lets a raw SQLAlchemy exception propagate to the ASGI boundary).
This guarantees that Starlette's CORSMiddleware always has a Response object to
attach the Access-Control-Allow-Origin header to, even when the DB is unavailable
or the migration has not yet run.
"""

import asyncio
import uuid
import logging
from pathlib import Path
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.auth import get_current_user_optional
from app.utils.log_sanitize import sfmt
from app.models import (
    Agreement,
    AgreementDocumentComment,
    AgreementReviewDocument,
    CommentStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter()

# ── CORS-safe error response helper ──────────────────────────────────────────
# Return a JSONResponse (not raise an exception) so CORSMiddleware can still
# inject Access-Control-Allow-Origin into the response.

def _err(status: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"detail": detail})


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class CommentReplyCreate(BaseModel):
    reply_text: str
    author_name: Optional[str] = "Internal Reviewer"


class CommentStatusUpdate(BaseModel):
    status: str  # pending | accepted | rejected | modified


# ── Helpers ───────────────────────────────────────────────────────────────────

def _serialize_comment(c: AgreementDocumentComment) -> dict:
    """Convert an ORM row to a JSON-safe dict."""
    return {
        "id":                str(c.id),
        "comment_id":        c.comment_id,
        "review_document_id": str(c.review_document_id) if c.review_document_id else None,
        "agreement_id":      str(c.agreement_id),
        "author_email":      c.author_email,
        "comment_text":      c.comment_text,
        "referenced_text":   c.referenced_text or "",
        "oo_date":           c.oo_date,
        "status":            c.status,
        "parent_comment_id": str(c.parent_comment_id) if c.parent_comment_id else None,
        "is_internal_reply": c.is_internal_reply == "true",
        "created_at":        c.created_at.isoformat() if c.created_at else None,
        "updated_at":        c.updated_at.isoformat() if c.updated_at else None,
    }


def _write_review_temp_docx(data: bytes) -> str:
    """Write ``data`` to a NamedTemporaryFile(delete=False, suffix='.docx') and
    return its path. Sync on purpose — called via asyncio.to_thread so the
    blocking file I/O stays off the event loop."""
    import tempfile as _re_tmp
    _re_temp = _re_tmp.NamedTemporaryFile(delete=False, suffix=".docx")
    _re_temp.write(data)
    _re_temp.close()
    return _re_temp.name


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/agreements/{agreement_id}/comments")
async def list_agreement_comments(
    agreement_id: uuid.UUID,
    review_document_id: Optional[str] = Query(None, description="Filter by specific review document"),
    include_replies: bool = Query(True, description="Include reply comments"),
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    List all comments for an agreement.

    Returns top-level site comments together with their internal replies,
    ordered by created_at ascending.

    Accessible without authentication so that the public review page can also
    fetch the comment thread (replies + statuses are visible to site users).
    """
    try:
        # Base query: all comments for this agreement
        stmt = (
            select(AgreementDocumentComment)
            .where(AgreementDocumentComment.agreement_id == agreement_id)
            .order_by(AgreementDocumentComment.created_at.asc())
        )

        if review_document_id:
            try:
                stmt = stmt.where(
                    AgreementDocumentComment.review_document_id == uuid.UUID(review_document_id)
                )
            except ValueError:
                return _err(400, "Invalid review_document_id UUID")

        if not include_replies:
            stmt = stmt.where(AgreementDocumentComment.parent_comment_id.is_(None))

        result = await db.execute(stmt)
        rows = result.scalars().all()

        # Build a nested structure: top-level comments with replies embedded
        top_level = [c for c in rows if c.parent_comment_id is None]
        replies_map: dict = {}
        for c in rows:
            if c.parent_comment_id:
                key = str(c.parent_comment_id)
                replies_map.setdefault(key, []).append(_serialize_comment(c))

        serialized = []
        for c in top_level:
            s = _serialize_comment(c)
            s["replies"] = replies_map.get(str(c.id), [])
            serialized.append(s)

        return JSONResponse(content={"comments": serialized, "total": len(rows)})

    except SQLAlchemyError as exc:
        # FAIL LOUD. Returning an empty 200 here used to make a missing table /
        # missing constraint indistinguishable from "no comments", silently hiding
        # every review comment (the deployed failure mode). A failure to LOAD
        # comments is a server error the caller MUST see — never an empty success.
        msg = str(exc).splitlines()[0]
        logger.exception("list_agreement_comments DB error for %s: %s", agreement_id, msg)
        if "does not exist" in msg.lower() or "undefined" in msg.lower():
            return _err(
                503,
                "Comments storage is not initialised (schema/migration pending). "
                "This is a server configuration problem, not an empty thread.",
            )
        return _err(503, "Database error loading comments")
    except Exception as exc:
        logger.error("list_agreement_comments unexpected error: %s", exc, exc_info=True)
        return _err(500, "Unexpected error loading comments")


@router.get("/agreements/{agreement_id}/comments/{comment_pk}")
async def get_comment(
    agreement_id: uuid.UUID,
    comment_pk: uuid.UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """Fetch a single comment by its UUID primary key."""
    try:
        result = await db.execute(
            select(AgreementDocumentComment)
            .where(AgreementDocumentComment.id == comment_pk)
            .where(AgreementDocumentComment.agreement_id == agreement_id)
        )
        comment = result.scalar_one_or_none()
        if not comment:
            return _err(404, "Comment not found")
        return JSONResponse(content=_serialize_comment(comment))
    except SQLAlchemyError as exc:
        logger.warning("get_comment DB error: %s", str(exc).splitlines()[0])
        return _err(503, "Database error fetching comment")
    except Exception as exc:
        logger.error("get_comment unexpected error: %s", exc, exc_info=True)
        return _err(500, "Unexpected error")


@router.post("/agreements/{agreement_id}/comments/{comment_pk}/reply")
async def reply_to_comment(
    agreement_id: uuid.UUID,
    comment_pk: uuid.UUID,
    body: CommentReplyCreate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Add an internal reply to an existing site comment.

    Creates a new AgreementDocumentComment row that is linked to the parent via
    parent_comment_id.  The reply is flagged as is_internal_reply='true' so the
    frontend can render it differently.

    Only authenticated internal users should call this endpoint.
    """
    try:
        if not body.reply_text or not body.reply_text.strip():
            return _err(400, "reply_text cannot be empty")

        # Verify parent comment exists and belongs to this agreement
        parent_result = await db.execute(
            select(AgreementDocumentComment)
            .where(AgreementDocumentComment.id == comment_pk)
            .where(AgreementDocumentComment.agreement_id == agreement_id)
        )
        parent = parent_result.scalar_one_or_none()
        if not parent:
            return _err(404, "Parent comment not found")

        # Determine author
        author = body.author_name or "Internal Reviewer"
        if current_user:
            author = (
                current_user.get("name")
                or current_user.get("email")
                or author
            )

        # Generate a synthetic comment_id for this internal reply
        # (no OOXML backing – it's a CRM-side entity)
        synthetic_id = f"internal-{uuid.uuid4()}"

        reply = AgreementDocumentComment(
            comment_id=synthetic_id,
            review_document_id=parent.review_document_id,
            agreement_id=agreement_id,
            author_email=author,
            comment_text=body.reply_text.strip(),
            referenced_text=None,
            oo_date=datetime.now(timezone.utc).isoformat(),
            status=CommentStatus.PENDING,
            parent_comment_id=parent.id,
            is_internal_reply="true",
        )
        db.add(reply)
        await db.commit()
        await db.refresh(reply)

        logger.info(
            "Internal reply added to comment %s for agreement %s by %s",
            sfmt(comment_pk), sfmt(agreement_id), sfmt(author),
        )
        return JSONResponse(status_code=201, content=_serialize_comment(reply))

    except SQLAlchemyError as exc:
        await db.rollback()
        logger.warning("reply_to_comment DB error: %s", str(exc).splitlines()[0])
        return _err(503, "Database error saving reply")
    except Exception as exc:
        logger.error("reply_to_comment unexpected error: %s", exc, exc_info=True)
        return _err(500, "Unexpected error")


@router.put("/agreements/{agreement_id}/comments/{comment_pk}/status")
async def update_comment_status(
    agreement_id: uuid.UUID,
    comment_pk: uuid.UUID,
    body: CommentStatusUpdate,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Set the resolution status of a comment.

    Allowed values: pending | accepted | rejected | modified

    Only internal users should call this endpoint.
    """
    try:
        allowed = {"pending", "accepted", "rejected", "modified"}
        if body.status not in allowed:
            return _err(400, f"Invalid status '{body.status}'. Must be one of: {', '.join(sorted(allowed))}")

        result = await db.execute(
            select(AgreementDocumentComment)
            .where(AgreementDocumentComment.id == comment_pk)
            .where(AgreementDocumentComment.agreement_id == agreement_id)
        )
        comment = result.scalar_one_or_none()
        if not comment:
            return _err(404, "Comment not found")

        old_status = comment.status
        comment.status = body.status
        comment.updated_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(comment)

        logger.info(
            "Comment %s status changed %s → %s for agreement %s",
            comment_pk, old_status, body.status, agreement_id,
        )
        return JSONResponse(content=_serialize_comment(comment))

    except SQLAlchemyError as exc:
        await db.rollback()
        logger.warning("update_comment_status DB error: %s", str(exc).splitlines()[0])
        return _err(503, "Database error updating status")
    except Exception as exc:
        logger.error("update_comment_status unexpected error: %s", exc, exc_info=True)
        return _err(500, "Unexpected error")


# ── Re-extract comments from saved DOCX ──────────────────────────────────────

@router.post("/agreements/{agreement_id}/re-extract-comments")
async def re_extract_comments(
    agreement_id: uuid.UUID,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
):
    """
    Re-run comment extraction from the saved review DOCX for an agreement.

    Useful when the referenced_text field is empty for a comment because the
    extractor was improved after the comment was first saved.

    Internal users only.
    """
    if not current_user:
        return _err(401, "Authentication required")

    try:
        # Load the agreement
        ag_res = await db.execute(
            select(Agreement).where(Agreement.id == agreement_id)
        )
        agreement = ag_res.scalar_one_or_none()
        if not agreement:
            return _err(404, "Agreement not found")

        # Find the active review document
        rd_res = await db.execute(
            select(AgreementReviewDocument)
            .where(AgreementReviewDocument.agreement_id == agreement_id)
            .order_by(AgreementReviewDocument.created_at.desc())
        )
        review_doc = rd_res.scalars().first()
        if not review_doc:
            return _err(404, "No review document found for this agreement")

        docx_path = getattr(review_doc, "review_file_path", None)
        if not docx_path:
            return _err(404, "Review document file not found")

        _re_temp_path = None
        from app.utils.azure_storage import get_document_storage as _gds_re
        _re_storage = _gds_re()
        if _re_storage and docx_path.startswith("agreement_reviews/"):
            _re_bytes = await _re_storage.download_file(docx_path)
            if not _re_bytes:
                return _err(404, "Review document not found in Azure")
            _re_temp_path = await asyncio.to_thread(_write_review_temp_docx, _re_bytes)
            docx_path = _re_temp_path
        elif not Path(docx_path).exists():
            return _err(404, "Review document file not found on disk")

        from app.modules.agreements.routes.signing import _upsert_comments_from_docx

        try:
            count = await _upsert_comments_from_docx(
                db=db,
                agreement_id=agreement_id,
                review_document=review_doc,
                docx_path=str(docx_path),
            )
        finally:
            if _re_temp_path and Path(_re_temp_path).exists():
                import os
                os.unlink(_re_temp_path)

        return JSONResponse(content={"extracted": count, "status": "ok"})

    except SQLAlchemyError as exc:
        await db.rollback()
        logger.warning("re_extract_comments DB error: %s", str(exc).splitlines()[0])
        return _err(503, "Database error during re-extraction")
    except Exception as exc:
        logger.error("re_extract_comments unexpected error: %s", exc, exc_info=True)
        return _err(500, "Unexpected error during re-extraction")

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..core.database import get_database
from ..services.tmf_kafka_service import route_document_to_tmf
from ..utils.auth import get_current_user


router = APIRouter(prefix="/tmf", tags=["TMF Routing"])


class TMFSendRequest(BaseModel):
    documentId: str
    studyId: Optional[str] = None
    studyNumber: Optional[str] = None
    # Retained for backward compatibility with older clients; no longer used
    # (documents route via Kafka now, not email).
    tmfEmail: Optional[str] = None


@router.post("/send")
async def tmf_send(
    payload: TMFSendRequest,
    db=Depends(get_database),
    current_user=Depends(get_current_user),
):
    """
    Route an ISF document to the TMF repository by publishing its full Mongo
    payload onto the Data Platform ``platform.documents`` Kafka topic.

    The frontend passes:
      - documentId: ISF document identifier
      - studyId / studyNumber: optional study context

    The authenticated user's id is forwarded as ``payload.created_by`` for
    provenance (omitted for the anonymous fallback user).
    """
    # get_current_user degrades to an anonymous placeholder without a valid
    # token — don't record that as provenance.
    created_by = None
    if current_user is not None and current_user.id != "crm-anonymous":
        created_by = current_user.id

    ok = await route_document_to_tmf(
        db=db,
        document_id=payload.documentId,
        study_id=payload.studyId,
        study_number=payload.studyNumber,
        created_by=created_by,
    )
    if not ok:
        raise HTTPException(status_code=502, detail="Failed to publish document to TMF (Kafka)")

    return {"success": True}

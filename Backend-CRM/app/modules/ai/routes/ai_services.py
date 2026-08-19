from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Header, Query, UploadFile, File, Form, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_, and_, delete, update
from sqlalchemy.orm import selectinload
from typing import Optional, List
from uuid import UUID
from datetime import timedelta, datetime, timezone
import asyncio
import os
import hashlib
import shutil
from pathlib import Path
import secrets
from app.db import get_db, init_db
from app import crud, schemas
from app.models import MessageDirection, MessageStatus, MessageChannel, ConversationAccessLevel, ThreadAttachment, Attachment, Conversation, ChatDocument, PrimarySiteStatus, UserRoleAssignment, Site, Study, StudySite, SiteStatus, SiteWorkflowStep, SiteDocument, WorkflowStepName, StepStatus, DocumentCategory, DocumentType, ReviewStatus, ProjectFeasibilityCustomQuestion, FeasibilityRequest, FeasibilityResponse, FeasibilityRequestStatus, FeasibilityAttachment
from app.websocket_manager import manager
from app.config import settings
from app.auth import create_access_token, get_password_hash, get_current_user, get_current_user_optional, ACCESS_TOKEN_EXPIRE_MINUTES
from app.modules.sites.services.site_status_service import (
    get_study_status_summary,
    get_country_site_counts,
    get_sites_by_status,
    get_site_status_detail,
)
from app.integrations.ai import ai_service
import uuid
import logging
# Tasks imported where needed to avoid circular imports


router = APIRouter(tags=["AI"])
logger = logging.getLogger(__name__)

@router.get("/health/ai")
async def health_ai():
    """Check AI service health and configuration."""
    api_key_configured = bool(settings.gemini_api_key)
    ai_available = ai_service.is_available()
    model_info = "not initialized"
    init_error = None

    if ai_service.model:
        try:
            model_info = ai_service.model_name or "initialized"
        except:
            model_info = "initialized (unknown model name)"

    if hasattr(ai_service, '_init_error') and ai_service._init_error:
        init_error = ai_service._init_error

    # Debug info
    debug_info = {
        "api_key_configured": api_key_configured,
        "api_key_length": len(settings.gemini_api_key) if settings.gemini_api_key else 0,
        "api_key_preview": f"{settings.gemini_api_key[:10]}...{settings.gemini_api_key[-5:]}" if settings.gemini_api_key else None,
        "ai_service_available": ai_available,
        "model_info": model_info,
        "model_is_none": ai_service.model is None,
        "initialized": ai_service._initialized if hasattr(ai_service, '_initialized') else False,
        "init_error": init_error,
        "stored_api_key": f"{ai_service.api_key[:10]}...{ai_service.api_key[-5:]}" if ai_service.api_key else None
    }

    return debug_info


@router.get("/health/ai/test")
async def test_ai_api_key():
    """Test the API key with a direct Gemini API call."""
    import google.generativeai as genai
    import asyncio

    api_key = settings.gemini_api_key
    if not api_key:
        return {
            "success": False,
            "error": "API key not configured",
            "api_key_preview": None
        }

    try:
        # Configure and test using old SDK
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-3.5-flash')

        # Make a test call
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: model.generate_content("Say 'OK' in JSON: {\"status\": \"ok\"}")
        )

        if response and hasattr(response, 'text'):
            return {
                "success": True,
                "message": "API key is working!",
                "response_preview": response.text[:100],
                "api_key_preview": f"{api_key[:10]}...{api_key[-5:]}"
            }
        else:
            return {
                "success": False,
                "error": "API call returned no response",
                "api_key_preview": f"{api_key[:10]}...{api_key[-5:]}"
            }
    except Exception as e:
        error_msg = str(e)
        return {
            "success": False,
            "error": error_msg,
            "error_type": type(e).__name__,
            "api_key_preview": f"{api_key[:10]}...{api_key[-5:]}" if api_key else None
        }


@router.post("/ai/compose-reply", response_model=schemas.AIComposeReplyResponse)
async def ai_compose_reply(
    payload: schemas.AIComposeReplyRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """AI compose‑assist for conversations or threads."""
    if not ai_service.is_available():
        api_key_status = "configured" if settings.gemini_api_key else "not configured"
        raise HTTPException(
            status_code=503,
            detail=f"AI service is not available. GEMINI_API_KEY is {api_key_status}. Please check your .env file.",
        )

    if not payload.conversation_id and not payload.thread_id:
        raise HTTPException(status_code=400, detail="conversation_id or thread_id is required")

    try:
        history_text = ""

        if payload.conversation_id:
            # Access check if user is authenticated
            if current_user:
                user_id = current_user.get("user_id")
                access_type = await crud.check_user_access(db, payload.conversation_id, user_id)
                if access_type is None:
                    raise HTTPException(status_code=403, detail="You don't have access to this conversation")

            conv = await crud.get_conversation_with_messages(db, payload.conversation_id, limit=200, offset=0)
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found")

            messages = conv.get("messages", []) if isinstance(conv, dict) else conv.messages
            if not messages:
                raise HTTPException(status_code=400, detail="No messages found in conversation. Cannot generate reply drafts.")
            # For compose‑reply we rely purely on the actual message history
            # to avoid leaking stale subject lines from older contexts.
            history_text = ai_service._format_messages_for_summary(messages)  # type: ignore[attr-defined]
            if not history_text or not history_text.strip():
                raise HTTPException(status_code=400, detail="No message history available. Cannot generate reply drafts.")

        elif payload.thread_id:
            thread = await crud.get_thread_with_messages(db, payload.thread_id, limit=200, offset=0)
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")

            messages = thread.get("messages", []) if isinstance(thread, dict) else thread.messages
            if not messages:
                raise HTTPException(status_code=400, detail="No messages found in thread. Cannot generate reply drafts.")
            history_text = ai_service._format_thread_messages_for_summary(messages)  # type: ignore[attr-defined]
            if not history_text or not history_text.strip():
                raise HTTPException(status_code=400, detail="No message history available. Cannot generate reply drafts.")

        result = await ai_service.compose_reply(history_text=history_text, latest_draft=payload.latest_draft)
        if not result:
            raise HTTPException(status_code=500, detail="Failed to generate AI drafts")

        return schemas.AIComposeReplyResponse(
            drafts=schemas.AIComposeReplyDrafts(**result["drafts"]),
            summary=result["summary"],
            facts=result["facts"],
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in ai_compose_reply: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error generating AI reply drafts: {str(e)}")


@router.post("/ai/check-message", response_model=schemas.AICheckMessageResponse)
async def ai_check_message(
    payload: schemas.AICheckMessageRequest,
    current_user: Optional[dict] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db)
):
    """AI pre‑send check for a draft message."""
    if not ai_service.is_available():
        api_key_status = "configured" if settings.gemini_api_key else "not configured"
        raise HTTPException(
            status_code=503,
            detail=f"AI service is not available. GEMINI_API_KEY is {api_key_status}. Please check your .env file.",
        )

    if not payload.conversation_id and not payload.thread_id:
        raise HTTPException(status_code=400, detail="conversation_id or thread_id is required")

    try:
        history_text = ""

        if payload.conversation_id:
            # Access check if user is authenticated
            if current_user:
                user_id = current_user.get("user_id")
                access_type = await crud.check_user_access(db, payload.conversation_id, user_id)
                if access_type is None:
                    raise HTTPException(status_code=403, detail="You don't have access to this conversation")

            conv = await crud.get_conversation_with_messages(db, payload.conversation_id, limit=50, offset=0)
            if not conv:
                raise HTTPException(status_code=404, detail="Conversation not found")
            messages = conv.get("messages", []) if isinstance(conv, dict) else conv.messages
            messages_text = ai_service._format_messages_for_summary(messages)  # type: ignore[attr-defined]
            history_text = messages_text

        elif payload.thread_id:
            thread = await crud.get_thread_with_messages(db, payload.thread_id, limit=50, offset=0)
            if not thread:
                raise HTTPException(status_code=404, detail="Thread not found")
            messages = thread.get("messages", []) if isinstance(thread, dict) else thread.messages
            messages_text = ai_service._format_thread_messages_for_summary(messages)  # type: ignore[attr-defined]
            history_text = messages_text

        result = await ai_service.check_message_before_send(
            context_text=history_text,
            draft_body=payload.draft_body,
            attachments=payload.attachments or [],
        )
        if not result:
            # If AI is unavailable at runtime, allow send with no issues
            return schemas.AICheckMessageResponse(issues=[], okToSend=True)

        issues = [schemas.AICheckMessageIssue(**issue) for issue in result.get("issues", [])]
        ok_to_send = bool(result.get("okToSend"))
        return schemas.AICheckMessageResponse(issues=issues, okToSend=ok_to_send)
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in ai_check_message: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error checking message before send: {str(e)}")

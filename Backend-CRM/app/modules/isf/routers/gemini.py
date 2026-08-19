from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from typing import Dict, Any, Optional

from ..models.user import UserResponse
from ..core.database import get_database
from ..services.gemini_service import GeminiService
from ..utils.auth import get_current_user

router = APIRouter()

def get_gemini_service():
    return GeminiService()

@router.post("/classify-content")
async def classify_content(
    file: UploadFile = File(...),
    payload: Optional[str] = Form(None),
    document_type: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    service: GeminiService = Depends(get_gemini_service)
):
    """Classify content using Gemini AI"""
    try:
        # Read file content
        content = await file.read()
        
        # Parse validation data from payload if provided
        validation_data = {}
        if payload:
            try:
                import json
                validation_data = json.loads(payload)
            except json.JSONDecodeError:
                pass  # Ignore invalid JSON
        
        # Classify content
        classification = await service.classify_document(
            content=content,
            filename=file.filename,
            mime_type=file.content_type,
            document_type=document_type
        )
        
        return {
            "success": True,
            "classification": classification,
            "validation_data": validation_data
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/classify-document")
async def classify_document(
    file: UploadFile = File(...),
    document_type: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    service: GeminiService = Depends(get_gemini_service)
):
    """Classify document using Gemini AI"""
    try:
        # Read file content
        content = await file.read()
        
        # Classify document
        classification = await service.classify_document(
            content=content,
            filename=file.filename,
            mime_type=file.content_type,
            document_type=document_type
        )
        
        return classification
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to classify document: {str(e)}"
        )

@router.post("/extract-metadata")
async def extract_metadata(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    service: GeminiService = Depends(get_gemini_service)
):
    """Extract metadata from document using Gemini AI"""
    try:
        # Read file content
        content = await file.read()
        
        # Extract metadata
        metadata = await service.extract_metadata(
            content=content,
            filename=file.filename,
            mime_type=file.content_type
        )
        
        return metadata
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract metadata: {str(e)}"
        )

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from typing import Dict, Any, List, Optional

from ..models.user import UserResponse
from ..core.database import get_database
from ..services.validation_service import ValidationService
from ..utils.auth import get_current_user

router = APIRouter()

def get_validation_service():
    return ValidationService()

@router.post("/validate-file")
async def validate_file(
    file: UploadFile = File(...),
    document_type: Optional[str] = None,
    current_user: UserResponse = Depends(get_current_user),
    service: ValidationService = Depends(get_validation_service)
):
    """Validate uploaded file"""
    try:
        # Read file content
        content = await file.read()
        
        # Validate file
        validation_result = service.validate_document(
            content=content,
            filename=file.filename,
            mime_type=file.content_type,
            document_type=document_type
        )
        
        return validation_result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to validate file: {str(e)}"
        )

@router.post("/validate-upload/virus-scan")
async def virus_scan(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    service: ValidationService = Depends(get_validation_service)
):
    """Perform virus scan on uploaded file"""
    try:
        # Read file content
        content = await file.read()
        
        # Perform virus scan
        scan_result = await service.perform_virus_scan(
            content=content,
            filename=file.filename,
            mime_type=file.content_type
        )
        
        # Return response in the format expected by frontend
        return {
            "success": True,
            "virusScan": scan_result
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/validate-upload/format-validation")
async def format_validation(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    service: ValidationService = Depends(get_validation_service)
):
    """Perform format validation on uploaded file"""
    try:
        # Read file content
        content = await file.read()
        
        # Perform format validation
        validation_result = service.validate_document(
            content=content,
            filename=file.filename,
            mime_type=file.content_type
        )
        
        # Return response in the format expected by frontend
        return {
            "success": True,
            "generalValidation": {
                "isValid": validation_result["is_valid"],
                "status": "VALID" if validation_result["is_valid"] else "INVALID",
                "notes": validation_result["validation_summary"],
                "warnings": []
            },
            "mimeValidation": {
                "isValid": True,
                "detectedType": file.content_type,
                "expectedTypes": ["application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"]
            },
            "warnings": []
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.post("/validate-upload/phi-detection")
async def phi_detection(
    file: UploadFile = File(...),
    current_user: UserResponse = Depends(get_current_user),
    service: ValidationService = Depends(get_validation_service)
):
    """Perform PHI detection on uploaded file"""
    try:
        # Read file content
        content = await file.read()
        
        # Perform PHI detection
        phi_result = await service.perform_phi_detection(
            content=content,
            filename=file.filename,
            mime_type=file.content_type
        )
        
        # Return response in the format expected by frontend
        return {
            "success": True,
            "fileName": file.filename,
            "stage": "phi-detection",
            "phiDetection": phi_result
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

from fastapi import APIRouter, Depends, HTTPException, status, Request
from typing import List, Optional, Dict, Any

from ..models.user import UserResponse
from ..core.database import get_database
from ..services.isf_workflow_service import ISFWorkflowService
from ..utils.auth import get_current_user

router = APIRouter()

def get_workflow_service():
    return ISFWorkflowService()

def _workflow_response(workflow, message: str = "Workflow loaded"):
    """Match Node.js response: { success: true, message, data: workflow }."""
    return {"success": True, "message": message, "data": workflow}

@router.get("/{document_id}/workflow")
async def get_document_workflow(
    document_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_database),
    service: ISFWorkflowService = Depends(get_workflow_service)
):
    """Get document workflow. Creates workflow if missing (same as Node)."""
    try:
        workflow = await service.get_workflow(db, document_id, current_user.id)
        if not workflow:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Workflow not found for this document"
            )
        return _workflow_response(workflow, "Workflow loaded")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve workflow: {str(e)}"
        )

@router.post("/{document_id}/workflow/initialize")
async def initialize_workflow(
    document_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_database),
    service: ISFWorkflowService = Depends(get_workflow_service)
):
    """Initialize document workflow. Returns { success, message, data: { workflow, auditTrail } } like Node."""
    try:
        data = await service.initialize_workflow(db, document_id, current_user.id)
        return {"success": True, "message": "Workflow initialized", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initialize workflow: {str(e)}"
        )

@router.post("/{document_id}/workflow/intake")
async def update_intake_workflow(
    document_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_database),
    service: ISFWorkflowService = Depends(get_workflow_service)
):
    """Update intake workflow stage."""
    try:
        payload = await request.json()
        data = await service.update_intake_workflow(db, document_id, payload, current_user.id)
        return {"success": True, "message": "Intake workflow updated", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update intake workflow: {str(e)}"
        )


@router.post("/{document_id}/workflow/qc-validation")
async def update_qc_validation_workflow(
    document_id: str,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_database),
    service: ISFWorkflowService = Depends(get_workflow_service)
):
    """Update QC Validation workflow stage."""
    try:
        payload = await request.json()
        data = await service.update_qc_validation_workflow(db, document_id, payload, current_user.id)
        return {"success": True, "message": "QC Validation updated", "data": data}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update QC Validation: {str(e)}"
        )

from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional

from ..models.user import UserResponse
from ..core.database import get_database
from ..services.isf_reference_service import ISFReferenceService
from ..utils.auth import get_current_user

router = APIRouter()

def get_reference_service():
    return ISFReferenceService()

@router.get("/zones")
async def get_zones(
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_database),
    service: ISFReferenceService = Depends(get_reference_service)
):
    """Get all ISF zones"""
    try:
        zones = await service.get_zones(db)
        return zones
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve zones: {str(e)}"
        )

@router.get("/zones/{zone_id}/sections")
async def get_sections_by_zone(
    zone_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_database),
    service: ISFReferenceService = Depends(get_reference_service)
):
    """Get sections by zone ID"""
    try:
        sections = await service.get_sections_by_zone(db, zone_id)
        return sections
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve sections: {str(e)}"
        )


@router.get("/hierarchy")
async def get_tmf_hierarchy(
    current_user: UserResponse = Depends(get_current_user),
    db=Depends(get_database),
    service: ISFReferenceService = Depends(get_reference_service),
):
    """Get full TMF reference hierarchy (zones → sections → artifacts → subartifacts)."""
    try:
        return await service.get_hierarchy(db)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve TMF hierarchy: {str(e)}",
        )

"""sites HTTP route layer - sites + IRBs + IRB requirements + site-IRB mapping."""
from __future__ import annotations

from fastapi import APIRouter

from .sites import router as _sites_router
from .irbs import router as _irbs_router
from .irb_requirements import router as _irb_requirements_router
from .irb_administrative_info import router as _irb_administrative_info_router
from .site_irb_mapping import router as _site_irb_mapping_router
from .site_staff import router as _site_staff_router

router = APIRouter()
router.include_router(_sites_router)
router.include_router(_irbs_router)
router.include_router(_irb_requirements_router)
router.include_router(_irb_administrative_info_router)
router.include_router(_site_irb_mapping_router)
router.include_router(_site_staff_router)

__all__ = ["router"]

"""clinical_workflow HTTP route layer — aggregator router."""
from __future__ import annotations

from fastapi import APIRouter

from .feasibility_questionnaire import router as _feasibility_questionnaire_router
from .feasibility_requests import router as _feasibility_requests_router
from .site_status import router as _site_status_router
from .sites import router as _sites_router
from .workflow_steps import router as _workflow_steps_router

router = APIRouter(tags=["Clinical Workflow"])
router.include_router(_site_status_router)
router.include_router(_sites_router)
router.include_router(_workflow_steps_router)
router.include_router(_feasibility_questionnaire_router)
router.include_router(_feasibility_requests_router)

__all__ = ["router"]

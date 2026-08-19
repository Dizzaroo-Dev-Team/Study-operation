"""
Site Budgeting parent router (aggregator).

All endpoints for /api/budgeting/* used to live in this one file (3,065 lines,
59 endpoints). They have been split across 10 focused per-domain route files:

  elements.py          - element categories, cost elements, bundle composition, FMV import
  factors.py           - conversion factors (multiplicative / additive)
  milestones.py        - per-template milestones + milestone library + AI generation
  notes.py             - per-template freeform notes
  policy_documents.py  - per-trial policy PDFs (BYTEA)
  reference.py         - ISO-3 countries + FX rates
  templates.py         - budget template CRUD + cascade + resolve/total/status + policy refactor
  visits.py            - trial-level + template-level visit schedules
  visit_matrix.py      - visit matrix generate/get/patch + line items + amendment marks
  soa.py               - Schedule of Activities import + AI preview/apply

This file is now a 30-line aggregator: it owns the parent ``router`` that
main.py imports, and includes each sub-router. The URL surface is unchanged
from when every endpoint lived here.

When adding a new endpoint:
  - It belongs in the matching domain file above.
  - If no domain fits, create a new domain file and add an include_router line
    here. Do not let this file accrete endpoints again.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.modules.site_budgeting.routes.elements import router as _elements_router
from app.modules.site_budgeting.routes.factors import router as _factors_router
from app.modules.site_budgeting.routes.milestones import router as _milestones_router
from app.modules.site_budgeting.routes.notes import router as _notes_router
from app.modules.site_budgeting.routes.policy_documents import router as _policy_documents_router
from app.modules.site_budgeting.routes.reference import router as _reference_router
from app.modules.site_budgeting.routes.soa import router as _soa_router
from app.modules.site_budgeting.routes.templates import router as _templates_router
from app.modules.site_budgeting.routes.visit_matrix import router as _visit_matrix_router
from app.modules.site_budgeting.routes.visits import router as _visits_router

router = APIRouter(tags=["Site Budgeting"])

router.include_router(_elements_router)
router.include_router(_factors_router)
router.include_router(_milestones_router)
router.include_router(_notes_router)
router.include_router(_policy_documents_router)
router.include_router(_reference_router)
router.include_router(_soa_router)
router.include_router(_templates_router)
router.include_router(_visit_matrix_router)
router.include_router(_visits_router)

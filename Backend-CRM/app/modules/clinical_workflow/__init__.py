"""
clinical_workflow module.

Split of the former 2,264-line app/api/v1/endpoints/clinical_workflow.py.
Follows the Pattern B module shape used by app/modules/site_budgeting/.

Layout:
  routes/
    site_status.py               Site status dashboard endpoints (4)
    feasibility_questionnaire.py Custom-question CRUD + MongoDB merge (5)
    feasibility_requests.py      Public form lifecycle (request, get, submit, lookup, responses, reset) (6)
    workflow_steps.py            (future) Per-site workflow step state machine (3)
  services/
    study_site_service.py        get_or_create_study_site race-safe upsert helper
    cda_documents.py             (future) CDA HTML generator + path resolver

clinical_workflow.py at the original path remains as a thin shim that
re-exports the public surface (router + helper functions) so existing
imports (main router config, legal_docs.py) keep working.
"""

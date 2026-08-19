"""Workflow platform module.

A generic, data-driven workflow engine (definitions → versions → instances →
audit) that runs any document lifecycle (CTA, CDA, NDA, ...) without per-type
code. Ported from the standalone workflow-platform reference and wired into the
CRM backend:

  * models inherit from the shared ``app.db`` Base (Alembic / metadata visibility)
  * service + router are async (AsyncSession), router owns the transaction
  * auth maps the CRM ``get_current_user`` dict to the engine's CurrentUser

The pure layers — ``engine`` and ``conditions`` — touch no DB and stay sync.

This package ``__init__`` is intentionally side-effect free (no router import) so
that ``app.models`` can register the ORM models without dragging in the FastAPI /
auth dependency chain. Import the router explicitly where it is mounted:

    from app.modules.workflows.router import router as workflows_router
"""

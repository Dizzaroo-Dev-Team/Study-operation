## Scripts Folder

This directory groups **operational scripts** that support the backend without being part of the running FastAPI application.

- `maintenance/` – data-fix and maintenance scripts (e.g. workflow resets, data audits, one-time corrections). These are typically run manually by operators or during controlled maintenance windows.
- `integration/` – scripts that integrate with external systems or databases (e.g. Neon sync, cross-system copy jobs). They should be run only in environments where those integrations are configured.
- `tools/` – small utility scripts used by developers or ops (e.g. JWT secret generation, helper CLIs). These do not change schema by themselves.

**Usage guidelines:**
- Scripts here are **not imported** by the application code and should be executed explicitly (for example, `python scripts/maintenance/reset_workflow_steps.py`).
- Review each script before running it in a non-development environment; many are one-time or environment-specific.
- Do not rely on these scripts as part of the normal request/response path; they are for out-of-band operations only.


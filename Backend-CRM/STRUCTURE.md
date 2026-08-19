# Backend folder structure

State as of 2026-05-19 (doc refresh: monitoring `routes/` layout, `app/db/` wording).

## End-state tree

```
Backend-CRM/
├── app/
│   ├── main.py                 # single source of truth for router wiring
│   ├── config.py               # Pydantic Settings
│   ├── db/                     # database connectivity package
│   │   ├── __init__.py           # re-exports get_db, AsyncSessionLocal, Base, engine, init_db, transactional
│   │   ├── postgres.py           # async PostgreSQL engine + session factory (was app/db.py)
│   │   ├── mongo.py              # MongoDB client (was app/db_mongo.py)
│   │   └── feasibility_mongo.py  # Mongo client for feasibility questions (was app/db_feasibility_mongo.py)
│   ├── auth.py                 # get_current_user dependency
│   ├── audit.py                # audit-log helpers
│   ├── errors.py               # AppError hierarchy + FastAPI exception handlers
│   ├── permissions.py          # permission predicates + require() dependency
│   ├── websocket_manager.py    # WS connection manager
│   ├── crud.py                 # legacy god-file (being absorbed by modules)
│   │
│   ├── models/                 # SQLAlchemy models (split from former god-file)
│   ├── schemas/                # Pydantic models (split from former god-file)
│   ├── crud/                   # CRUD package (split from former god-file)
│   ├── utils/                  # generic helpers (azure_storage, onlyoffice_utils, etc.)
│   ├── workers/                # Celery: celery_app.py, tasks.py, provider.py
│   │
│   ├── integrations/           # third-party glue
│   │   ├── ai/                   # Gemini client + per-feature wrappers
│   │   ├── iam/                  # IAM JWT verification + local user mirror reads
│   │   ├── kafka/                # Data Platform IAM consumer (port of D:/kafka: data_platform_consumer + events/ + models/ + utils/)
│   │   ├── milestones_kafka/     # Data Platform milestone + document PRODUCER
│   │   ├── google_search.py
│   │   ├── mailgun_service.py
│   │   ├── smtp_service.py
│   │   └── tmf_service.py
│   │
│   └── modules/                # one folder per CRM domain
│       ├── agreements/           (routes/, services/, aggregator.py)
│       ├── ai/                   (routes/ — chat docs, summarize endpoints)
│       ├── auth_profiles/        (routes/profiles.py — user CRUD, login, signup)
│       ├── clinical_workflow/    (routes/, services/)
│       ├── communications/       (routes/, services/ — conversations, threads, email webhook)
│       ├── facilities/           (routes/facilities.py)
│       ├── feasibility/          (routes/, services/ — questionnaire + attachments)
│       ├── isf/                  (Investigator Site File — its own routers/, services/, db_models)
│       ├── monitoring/           (routes/*.py — visits, findings, dashboard, MVR templates, letters, … + aggregator.py)
│       ├── operations/           (routes/operations.py — tasks + health)
│       ├── review_comments/      (routes/comments.py — comment-only mode workflow)
│       ├── site_budgeting/       (full Pattern B: db_models, routes/, services/, repositories/, validators/)
│       ├── site_packages/        (routes.py, services.py — moved from app/site_packages/)
│       ├── sites/                (routes/sites.py + 4 IRB route files, services/site_status_service.py, irb_catalog.py)
│       └── study_dashboard/      (routes/, services/ — read-only SDTM views)
│
├── migrations/                 # historical .sql + .py scripts (see migrations/README.md + AUDIT.md)
├── scripts/                    # operational scripts; setup_local_db_full.sql = canonical bootstrap
├── tests/                      # pytest suite
├── uploads/                    # canonical upload root (relative to settings.upload_dir)
├── pytest.ini
└── alembic.ini
```

Note: `local_schema.sql` is gitignored. It's a pg_dump artifact produced on demand by `scripts/refresh_local_from_neon.ps1` and consumed by `scripts/sync_schema_to_neon.py`.

## Conventions

### Module shape (`app/modules/<feature>/`)

A module owns its own slice of the domain. Every module follows this layout:

- `__init__.py` — short docstring describing the module's responsibility.
- `routes/` — FastAPI routers.
  - One file per route group (e.g. `routes/sites.py`, `routes/irbs.py`).
  - `routes/__init__.py` exports a single `router` that aggregates sub-routers and is mounted by `app/main.py`.
- `services/` — business logic. One file per domain concern. Routes call services; services never import routes.
- `repositories/` — query-heavy or race-safe persistence helpers. **Don't create a repo to wrap one ORM call** — only create one when the query has non-trivial joins, filters, or concurrency control.
- `validators/schemas.py` — Pydantic models specific to this module (when the shape doesn't belong in shared `app/schemas/`).
- `db_models.py` — module-specific SQLAlchemy models. Older modules still share `app/models/`; new modules should co-locate.
- `aggregator.py` — present only where a god-file extraction left a legacy-helper carve-out (today: `agreements/aggregator.py`, `monitoring/aggregator.py`). New modules should not have one.

**Module-local repositories (per-domain)**

- `app/modules/communications/repositories/mongo.py` — `ConversationRepository`, `MessageRepository`, `AttachmentRepository`, `ThreadRepository`, `ThreadParticipantRepository`, `ThreadMessageRepository`, `ThreadAttachmentRepository`, `ThreadFromConversationRepository`.
- `app/modules/operations/repositories/tasks.py` — `TaskRepository`.
- `app/modules/auth_profiles/repositories/postgres.py` — `UserRepository`, `ConversationAccessRepository`, `UserRoleAssignmentRepository`.
- `app/modules/sites/repositories/postgres.py` — `StudyRepository`, `SiteRepository`.

Each repositories folder has an `__init__.py` that re-exports its public classes, so callers do `from app.modules.<feature>.repositories import X`. The legacy shared `app/repositories/` package no longer exists.

### Integrations shape (`app/integrations/<name>/` or `app/integrations/<name>.py`)

A file (or sub-package) per provider. No internal layering — just the client class plus the functions it exposes. The boundary rule: anything that talks to a third-party service goes here, not under `modules/`.

| File | Purpose |
|---|---|
| `integrations/ai/` | Gemini client + summarization, classification, chat, similarity, compose-assist |
| `integrations/iam/auth.py` | IAM JWT verification, hub-token introspection |
| `integrations/iam/users.py` | Local user mirror (Postgres rows synced from IAM) |
| `integrations/kafka/` | Inbound IAM Kafka consumer — faithful Python port of the `D:/kafka` Node bundle: `data_platform_consumer.py` (connection/lifecycle), `events/` (router + 6 entity handlers), `models/sync_models.py` (collection contracts + indexes), `utils/` (config, logger, policy-cache stub). Reuses the milestone producer's Data Platform connection |
| `integrations/kafka/events/user_event.py` | User sync + the Postgres `users` upsert helper (`_upsert_postgres_user` / `_DEFAULT_PASSWORD_HASH`) imported by the auth/login path |
| `integrations/smtp_service.py` | Email send via direct SMTP |
| `integrations/mailgun_service.py` | Email send via Mailgun HTTP API |
| `integrations/tmf_service.py` | TMF (Trial Master File) handoff |
| `integrations/google_search.py` | Google search wrapper |

### Cross-cutting infra (flat at `app/`)

Files that don't belong to any single module stay at `app/` root:

- `main.py`, `config.py`
- `auth.py`, `audit.py`, `errors.py`, `permissions.py`
- `websocket_manager.py`
- `crud.py` — legacy god-file. New CRUD goes into the matching module's `services/` or `repositories/`.

Database connectivity lives in the **`app/db/`** package (`postgres.py`, `mongo.py`, `feasibility_mongo.py`, …); import via `from app.db import get_db`, etc.

Packages: `models/`, `schemas/`, `crud/`, `utils/`, `workers/`.

### Why no `core/` folder

`app/core/` was considered and rejected because "core" is opaque. Cross-cutting infra is just kept flat at `app/` root, where the file names (`auth.py`, `errors.py`, `permissions.py`) describe themselves.

### Routing

- `app/main.py` mounts every module's aggregator router with `prefix="/api"` and explicit tags.
- The legacy `/api/v1/` prefix was eliminated — there is no `v2` and there never was, so the version segment was carrying no information.
- Module-internal route paths are unchanged from the pre-refactor state. URLs on the wire are identical.

### Upload paths

`settings.upload_dir` (default `"uploads"`) is anchored to the repo root (`Backend-CRM/uploads/`). Callers that previously used `__file__.parent.parent / settings.upload_dir` were rewritten in `ai_services.py` and `feasibility/routes/attachments.py` to anchor to `Path(__file__).resolve().parents[N]` where N is chosen so the resolved path is always `Backend-CRM/`.

Stale `app/uploads/` and `app/api/v1/uploads/` folders were deleted; their content moved into the canonical `Backend-CRM/uploads/`.

## Adding a new module

1. Create `app/modules/<feature>/` with `__init__.py`.
2. Create `routes/<group>.py` (or multiple) and `routes/__init__.py` that aggregates them into a single `router`.
3. Create `services/<thing>_service.py` for the business logic. Routes call services; services never call routes.
4. If the queries are non-trivial, create `repositories/<thing>_repo.py`. Otherwise services use SQLAlchemy directly.
5. In `app/main.py`, add `from app.modules.<feature>.routes import router as <feature>_router` and `app.include_router(<feature>_router, prefix="/api", tags=["<Feature>"])`.
6. Add an entry to the CLAUDE.md "Backend — feature index" table.

## Pre-refactor → post-refactor map

If you have an old reference, here's where things moved:

| Old path | New path |
|---|---|
| `app/api/v1/endpoints/legal_docs.py` | `app/modules/agreements/aggregator.py` + `app/modules/agreements/routes/*.py` |
| `app/api/v1/endpoints/clinical_workflow.py` | `app/modules/clinical_workflow/routes/*.py` + `services/*.py` |
| `app/api/v1/endpoints/communications.py` | `app/modules/communications/routes/communications.py` |
| `app/api/v1/endpoints/auth_profiles.py` | `app/modules/auth_profiles/routes/profiles.py` |
| `app/api/v1/endpoints/ai_services.py` | `app/modules/ai/routes/ai_services.py` |
| `app/api/v1/endpoints/operations.py` | `app/modules/operations/routes/operations.py` |
| `app/api/v1/endpoints/document_comments.py` | `app/modules/review_comments/routes/comments.py` |
| `app/api/v1/endpoints/facilities_external.py` | `app/modules/facilities/routes/facilities.py` |
| `app/api/sites.py` | `app/modules/sites/routes/sites.py` |
| `app/api/irbs.py`, `irb_requirements.py`, `irb_administrative_info.py`, `site_irb_mapping.py` | `app/modules/sites/routes/*.py` |
| `app/api/feasibility_attachments.py` | `app/modules/feasibility/routes/attachments.py` |
| `app/api/email_webhook.py` | `app/modules/communications/routes/email_webhook.py` |
| `app/services/agreement_service.py` | `app/modules/agreements/services/agreement_service.py` |
| `app/services/conversation_service.py` | `app/modules/communications/services/conversation_service.py` |
| `app/services/cda_thread_service.py` | `app/modules/communications/services/cda_thread_service.py` (2026-05 reorg) -> `app/modules/agreements/types/cda/thread_integration.py` (Phase 2 isolation, file is CDA-specific) |
| `app/modules/agreements/routes/crud.py::complete_cda_execution_milestone` | `app/modules/agreements/types/cda/service.py::complete_cda_execution_milestone` (Phase 2 isolation, CDA-only side effect lifted out of shared CRUD) |
| `app/services/feasibility_service.py` | `app/modules/feasibility/services/feasibility_service.py` |
| `app/services/smtp_service.py` | `app/integrations/smtp_service.py` |
| `app/services/mailgun_service.py` | `app/integrations/mailgun_service.py` |
| `app/services/tmf_service.py` | `app/integrations/tmf_service.py` |
| `app/services/ai/` | `app/integrations/ai/` |
| `app/ai_service.py` (shim) | DELETED. Use `from app.integrations.ai import ai_service` |
| `app/iam_auth.py` | `app/integrations/iam/auth.py` |
| `app/iam_users.py` | `app/integrations/iam/users.py` |
| `app/google_search_service.py` | `app/integrations/google_search.py` |
| `app/site_status_service.py` | `app/modules/sites/services/site_status_service.py` |
| `app/irb_catalog.py` | `app/modules/sites/irb_catalog.py` |
| `app/site_packages/` | `app/modules/site_packages/` |
| `app/monitor/router.py` | `app/modules/monitoring/aggregator.py` |
| `app/migrations/` (empty stub) | DELETED |
| `app/core/` (empty stub) | DELETED |
| `app/uploads/` (stale) | DELETED; content migrated to `Backend-CRM/uploads/` |
| `app/api/v1/uploads/` (stale) | DELETED |
| `app/db.py` | `app/db/postgres.py` (`from app.db import get_db` still works via package re-export) |
| `app/db_mongo.py` | `app/db/mongo.py` |
| `app/db_feasibility_mongo.py` | `app/db/feasibility_mongo.py` |
| `app/repositories/mongo_repository.py` (Conversation/Message/Thread*) | `app/modules/communications/repositories/mongo.py` |
| `app/repositories/mongo_repository.py` (TaskRepository) | `app/modules/operations/repositories/tasks.py` |
| `app/repositories/postgres_repository.py` (User/Role/ConvAccess) | `app/modules/auth_profiles/repositories/postgres.py` |
| `app/repositories/postgres_repository.py` (Study/Site) | `app/modules/sites/repositories/postgres.py` |
| `app/repositories/` (whole folder) | DELETED |

The 26-test pytest suite stayed green after every cluster move.

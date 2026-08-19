-- ============================================================================
-- Workflow Platform (full) — ADDITIVE schema install for PRODUCTION Postgres
-- Run directly in pgAdmin against the prod database.
--
-- WHY THIS VERSION
--   The precondition check revealed prod has NO workflow tables yet (the whole
--   workflow platform — base V1 + V2 — is absent). This script therefore creates
--   the ENTIRE platform from scratch: the 4 base tables AND the 3 V2 tables, in
--   dependency order, all CREATE ... IF NOT EXISTS.
--
-- SAFETY (unchanged guarantees)
--   100% ADDITIVE and NON-DESTRUCTIVE. It only CREATEs brand-new workflow tables
--   and their indexes. It does NOT read, drop, truncate, delete, rename, retype,
--   or add NOT NULL to ANY existing table. Your live agreements, signatures, and
--   21 CFR audit rows are completely untouched (those tables aren't referenced).
--   Wrapped in one transaction (BEGIN; ... COMMIT;): if anything fails, NOTHING
--   is applied. Fully IDEMPOTENT (IF NOT EXISTS everywhere): safe to run twice,
--   and safe to run on an env that already has some of these tables.
--
-- WHAT THIS ADDS
--   BASE workflow platform (4 tables):
--     * workflow_definitions          one row per document type (CTA, CDA, ...)
--     * workflow_definition_versions  immutable JSON snapshots of each flow
--     * workflow_instances            one running document walking a definition
--                                     (INCLUDES the V2 parent_instance_id /
--                                      parent_step_id sub-workflow columns)
--     * workflow_audit_entries        append-only action trail
--   V2 additions (3 tables):
--     * workflow_tasks                work-item / worklist read-model
--     * workflow_timers               durable boundary timers (escalations)
--     * workflow_jobs                 automated-step (job) executions
--   ...plus every index + the unique constraints the models declare.
--   Types/constraints follow the SQLAlchemy models and the project's canonical
--   V2 migration. BIGINT/BIGSERIAL is used consistently across all 7 tables so
--   every foreign key matches its parent key cleanly.
--
--   >>> TAKE A FULL DATABASE BACKUP BEFORE RUNNING. <<<
--   (pg_dump or an Azure restore point — instant rollback if you ever want it.)
--
-- NON-ADDITIVE ITEMS REQUIRING A MANUAL DECISION
--   NONE. Every statement is a CREATE of a brand-new object. There is no change
--   to any existing column, table, or row anywhere in this script.
--
-- After COMMIT, run the VERIFICATION queries at the bottom.
-- ============================================================================

BEGIN;

-- ==========================================================================
-- BASE PLATFORM
-- ==========================================================================

-- 1) workflow_definitions ---------------------------------------------------
CREATE TABLE IF NOT EXISTS workflow_definitions (
    id          BIGSERIAL    PRIMARY KEY,
    key         VARCHAR(64)  NOT NULL,
    name        VARCHAR(255) NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_workflow_definitions_key UNIQUE (key)
);
CREATE INDEX IF NOT EXISTS ix_workflow_definitions_key ON workflow_definitions (key);

-- 2) workflow_definition_versions ------------------------------------------
CREATE TABLE IF NOT EXISTS workflow_definition_versions (
    id             BIGSERIAL    PRIMARY KEY,
    definition_id  BIGINT       NOT NULL
                                REFERENCES workflow_definitions(id) ON DELETE CASCADE,
    version        INTEGER      NOT NULL,
    is_published   BOOLEAN      NOT NULL DEFAULT FALSE,
    body           JSON         NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_workflow_definition_versions_def_ver UNIQUE (definition_id, version)
);
CREATE INDEX IF NOT EXISTS ix_workflow_definition_versions_definition_id
    ON workflow_definition_versions (definition_id);

-- 3) workflow_instances (includes the V2 parent_* columns) -----------------
CREATE TABLE IF NOT EXISTS workflow_instances (
    id                  BIGSERIAL    PRIMARY KEY,
    version_id          BIGINT       NOT NULL
                                     REFERENCES workflow_definition_versions(id),
    definition_key      VARCHAR(64)  NOT NULL,
    definition_version  INTEGER      NOT NULL,
    status              VARCHAR(32)  NOT NULL DEFAULT 'active',
    current_step        VARCHAR(128),
    subject_ref         VARCHAR(255),
    parent_instance_id  BIGINT,
    parent_step_id      VARCHAR(128),
    context             JSON         NOT NULL DEFAULT '{}'::json,
    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_workflow_instances_version_id          ON workflow_instances (version_id);
CREATE INDEX IF NOT EXISTS ix_workflow_instances_definition_key      ON workflow_instances (definition_key);
CREATE INDEX IF NOT EXISTS ix_workflow_instances_status              ON workflow_instances (status);
CREATE INDEX IF NOT EXISTS ix_workflow_instances_subject_ref         ON workflow_instances (subject_ref);
CREATE INDEX IF NOT EXISTS ix_workflow_instances_parent_instance_id  ON workflow_instances (parent_instance_id);

-- 4) workflow_audit_entries -------------------------------------------------
CREATE TABLE IF NOT EXISTS workflow_audit_entries (
    id             BIGSERIAL    PRIMARY KEY,
    instance_id    BIGINT       NOT NULL
                                REFERENCES workflow_instances(id) ON DELETE CASCADE,
    actor          VARCHAR(255),
    action         VARCHAR(64)  NOT NULL,
    transition_id  VARCHAR(128),
    from_step      VARCHAR(128),
    to_step        VARCHAR(128),
    comment        TEXT,
    payload        JSON         NOT NULL DEFAULT '{}'::json,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_workflow_audit_entries_instance_id
    ON workflow_audit_entries (instance_id);

-- ==========================================================================
-- V2 ADDITIONS
-- ==========================================================================

-- 5) workflow_tasks — V2 work items (the worklist read-model) ---------------
CREATE TABLE IF NOT EXISTS workflow_tasks (
    id                BIGSERIAL    PRIMARY KEY,
    instance_id       BIGINT       NOT NULL
                                   REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_id           VARCHAR(128) NOT NULL,
    slot_id           VARCHAR(128) NOT NULL DEFAULT '',
    name              VARCHAR(255) NOT NULL,
    assignee_type     VARCHAR(16),
    assignee_value    VARCHAR(255),
    resolved_user_id  VARCHAR(255),
    status            VARCHAR(16)  NOT NULL DEFAULT 'open',
    claimed_by        VARCHAR(255),
    completed_by      VARCHAR(255),
    due_at            TIMESTAMPTZ,
    created_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_workflow_tasks_instance_id       ON workflow_tasks (instance_id);
CREATE INDEX IF NOT EXISTS ix_workflow_tasks_status            ON workflow_tasks (status);
CREATE INDEX IF NOT EXISTS ix_workflow_tasks_resolved_user_id  ON workflow_tasks (resolved_user_id);
COMMENT ON TABLE workflow_tasks IS
    'V2 work items: the worklist read-model, distinct from control-flow steps';

-- 6) workflow_timers — durable boundary timers (escalations / deadlines) -----
CREATE TABLE IF NOT EXISTS workflow_timers (
    id           BIGSERIAL    PRIMARY KEY,
    instance_id  BIGINT       NOT NULL
                              REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_id      VARCHAR(128) NOT NULL,
    action       VARCHAR(64)  NOT NULL,
    fire_at      TIMESTAMPTZ  NOT NULL,
    status       VARCHAR(16)  NOT NULL DEFAULT 'pending',
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_workflow_timers_instance_id  ON workflow_timers (instance_id);
CREATE INDEX IF NOT EXISTS ix_workflow_timers_fire_at      ON workflow_timers (fire_at);
CREATE INDEX IF NOT EXISTS ix_workflow_timers_status       ON workflow_timers (status);

-- 7) workflow_jobs — automated-step (job) executions ------------------------
CREATE TABLE IF NOT EXISTS workflow_jobs (
    id            BIGSERIAL    PRIMARY KEY,
    instance_id   BIGINT       NOT NULL
                               REFERENCES workflow_instances(id) ON DELETE CASCADE,
    step_id       VARCHAR(128) NOT NULL,
    kind          VARCHAR(64)  NOT NULL,
    params        JSON         NOT NULL DEFAULT '{}'::json,
    status        VARCHAR(16)  NOT NULL DEFAULT 'pending',
    attempts      INTEGER      NOT NULL DEFAULT 0,
    max_attempts  INTEGER      NOT NULL DEFAULT 1,
    result        JSON,
    error         TEXT,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_workflow_jobs_instance_id  ON workflow_jobs (instance_id);
CREATE INDEX IF NOT EXISTS ix_workflow_jobs_status       ON workflow_jobs (status);

-- 8) Idempotent guard: if an env already had the base table WITHOUT the V2
--    parent columns, add them now (no-op here, since step 3 created them).
ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS parent_instance_id BIGINT;
ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS parent_step_id     VARCHAR(128);
CREATE INDEX IF NOT EXISTS ix_workflow_instances_parent_instance_id
    ON workflow_instances (parent_instance_id);

COMMIT;

-- ============================================================================
-- POST-RUN VERIFICATION  (run separately, AFTER the COMMIT above)
-- ============================================================================

-- (1) Confirm all 7 workflow tables now exist:
-- SELECT table_name
-- FROM information_schema.tables
-- WHERE table_schema = 'public'
--   AND table_name IN ('workflow_definitions','workflow_definition_versions',
--                      'workflow_instances','workflow_audit_entries',
--                      'workflow_tasks','workflow_timers','workflow_jobs')
-- ORDER BY table_name;          -- expect 7 rows

-- (2) Confirm the V2 parent columns on workflow_instances (both NULLABLE):
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'workflow_instances'
--   AND column_name IN ('parent_instance_id','parent_step_id')
-- ORDER BY column_name;

-- (3) DATA UNCHANGED — run BEFORE and AFTER; counts MUST be identical.
--     (This script never touches these tables; it only creates new empty ones.)
-- SELECT 'agreements'                       AS tbl, COUNT(*) AS rows FROM agreements
-- UNION ALL SELECT 'agreement_signers',            COUNT(*) FROM agreement_signers
-- UNION ALL SELECT 'agreement_internal_signatures',COUNT(*) FROM agreement_internal_signatures
-- UNION ALL SELECT 'agreement_reviewer_signatures',COUNT(*) FROM agreement_reviewer_signatures
-- UNION ALL SELECT 'agreement_signed_documents',   COUNT(*) FROM agreement_signed_documents
-- UNION ALL SELECT 'audit_logs',                   COUNT(*) FROM audit_logs
-- ORDER BY tbl;

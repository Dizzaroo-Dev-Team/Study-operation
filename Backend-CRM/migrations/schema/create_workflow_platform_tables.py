"""
Workflow platform — schema migration.

Creates the four tables that back the generic, data-driven workflow engine
(app/modules/workflows). Nothing existing is touched: no enum changes, no
alterations to `agreements` / `cta_*`. This lands the engine ALONGSIDE the
current hardcoded CTA/CDA flows.

Tables created (all idempotent via CREATE TABLE IF NOT EXISTS):
  1. workflow_definitions          — one row per document type (CTA, CDA, NDA...)
  2. workflow_definition_versions  — immutable JSON snapshots of each flow
  3. workflow_instances            — one running document, pinned to a version
  4. workflow_audit_entries        — every action ever taken (audit trail)

Notes:
  * Integer (BIGSERIAL) primary keys, matching the int ids the engine/router use.
  * `body` / `context` / `payload` are JSON columns (flow-as-data + accumulated
    variables). `gen_random_uuid()` is NOT used — these tables key on integers.
  * created_at / updated_at use TIMESTAMPTZ (house style — matches the other
    tables and the SQLAlchemy DateTime(timezone=True) mapping in
    app/modules/workflows/models.py).

This is NON-destructive. It only creates tables/indexes if absent.

Run inside the backend container:
  python migrations/schema/create_workflow_platform_tables.py
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from app.config import settings


async def upgrade() -> None:
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    SessionLocal = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )

    async with SessionLocal() as session:
        try:
            # ------------------------------------------------------------------
            # 1. workflow_definitions — one row per document type.
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS workflow_definitions (
                    id          BIGSERIAL    PRIMARY KEY,
                    key         VARCHAR(64)  NOT NULL UNIQUE,
                    name        VARCHAR(255) NOT NULL,
                    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_workflow_definitions_key
                    ON workflow_definitions (key);
            """))
            await session.execute(text("""
                COMMENT ON TABLE workflow_definitions IS
                    'One row per document workflow type (CTA, CDA, NDA, ...)';
            """))

            # ------------------------------------------------------------------
            # 2. workflow_definition_versions — immutable JSON snapshots.
            #    UNIQUE (definition_id, version). Cascades with its definition.
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS workflow_definition_versions (
                    id             BIGSERIAL PRIMARY KEY,
                    definition_id  BIGINT    NOT NULL
                                             REFERENCES workflow_definitions(id) ON DELETE CASCADE,
                    version        INTEGER     NOT NULL,
                    is_published   BOOLEAN     NOT NULL DEFAULT FALSE,
                    body           JSON        NOT NULL,
                    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    CONSTRAINT uq_workflow_definition_versions_def_version
                        UNIQUE (definition_id, version)
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_workflow_definition_versions_definition_id
                    ON workflow_definition_versions (definition_id);
            """))
            await session.execute(text("""
                COMMENT ON TABLE workflow_definition_versions IS
                    'Immutable flow-as-data snapshots; instances pin to one version';
            """))

            # ------------------------------------------------------------------
            # 3. workflow_instances — one running document.
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS workflow_instances (
                    id                  BIGSERIAL    PRIMARY KEY,
                    version_id          BIGINT       NOT NULL
                                                     REFERENCES workflow_definition_versions(id),
                    definition_key      VARCHAR(64)  NOT NULL,
                    definition_version  INTEGER      NOT NULL,
                    status              VARCHAR(32)  NOT NULL DEFAULT 'active',
                    current_step        VARCHAR(128),
                    subject_ref         VARCHAR(255),
                    context             JSON         NOT NULL DEFAULT '{}'::json,
                    created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
                    updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW()
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_workflow_instances_version_id
                    ON workflow_instances (version_id);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_workflow_instances_definition_key
                    ON workflow_instances (definition_key);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_workflow_instances_status
                    ON workflow_instances (status);
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_workflow_instances_subject_ref
                    ON workflow_instances (subject_ref);
            """))
            await session.execute(text("""
                COMMENT ON TABLE workflow_instances IS
                    'A running document walking a pinned workflow version';
            """))

            # ------------------------------------------------------------------
            # 4. workflow_audit_entries — every action ever taken.
            # ------------------------------------------------------------------
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS workflow_audit_entries (
                    id             BIGSERIAL   PRIMARY KEY,
                    instance_id    BIGINT      NOT NULL
                                               REFERENCES workflow_instances(id) ON DELETE CASCADE,
                    actor          VARCHAR(255),
                    action         VARCHAR(64) NOT NULL,
                    transition_id  VARCHAR(128),
                    from_step      VARCHAR(128),
                    to_step        VARCHAR(128),
                    comment        TEXT,
                    payload        JSON        NOT NULL DEFAULT '{}'::json,
                    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
            """))
            await session.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_workflow_audit_entries_instance_id
                    ON workflow_audit_entries (instance_id);
            """))
            await session.execute(text("""
                COMMENT ON TABLE workflow_audit_entries IS
                    'Append-only audit trail of every workflow transition';
            """))

            # ------------------------------------------------------------------
            # 5. Self-heal timestamp types.
            #    If the tables were auto-created by SQLAlchemy create_all (which
            #    runs on app startup / uvicorn --reload) BEFORE this migration,
            #    they may carry plain `timestamp without time zone`. Convert any
            #    such column to TIMESTAMPTZ (interpreting existing naive values as
            #    UTC). Guarded so it only fires on drift — a no-op once correct.
            # ------------------------------------------------------------------
            await session.execute(text("""
                DO $$
                DECLARE
                    col RECORD;
                BEGIN
                    FOR col IN
                        SELECT table_name, column_name
                        FROM information_schema.columns
                        WHERE table_name IN (
                                  'workflow_definitions',
                                  'workflow_definition_versions',
                                  'workflow_instances',
                                  'workflow_audit_entries'
                              )
                          AND column_name IN ('created_at', 'updated_at')
                          AND data_type = 'timestamp without time zone'
                    LOOP
                        EXECUTE format(
                            'ALTER TABLE %I ALTER COLUMN %I TYPE timestamptz '
                            'USING %I AT TIME ZONE ''UTC''',
                            col.table_name, col.column_name, col.column_name
                        );
                    END LOOP;
                END $$;
            """))

            await session.commit()
            print("create_workflow_platform_tables migration applied successfully.")

        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(upgrade())

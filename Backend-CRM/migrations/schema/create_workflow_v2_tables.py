"""
Workflow Platform V2 — schema migration (additive, idempotent).

Phase 3: workflow_tasks — the work-item / worklist read-model. One row per open
human work unit (a parked human step, an open parallel branch, the current
ordered-signing slot, a parked decision). Created/completed/cancelled by kernel
commands; claimed/reassigned by users.

Nothing existing is touched. Safe to re-run (CREATE TABLE IF NOT EXISTS).

Run inside the backend container:
  python migrations/schema/create_workflow_v2_tables.py
"""

import asyncio

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings


STATEMENTS = [
    """
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
    """,
    "CREATE INDEX IF NOT EXISTS ix_workflow_tasks_instance_id ON workflow_tasks (instance_id);",
    "CREATE INDEX IF NOT EXISTS ix_workflow_tasks_status ON workflow_tasks (status);",
    "CREATE INDEX IF NOT EXISTS ix_workflow_tasks_resolved_user_id ON workflow_tasks (resolved_user_id);",
    """
    COMMENT ON TABLE workflow_tasks IS
        'V2 work items: the worklist read-model, distinct from control-flow steps';
    """,
    # Phase 4: durable boundary timers + automated-step job executions.
    """
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
    """,
    "CREATE INDEX IF NOT EXISTS ix_workflow_timers_instance_id ON workflow_timers (instance_id);",
    "CREATE INDEX IF NOT EXISTS ix_workflow_timers_fire_at ON workflow_timers (fire_at);",
    "CREATE INDEX IF NOT EXISTS ix_workflow_timers_status ON workflow_timers (status);",
    """
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
    """,
    "CREATE INDEX IF NOT EXISTS ix_workflow_jobs_instance_id ON workflow_jobs (instance_id);",
    "CREATE INDEX IF NOT EXISTS ix_workflow_jobs_status ON workflow_jobs (status);",
    # Phase 5: sub-workflow parent linkage on instances.
    "ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS parent_instance_id BIGINT;",
    "ALTER TABLE workflow_instances ADD COLUMN IF NOT EXISTS parent_step_id VARCHAR(128);",
    "CREATE INDEX IF NOT EXISTS ix_workflow_instances_parent_instance_id ON workflow_instances (parent_instance_id);",
]


async def upgrade() -> None:
    engine = create_async_engine(settings.database_url, echo=False, future=True)
    SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with SessionLocal() as session:
        try:
            for stmt in STATEMENTS:
                await session.execute(text(stmt))
            await session.commit()
            print("create_workflow_v2_tables migration applied successfully.")
        except Exception:
            await session.rollback()
            raise
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(upgrade())

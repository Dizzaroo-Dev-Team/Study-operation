"""
Migration: add study_country table

Tracks which countries are formally enrolled in a given study/trial.
Sites are linked via the existing sites.country field.
This table supports the left-panel country-site hierarchy in the budget module
and will serve as the anchor for site setup once site creation is integrated.
"""
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise SystemExit(
        "DATABASE_URL is not set. Run inside the backend container "
        "(docker compose sets it) or export it first."
    )

SQL = """
-- study_country: maps a trial/study to the countries it operates in
CREATE TABLE IF NOT EXISTS study_country (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id        UUID NOT NULL,
    country_code    CHAR(3) NOT NULL,
    country_name    VARCHAR(255),
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_study_country UNIQUE (trial_id, country_code)
);

CREATE INDEX IF NOT EXISTS ix_study_country_trial_id
    ON study_country(trial_id);

COMMENT ON TABLE study_country IS
    'Countries enrolled in a study. Used by the budget module for country-level template cascade.';
"""


async def run():
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text(SQL))
    await engine.dispose()
    print("[OK] study_country table created (or already exists).")


if __name__ == "__main__":
    asyncio.run(run())

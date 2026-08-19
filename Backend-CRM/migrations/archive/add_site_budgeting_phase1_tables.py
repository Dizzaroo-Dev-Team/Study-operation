"""
Phase 1 schema additions:
  - element_category (hierarchical taxonomy)
  - element_bundle_composition (bundle → child element map)
  - element_cost_version: add source, is_bundle_override columns
  - cost_element: add category_id FK (alongside existing varchar category)
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
-- ── element_category ─────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS element_category (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL,
    parent_id   UUID REFERENCES element_category(id) ON DELETE SET NULL,
    sort_order  INTEGER NOT NULL DEFAULT 0,
    created_at  TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_element_category_parent_id ON element_category(parent_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_element_category_name_parent
    ON element_category(name, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid));

-- ── element_bundle_composition ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS element_bundle_composition (
    bundle_element_id  UUID NOT NULL REFERENCES cost_element(id) ON DELETE CASCADE,
    child_element_id   UUID NOT NULL REFERENCES cost_element(id) ON DELETE CASCADE,
    quantity_in_bundle DECIMAL(10,4) NOT NULL DEFAULT 1,
    sort_order         INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bundle_element_id, child_element_id)
);

CREATE INDEX IF NOT EXISTS ix_ebc_bundle_element_id ON element_bundle_composition(bundle_element_id);
CREATE INDEX IF NOT EXISTS ix_ebc_child_element_id  ON element_bundle_composition(child_element_id);

-- ── element_cost_version: add missing columns ─────────────────────────────────
ALTER TABLE element_cost_version
    ADD COLUMN IF NOT EXISTS source             VARCHAR(100),
    ADD COLUMN IF NOT EXISTS is_bundle_override BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS created_by         VARCHAR(255),
    ADD COLUMN IF NOT EXISTS approved_by        VARCHAR(255);

-- ── cost_element: add category_id FK (optional, alongside varchar category) ──
ALTER TABLE cost_element
    ADD COLUMN IF NOT EXISTS category_id UUID REFERENCES element_category(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_cost_element_category_id ON cost_element(category_id);
"""


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for stmt in [s.strip() for s in SQL.split(";") if s.strip()]:
            await conn.execute(text(stmt))
    await engine.dispose()
    print("[OK] Phase 1 schema additions applied.")


if __name__ == "__main__":
    asyncio.run(main())

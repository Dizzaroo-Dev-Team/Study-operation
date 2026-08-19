"""
Align the 4 Phase-1 tables to the exact spec in site_budgeting_engineering_guide.md.

Changes:
  element_cost_version:
    - RENAME cost_element_id  → element_id
    - RENAME base_amount      → base_unit_cost
    - RENAME currency_code    → reference_currency

  cost_element:
    - RENAME unit             → unit_of_measure
    - DROP   category         (legacy varchar; category_id FK is now the source of truth)
    - Tighten VARCHAR lengths: code→50, name→255, unit_of_measure→50
    - Set NOT NULL on element_type, cost_type where already populated
      (leave NULL-safe: rows with NULL get a default first)
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

STEPS = [
    # ── element_cost_version ─────────────────────────────────────────────────
    # Drop the old index and unique constraint that reference the old column name
    "DROP INDEX IF EXISTS ix_element_cost_version_cost_element_id",
    "ALTER TABLE element_cost_version DROP CONSTRAINT IF EXISTS uq_element_cost_version_label",

    # Rename columns
    "ALTER TABLE element_cost_version RENAME COLUMN cost_element_id    TO element_id",
    "ALTER TABLE element_cost_version RENAME COLUMN base_amount         TO base_unit_cost",
    "ALTER TABLE element_cost_version RENAME COLUMN currency_code       TO reference_currency",

    # Tighten reference_currency to CHAR(3) (was VARCHAR(3))
    "ALTER TABLE element_cost_version ALTER COLUMN reference_currency TYPE CHAR(3) USING reference_currency",

    # Recreate index and unique constraint with new column names
    "CREATE INDEX IF NOT EXISTS ix_element_cost_version_element_id ON element_cost_version(element_id)",
    """
    ALTER TABLE element_cost_version
        ADD CONSTRAINT uq_element_cost_version_label
        UNIQUE (element_id, version_label)
    """,

    # ── cost_element ──────────────────────────────────────────────────────────
    # Rename unit → unit_of_measure
    "ALTER TABLE cost_element RENAME COLUMN unit TO unit_of_measure",

    # Drop legacy category varchar (category_id FK is now authoritative)
    "ALTER TABLE cost_element DROP COLUMN IF EXISTS category",

    # Tighten VARCHAR lengths to match spec
    "ALTER TABLE cost_element ALTER COLUMN code           TYPE VARCHAR(50)  USING code",
    "ALTER TABLE cost_element ALTER COLUMN name           TYPE VARCHAR(255) USING name",
    "ALTER TABLE cost_element ALTER COLUMN unit_of_measure TYPE VARCHAR(50) USING unit_of_measure",

    # Back-fill NULLs before applying NOT NULL constraint
    "UPDATE cost_element SET element_type  = 'ATOMIC'    WHERE element_type  IS NULL",
    "UPDATE cost_element SET cost_type     = 'PER_VISIT' WHERE cost_type     IS NULL",
    "UPDATE cost_element SET unit_of_measure = 'unit'    WHERE unit_of_measure IS NULL",

    # Apply NOT NULL
    "ALTER TABLE cost_element ALTER COLUMN element_type   SET NOT NULL",
    "ALTER TABLE cost_element ALTER COLUMN cost_type      SET NOT NULL",
    "ALTER TABLE cost_element ALTER COLUMN unit_of_measure SET NOT NULL",
]


async def main() -> None:
    engine = create_async_engine(DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        for i, stmt in enumerate(STEPS):
            s = stmt.strip()
            if not s:
                continue
            try:
                await conn.execute(text(s))
                print(f"  [{i+1:02d}] OK  {s[:80]}")
            except Exception as e:
                print(f"  [{i+1:02d}] ERR {s[:80]}")
                print(f"       → {e}")
                raise
    await engine.dispose()
    print("[DONE] Schema aligned to spec.")


if __name__ == "__main__":
    asyncio.run(main())

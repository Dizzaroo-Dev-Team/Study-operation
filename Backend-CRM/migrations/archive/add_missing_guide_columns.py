"""
Add columns required by the engineering guide that are currently missing (A6).

Additions:
- budget_template.locked_exchange_rate_date DATE   (guide §3.4 — FX rate snapshot at EXECUTED)
- site_budgeting_audit_log.user_role VARCHAR(50)    (guide §3.8 — role at time of action)
- budget_milestone.element_id UUID FK cost_element  (guide §3.6 — NULLABLE link to library)
- budget_milestone: rename amount → unit_cost       (guide §3.6 naming)

Safe to re-run.
"""
import asyncio
import sys

if sys.platform == "win32":
    import codecs
    sys.stdout = codecs.getwriter("utf-8")(sys.stdout.buffer, "strict")
    sys.stderr = codecs.getwriter("utf-8")(sys.stderr.buffer, "strict")

from sqlalchemy import text
from app.db import AsyncSessionLocal
from app.config import settings

# Each entry is a standalone DDL statement (no multi-statement blocks)
STMTS = [
    # budget_template: FX rate lock date
    "ALTER TABLE budget_template ADD COLUMN IF NOT EXISTS locked_exchange_rate_date DATE",
    # audit log: role at time of action
    "ALTER TABLE site_budgeting_audit_log ADD COLUMN IF NOT EXISTS user_role VARCHAR(50)",
    # budget_milestone: link to cost element library (NULLABLE)
    "ALTER TABLE budget_milestone ADD COLUMN IF NOT EXISTS element_id UUID REFERENCES cost_element(id) ON DELETE SET NULL",
]

CHECK_AMOUNT = """
SELECT column_name FROM information_schema.columns
WHERE table_name = 'budget_milestone' AND column_name = 'amount'
"""

CHECK_UNIT_COST = """
SELECT column_name FROM information_schema.columns
WHERE table_name = 'budget_milestone' AND column_name = 'unit_cost'
"""

RENAME_AMOUNT = "ALTER TABLE budget_milestone RENAME COLUMN amount TO unit_cost"


async def run() -> None:
    print("Add missing guide columns (A6)")
    db_info = settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url
    print(f"Database: {db_info}\n")
    async with AsyncSessionLocal() as session:
        try:
            for stmt in STMTS:
                await session.execute(text(stmt))
                print(f"  [OK] {stmt[:60]}...")

            # Rename amount → unit_cost only if amount exists and unit_cost does not
            has_amount = (await session.execute(text(CHECK_AMOUNT))).scalar_one_or_none()
            has_unit_cost = (await session.execute(text(CHECK_UNIT_COST))).scalar_one_or_none()
            if has_amount and not has_unit_cost:
                await session.execute(text(RENAME_AMOUNT))
                print("  [OK] Renamed budget_milestone.amount → unit_cost")
            elif has_unit_cost:
                print("  [SKIP] budget_milestone.unit_cost already exists")
            else:
                print("  [WARN] budget_milestone.amount not found — column may already be renamed or missing")

            await session.commit()
            print("\n[OK] Missing guide columns added.")
        except Exception as e:
            await session.rollback()
            print(f"[ERROR] {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run())

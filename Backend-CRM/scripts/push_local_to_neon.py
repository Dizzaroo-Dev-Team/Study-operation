"""
Additive local → Neon row push for the tables where local is the source of truth.

Pushes every local row whose PK doesn't already exist on Neon. Never overwrites
or deletes Neon rows. Tables are processed in FK-dependency order so children
arrive after their parents. Self-referencing FK (element_category.parent_id) is
handled with a two-pass insert: rows go in with parent_id=NULL, then a second
pass UPDATEs parent_id once every row is present.

Per row uses INSERT … ON CONFLICT (id) DO NOTHING — idempotent and safe to
re-run. Output reports per-table inserted / already-present / skipped counts.

Run:
  docker exec backend-crm-backend-1 python /app/scripts/push_local_to_neon.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Optional

sys.path.insert(0, "/app")

import asyncpg  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("push")


LOCAL_DSN = (
    os.environ.get("LOCAL_PG_DSN")
    or (os.environ.get("DATABASE_URL") or "").replace("postgresql+asyncpg://", "postgresql://")
)
if not LOCAL_DSN:
    sys.stderr.write(
        "ERROR: LOCAL_PG_DSN (or DATABASE_URL) is not set.\n"
        "Run inside the backend container or export the local connection string.\n"
    )
    sys.exit(2)
NEON_DSN = os.environ.get("NEON_PG_DSN")
if not NEON_DSN:
    sys.stderr.write(
        "ERROR: NEON_PG_DSN is not set.\n"
        "Export the Neon connection string before running this script.\n"
    )
    sys.exit(2)


# Tables in FK-dependency order. Each entry: (table_name, has_self_ref_parent_col)
# Catalog (no FK to study/site) → sites/mappings → study-scoped budget data.
PUSH_ORDER: list[tuple[str, Optional[str]]] = [
    # ── Catalog: no FK to studies/sites ──────────────────────────────────────
    ("element_category", "parent_id"),       # self-ref via parent_id
    ("cost_element", None),                  # FK → element_category
    ("element_cost_version", None),          # FK → cost_element
    ("element_bundle_composition", None),    # FK → cost_element (twice)
    ("milestone_library_item", None),
    ("currency_exchange_rate", None),
    ("conversion_factor_type", None),
    # ── Sites (additive) ─────────────────────────────────────────────────────
    ("sites", None),                         # FK → users (PI), optional
    ("study_sites", None),                   # FK → studies, sites
    # ── Study-scoped budget data ─────────────────────────────────────────────
    ("visit_schedule", None),                # FK → studies
    ("budget_template", "parent_template_id"),  # self-ref via parent_template_id
    ("conversion_factor", None),             # FK → studies, conversion_factor_type
    ("trial_factor_configuration", None),    # FK → studies
    ("budget_personnel_role", None),         # FK → budget_template
    ("budget_line_item", None),              # FK → budget_template, cost_element
    ("budget_visit_matrix", None),           # FK → budget_line_item, visit_schedule
    ("budget_milestone", None),              # FK → budget_template, cost_element (optional)
    ("budget_note", None),                   # FK → budget_template, users (optional)
    ("widget_schedule_visit", None),         # FK → studies
    ("site_packages", None),                 # FK → studies, sites (optional)
    ("site_workflow_steps", None),           # FK → study_sites
    ("site_budgeting_audit_log", None),      # FK loose
    # ── Tail: small tables found missing on second-pass diff ─────────────────
    ("budget_policy_document", None),        # FK → studies, optional users
    ("user_role_assignments", None),         # FK → users, studies, sites
    ("agreement_review_tokens", None),       # ephemeral signed-link tokens
    ("agreement_signing_tokens", None),
    ("site_enrollment_plan", None),          # FK → studies, sites (new feature table)
]


# ─── Helpers ─────────────────────────────────────────────────────────────────

async def _columns_for(conn: asyncpg.Connection, table: str) -> list[str]:
    """Ordered column list for a table (excludes generated columns)."""
    rows = await conn.fetch(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema='public' AND table_name=$1
          AND COALESCE(is_generated, 'NEVER') = 'NEVER'
        ORDER BY ordinal_position
        """,
        table,
    )
    return [r[0] for r in rows]


async def _table_exists_on_neon(neon: asyncpg.Connection, table: str) -> bool:
    return bool(
        await neon.fetchval(
            "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=$1)",
            table,
        )
    )


def _placeholder_list(n: int) -> str:
    return ", ".join(f"${i}" for i in range(1, n + 1))


# ─── Per-table push ──────────────────────────────────────────────────────────

async def _push_one_table(
    local: asyncpg.Connection,
    neon: asyncpg.Connection,
    *,
    table: str,
    self_ref_col: Optional[str],
) -> dict[str, int]:
    """Push every local row whose `id` isn't on Neon. Two-pass for self-ref."""
    if not await _table_exists_on_neon(neon, table):
        log.warning("[skip] %s: not present on Neon", table)
        return {"skipped_missing_table": 1}

    local_cols = await _columns_for(local, table)
    neon_cols = await _columns_for(neon, table)
    cols = [c for c in local_cols if c in neon_cols]
    if "id" not in cols:
        log.warning("[skip] %s: no `id` column in shared schema; cannot ON CONFLICT", table)
        return {"skipped_no_id": 1}

    # Always double-quote column identifiers — some legacy migrations created
    # mixed-case columns (e.g. `site_packages."ethicsBoard"`) which Postgres
    # only resolves correctly when quoted.
    qcols = ", ".join(f'"{c}"' for c in cols)

    # Discover what's already on Neon by id.
    existing = await neon.fetch(f"SELECT id FROM {table}")
    existing_ids = {str(r[0]) for r in existing}

    local_rows = await local.fetch(f"SELECT {qcols} FROM {table}")
    inserted = 0
    already = 0
    errored = 0
    deferred_parent_updates: list[tuple[Any, Any]] = []  # (id, parent_value)

    for row in local_rows:
        row_id = str(row["id"])
        if row_id in existing_ids:
            already += 1
            continue

        values: list[Any] = []
        for c in cols:
            v = row[c]
            if self_ref_col and c == self_ref_col and v is not None:
                # First pass: insert with parent NULL; remember to set later.
                deferred_parent_updates.append((row["id"], v))
                values.append(None)
            else:
                values.append(v)

        sql = (
            f"INSERT INTO {table} ({qcols}) "
            f"VALUES ({_placeholder_list(len(cols))}) "
            f"ON CONFLICT (id) DO NOTHING"
        )
        try:
            await neon.execute(sql, *values)
            inserted += 1
        except Exception as exc:  # noqa: BLE001
            errored += 1
            log.exception("[%s] insert failed for id=%s: %s", table, row_id, exc)

    # Second pass: backfill self-ref parent column.
    parent_set = 0
    for row_id, parent_v in deferred_parent_updates:
        try:
            await neon.execute(
                f'UPDATE {table} SET "{self_ref_col}" = $1 WHERE id = $2',
                parent_v, row_id,
            )
            parent_set += 1
        except Exception as exc:  # noqa: BLE001
            log.exception("[%s] parent backfill failed id=%s: %s", table, row_id, exc)

    out = {"inserted": inserted, "already": already, "errored": errored}
    if self_ref_col:
        out["parent_set"] = parent_set
    return out


# ─── Driver ──────────────────────────────────────────────────────────────────

async def main() -> None:
    log.info("connecting local + Neon")
    local = await asyncpg.connect(LOCAL_DSN)
    neon = await asyncpg.connect(NEON_DSN, ssl="require")
    try:
        log.info("=== push order: %d tables ===", len(PUSH_ORDER))
        totals: dict[str, dict[str, int]] = {}
        for table, self_ref in PUSH_ORDER:
            log.info("--- %s ---", table)
            result = await _push_one_table(local, neon, table=table, self_ref_col=self_ref)
            log.info("  %s: %s", table, result)
            totals[table] = result

        # Final summary
        log.info("\n=== summary ===")
        for t, r in totals.items():
            log.info("  %-40s %s", t, r)

        # Final count diff for the same tables
        log.info("\n=== post-push count comparison ===")
        for table, _ in PUSH_ORDER:
            try:
                ll = await local.fetchval(f"SELECT count(*) FROM {table}")
                nn = await neon.fetchval(f"SELECT count(*) FROM {table}")
                tag = "✓" if ll <= nn else "✗"
                log.info("  %s %-40s local=%d neon=%d", tag, table, ll, nn)
            except Exception as exc:  # noqa: BLE001
                log.warning("  ? %-40s (count failed: %s)", table, exc)

    finally:
        await local.close()
        await neon.close()


if __name__ == "__main__":
    asyncio.run(main())

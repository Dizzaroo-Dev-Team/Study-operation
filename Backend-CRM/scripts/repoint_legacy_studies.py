"""
One-shot: re-point legacy Postgres `studies` rows to their IAM/Mongo `_id`.

Why: the IAM Kafka mirror (`_upsert_postgres_study`) refuses to insert when a
legacy Postgres row already owns the same `study_id`. Result: every Postgres-
side feature that FK's into `studies.id` (budgets, study_sites, agreements,
visit_schedule, …) breaks for studies the user picks from the Mongo-driven
study dropdown.

This script aligns Postgres with Mongo by **moving** legacy rows to their
canonical IAM UUID, preserving every dependent FK. Pure-miss Mongo studies
(no legacy collision, just no Postgres row) get a fresh INSERT.

Behaviour:
  - For each Mongo study (level=3, appKey=study_operations, isActive=True):
      * If Postgres already has a row with that exact id → skip.
      * Else if a legacy Postgres row matches by `study_id` (case-insensitive
        match against Mongo `name`) → rename the legacy row's study_id to a
        `__tmp__`-suffixed value, INSERT a new row with the Mongo id and the
        original study_id, re-point every child FK, DELETE the legacy row.
      * Else (pure miss) → INSERT a fresh row with the Mongo id.
  - All steps for a single study run inside one transaction. If anything
    fails, that study is rolled back and the next one is attempted.
  - FK target tables are discovered dynamically via `information_schema`, so
    a future 14th FK target won't be silently skipped.

Idempotent: re-running after a successful run is a no-op (every Mongo study
already has a canonical Postgres row → first branch matches).

Run:
  docker exec backend-crm-backend-1 python /app/scripts/repoint_legacy_studies.py
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from typing import Any, Optional
from uuid import UUID

# Allow running as `python /app/scripts/repoint_legacy_studies.py`.
sys.path.insert(0, "/app")

import asyncpg  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("repoint")


# ─── Connection helpers ──────────────────────────────────────────────────────

def _pg_dsn() -> str:
    """Resolve the Postgres DSN. Priority:
      1. CLI: --target-dsn=<dsn>   (allows pointing at Neon explicitly)
      2. env: TARGET_PG_DSN
      3. env: DATABASE_URL (default — local Postgres)
    Strips the SQLAlchemy `postgresql+asyncpg://` prefix that asyncpg can't parse.
    """
    raw: Optional[str] = None
    for arg in sys.argv[1:]:
        if arg.startswith("--target-dsn="):
            raw = arg.split("=", 1)[1]
            break
    if raw is None:
        raw = os.environ.get("TARGET_PG_DSN") or os.environ.get("DATABASE_URL")
    if raw is None:
        raise SystemExit(
            "No DSN provided. Pass --target-dsn= or set TARGET_PG_DSN / "
            "DATABASE_URL (docker compose sets DATABASE_URL in the container)."
        )
    if raw.startswith("postgresql+asyncpg://"):
        raw = "postgresql://" + raw[len("postgresql+asyncpg://"):]
    return raw


def _mongo_uri() -> str:
    return os.environ.get("MONGODB_URI") or os.environ.get("MONGO_URI") or "mongodb://mongo:27017"


def _mongo_db_name() -> str:
    return (
        os.environ.get("MONGODB_DATABASE")
        or os.environ.get("MONGODB_DB_NAME")
        or os.environ.get("MONGO_DB")
        or "crm_db"
    )


# ─── FK introspection ────────────────────────────────────────────────────────

async def _discover_fk_targets(conn: asyncpg.Connection) -> list[tuple[str, str]]:
    """Every (table, column) pair whose FK references `studies.id`."""
    rows = await conn.fetch(
        """
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
        WHERE tc.constraint_type='FOREIGN KEY'
          AND ccu.table_name='studies'
          AND ccu.column_name='id'
        ORDER BY tc.table_name, kcu.column_name
        """
    )
    return [(r["table_name"], r["column_name"]) for r in rows]


# ─── Per-study transaction ───────────────────────────────────────────────────

async def _legacy_match_for(conn: asyncpg.Connection, mongo_name: str) -> Optional[asyncpg.Record]:
    """Return the legacy Postgres `studies` row whose `study_id` matches the
    Mongo `name` (case-insensitive). At most one — the column is UNIQUE."""
    if not mongo_name:
        return None
    return await conn.fetchrow(
        "SELECT id, study_id, name, status, description FROM studies WHERE LOWER(study_id) = LOWER($1)",
        mongo_name,
    )


async def _repoint_one(
    conn: asyncpg.Connection,
    *,
    mongo_id: UUID,
    mongo_name: str,
    fk_targets: list[tuple[str, str]],
) -> str:
    """Process a single Mongo study. Returns one of: 'already', 'repointed', 'inserted', 'skipped'."""
    # 1. Already mirrored?
    existing = await conn.fetchrow("SELECT id FROM studies WHERE id = $1", mongo_id)
    if existing is not None:
        return "already"

    # 2. Legacy collision?
    legacy = await _legacy_match_for(conn, mongo_name)

    async with conn.transaction():
        if legacy is not None:
            legacy_id = legacy["id"]
            original_study_id = legacy["study_id"]
            legacy_name = legacy["name"]
            legacy_status = legacy["status"]
            legacy_desc = legacy["description"]

            # 2a. Free up the UNIQUE study_id slot by renaming the legacy row.
            tmp_study_id = f"{original_study_id}__tmp__{str(legacy_id)[:8]}"
            await conn.execute(
                "UPDATE studies SET study_id = $1 WHERE id = $2",
                tmp_study_id, legacy_id,
            )

            # 2b. Insert the canonical IAM row with the original study_id.
            await conn.execute(
                """
                INSERT INTO studies (id, study_id, name, status, description)
                VALUES ($1, $2, $3, $4, $5)
                """,
                mongo_id, original_study_id, mongo_name or legacy_name,
                legacy_status or "active", legacy_desc,
            )

            # 2c. Re-point every child FK from legacy_id → mongo_id.
            for table, col in fk_targets:
                await conn.execute(
                    f"UPDATE {table} SET {col} = $1 WHERE {col} = $2",
                    mongo_id, legacy_id,
                )

            # 2d. Drop the (now child-less, tmp-named) legacy row.
            await conn.execute("DELETE FROM studies WHERE id = $1", legacy_id)
            log.info(
                "[repoint] %s : legacy %s -> mongo %s (study_id=%r)",
                mongo_name, legacy_id, mongo_id, original_study_id,
            )
            return "repointed"

        # 3. Pure miss — INSERT a fresh row keyed on the Mongo id.
        candidate_study_id = mongo_name or str(mongo_id)
        # Avoid UNIQUE collision: if the chosen study_id is taken by some other
        # row (rare — would mean Mongo `name` collides with a non-matching legacy
        # study_id), suffix it.
        clash = await conn.fetchrow(
            "SELECT id FROM studies WHERE study_id = $1", candidate_study_id
        )
        if clash is not None:
            candidate_study_id = f"{candidate_study_id} ({str(mongo_id)[:8]})"

        await conn.execute(
            """
            INSERT INTO studies (id, study_id, name, status)
            VALUES ($1, $2, $3, 'active')
            """,
            mongo_id, candidate_study_id, mongo_name or candidate_study_id,
        )
        log.info("[insert] %s : created Postgres row for mongo %s (study_id=%r)",
                 mongo_name, mongo_id, candidate_study_id)
        return "inserted"


# ─── Driver ──────────────────────────────────────────────────────────────────

async def main() -> None:
    pg_dsn = _pg_dsn()
    mongo_uri = _mongo_uri()
    mongo_db_name = _mongo_db_name()

    log.info("connecting Postgres=%s mongo=%s/%s", pg_dsn.split("@")[-1], mongo_uri, mongo_db_name)
    pg_kwargs: dict[str, Any] = {}
    if "neon.tech" in pg_dsn or "sslmode=require" in pg_dsn:
        pg_kwargs["ssl"] = "require"
    pg = await asyncpg.connect(pg_dsn, **pg_kwargs)
    mongo_client = AsyncIOMotorClient(mongo_uri)
    mongo = mongo_client[mongo_db_name]

    try:
        fk_targets = await _discover_fk_targets(pg)
        log.info("FK targets to studies.id (%d):", len(fk_targets))
        for t, c in fk_targets:
            log.info("  %s.%s", t, c)

        cursor = mongo["local_resources"].find(
            {"level": 3, "appKey": "study_operations", "isActive": True}
        )
        mongo_docs: list[dict[str, Any]] = await cursor.to_list(500)
        log.info("Mongo studies to consider: %d", len(mongo_docs))

        counts: dict[str, int] = {"already": 0, "repointed": 0, "inserted": 0, "skipped": 0}
        for doc in mongo_docs:
            try:
                mongo_id = UUID(str(doc.get("_id")))
            except (ValueError, TypeError):
                log.warning("[skip] non-UUID Mongo _id: %r", doc.get("_id"))
                counts["skipped"] += 1
                continue
            name = (doc.get("name") or "").strip()
            try:
                outcome = await _repoint_one(
                    pg, mongo_id=mongo_id, mongo_name=name, fk_targets=fk_targets
                )
                counts[outcome] = counts.get(outcome, 0) + 1
            except Exception as exc:  # noqa: BLE001
                log.exception("[error] %s (%s): %s", name, mongo_id, exc)
                counts["skipped"] += 1

        log.info("=== summary === %s", counts)

        # Final parity verification.
        log.info("=== parity verification ===")
        for doc in mongo_docs:
            mid = doc.get("_id")
            row = await pg.fetchrow("SELECT id FROM studies WHERE id = $1", UUID(str(mid)))
            mark = "✓" if row else "✗"
            log.info("  %s %s %s", mark, mid, doc.get("name"))

    finally:
        await pg.close()
        mongo_client.close()


if __name__ == "__main__":
    asyncio.run(main())

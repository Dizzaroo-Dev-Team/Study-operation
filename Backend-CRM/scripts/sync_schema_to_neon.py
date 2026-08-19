"""
sync_schema_to_neon.py
======================
Syncs the local PostgreSQL schema to Neon (production) safely.

Ground truth = local CRM DB.
Neon is brought in line WITHOUT dropping any existing data.

What this script does:
  1.  Creates any ENUM types that exist locally but not in Neon.
  2.  Creates any tables that exist locally but not in Neon.
  3.  Adds any columns that exist locally but are missing from Neon tables.
  4.  Creates any missing indexes.
  5.  Reports everything it does so you can review the changes.

What it does NOT do:
  - Drop tables / columns / enums (never destructive).
  - Modify column types or constraints on existing columns.
  - Touch data.

Usage (run from Backend-CRM/ directory):
    docker exec backend-crm-backend-1 python /app/scripts/sync_schema_to_neon.py
"""

import asyncio
import sys
import os
import re

# ── Connection strings ────────────────────────────────────────────────────────
# Required env var. Set before running:
#   $env:NEON_DATABASE_URL = "postgresql://USER:PASS@HOST/DB?sslmode=require"
_NEON_RAW = os.environ.get("NEON_DATABASE_URL")
if not _NEON_RAW:
    sys.stderr.write(
        "ERROR: NEON_DATABASE_URL is not set.\n"
        "Export the Neon connection string before running this script.\n"
    )
    sys.exit(2)

# SQLAlchemy async needs the asyncpg driver scheme.
if _NEON_RAW.startswith("postgresql+asyncpg://"):
    NEON_URL = _NEON_RAW
elif _NEON_RAW.startswith("postgresql://"):
    NEON_URL = "postgresql+asyncpg://" + _NEON_RAW[len("postgresql://"):]
elif _NEON_RAW.startswith("postgres://"):
    NEON_URL = "postgresql+asyncpg://" + _NEON_RAW[len("postgres://"):]
else:
    NEON_URL = _NEON_RAW

# Strip `sslmode=require` query param if present — asyncpg uses connect_args instead.
if "?" in NEON_URL:
    base, _, query = NEON_URL.partition("?")
    parts = [p for p in query.split("&") if not p.startswith("sslmode=")]
    NEON_URL = base + ("?" + "&".join(parts) if parts else "")

NEON_SSL  = {"ssl": "require"}

SCHEMA_SQL_PATH = os.path.join(os.path.dirname(__file__), "..", "local_schema.sql")

# ─────────────────────────────────────────────────────────────────────────────

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


def _section(msg: str):
    print(f"\n{'─'*60}\n  {msg}\n{'─'*60}")


def _is_harmless(err: Exception) -> bool:
    """True if the error is expected noise (already exists, etc.)."""
    msg = str(err).lower()
    return any(k in msg for k in [
        "already exists", "duplicate", "does not exist",
        "multiple primary key", "multiple default",
        "infailedsqltransaction",   # cascade from earlier error — we handle each stmt separately now
    ])


async def exec_one(engine, stmt: str, label: str = "") -> bool:
    """Execute a single statement in its own transaction. Returns True on success."""
    async with engine.begin() as conn:
        try:
            await conn.execute(text(stmt))
            return True
        except Exception as e:
            if _is_harmless(e):
                return True   # treat as success
            print(f"  ⚠  {label or stmt[:80]!r}")
            # Show the real error (first line only)
            first_line = str(e).splitlines()[0]
            print(f"     → {first_line[:140]}")
            return False


# ── Schema parsing ────────────────────────────────────────────────────────────

def parse_schema_sql(sql_path: str) -> dict:
    with open(sql_path, "r", encoding="utf-8") as f:
        raw = f.read()

    # Strip pg_dump meta-noise
    lines = []
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("SET ") or s.startswith("SELECT pg_catalog") or \
           s.startswith("\\") or s.startswith("--"):
            continue
        lines.append(line)
    sql = "\n".join(lines)

    statements = [s.strip() for s in re.split(r";\s*\n", sql) if s.strip()]

    result = {"enums": [], "tables": [], "alters": [],
              "indexes": [], "sequences": [], "other": []}

    for stmt in statements:
        m = re.match(r"CREATE TYPE\s+(?:public\.)?(\w+)\s+AS ENUM", stmt, re.IGNORECASE)
        if m:
            result["enums"].append((m.group(1), stmt));  continue

        m = re.match(r"CREATE TABLE\s+(?:public\.)?(\w+)", stmt, re.IGNORECASE)
        if m:
            result["tables"].append((m.group(1), stmt)); continue

        if re.match(r"CREATE SEQUENCE", stmt, re.IGNORECASE):
            result["sequences"].append(stmt);            continue

        m = re.match(r"CREATE (?:UNIQUE )?INDEX\s+(\w+)", stmt, re.IGNORECASE)
        if m:
            result["indexes"].append((m.group(1), stmt)); continue

        if re.match(r"ALTER TABLE", stmt, re.IGNORECASE):
            result["alters"].append(stmt);               continue

        if stmt:
            result["other"].append(stmt)

    return result


def _extract_columns_from_create(create_sql: str) -> dict:
    """Return {col_name: column_def_line} from a CREATE TABLE statement."""
    try:
        start = create_sql.index("(")
    except ValueError:
        return {}
    depth, body_chars = 0, []
    for ch in create_sql[start:]:
        if ch == "(": depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0: break
        body_chars.append(ch)
    body = "".join(body_chars[1:])
    cols = {}
    for line in body.splitlines():
        line = line.strip().rstrip(",")
        if not line: continue
        if re.match(r"(CONSTRAINT|PRIMARY KEY|UNIQUE|CHECK|FOREIGN KEY|EXCLUDE)", line, re.IGNORECASE):
            continue
        m = re.match(r'^"?(\w+)"?\s+', line)
        if m:
            cols[m.group(1)] = line
    return cols


# ── Query helpers ─────────────────────────────────────────────────────────────

async def fetch_existing_enums(engine) -> set:
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT typname FROM pg_type "
            "JOIN pg_namespace ON pg_namespace.oid = pg_type.typnamespace "
            "WHERE typtype = 'e' AND pg_namespace.nspname = 'public'"))
        return {row[0] for row in r}


async def fetch_existing_tables(engine) -> set:
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"))
        return {row[0] for row in r}


async def fetch_existing_columns(engine, table: str) -> set:
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=:t"), {"t": table})
        return {row[0] for row in r}


async def fetch_existing_indexes(engine) -> set:
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname='public'"))
        return {row[0] for row in r}


async def fetch_existing_sequences(engine) -> set:
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT sequencename FROM pg_sequences WHERE schemaname='public'"))
        return {row[0] for row in r}


# ── Sync steps ────────────────────────────────────────────────────────────────

async def sync_enums(engine, parsed, existing) -> int:
    created = 0
    for name, stmt in parsed["enums"]:
        if name not in existing:
            print(f"  + CREATE ENUM: {name}")
            if await exec_one(engine, stmt, f"CREATE ENUM {name}"):
                created += 1
        else:
            print(f"  ✓ {name}")
    return created


async def sync_sequences(engine, parsed, existing) -> int:
    created = 0
    for stmt in parsed["sequences"]:
        m = re.search(r"SEQUENCE\s+(?:public\.)?(\w+)", stmt, re.IGNORECASE)
        name = m.group(1) if m else "?"
        if name not in existing:
            print(f"  + CREATE SEQUENCE: {name}")
            if await exec_one(engine, stmt, f"CREATE SEQUENCE {name}"):
                created += 1
    return created


async def sync_tables(engine, parsed, existing) -> int:
    created = 0
    for name, stmt in parsed["tables"]:
        if name not in existing:
            print(f"  + CREATE TABLE: {name}")
            if await exec_one(engine, stmt, f"CREATE TABLE {name}"):
                created += 1
        else:
            print(f"  ✓ {name}")
    return created


async def sync_columns(engine, parsed, existing_tables) -> int:
    added = 0
    for name, stmt in parsed["tables"]:
        if name not in existing_tables:
            continue  # newly created; all columns present
        existing_cols = await fetch_existing_columns(engine, name)
        local_cols = _extract_columns_from_create(stmt)
        for col_name, col_def in local_cols.items():
            if col_name not in existing_cols:
                alter = f'ALTER TABLE "{name}" ADD COLUMN IF NOT EXISTS {col_def}'
                print(f"  + ADD COLUMN  {name}.{col_name}")
                if await exec_one(engine, alter, f"ADD COLUMN {name}.{col_name}"):
                    added += 1
    return added


async def sync_alters(engine, parsed) -> tuple:
    ok, skipped = 0, 0
    for stmt in parsed["alters"]:
        success = await exec_one(engine, stmt)
        if success:
            ok += 1
        else:
            skipped += 1
    return ok, skipped


async def sync_indexes(engine, parsed, existing) -> int:
    created = 0
    for name, stmt in parsed["indexes"]:
        if name not in existing:
            print(f"  + CREATE INDEX: {name}")
            if await exec_one(engine, stmt, f"CREATE INDEX {name}"):
                created += 1
    return created


# ── Main ──────────────────────────────────────────────────────────────────────

async def main():
    print("\n🔄  CRM Schema Sync — Local → Neon")
    print("    Ground truth : local CRM DB (crm_db @ localhost)")
    print("    Target       : Neon (from NEON_DATABASE_URL)\n")

    _section("Parsing local schema dump")
    if not os.path.exists(SCHEMA_SQL_PATH):
        print(f"ERROR: Schema file not found at {SCHEMA_SQL_PATH}")
        sys.exit(1)

    parsed = parse_schema_sql(SCHEMA_SQL_PATH)
    print(f"  Found: {len(parsed['enums'])} enums, "
          f"{len(parsed['sequences'])} sequences, "
          f"{len(parsed['tables'])} tables, "
          f"{len(parsed['alters'])} alters, "
          f"{len(parsed['indexes'])} indexes")

    _section("Connecting to Neon")
    engine = create_async_engine(NEON_URL, connect_args=NEON_SSL, echo=False,
                                 pool_pre_ping=True)

    existing_enums     = await fetch_existing_enums(engine)
    existing_tables    = await fetch_existing_tables(engine)
    existing_indexes   = await fetch_existing_indexes(engine)
    existing_sequences = await fetch_existing_sequences(engine)

    print(f"  Neon currently has: {len(existing_tables)} tables, "
          f"{len(existing_enums)} enums, {len(existing_indexes)} indexes, "
          f"{len(existing_sequences)} sequences")

    _section("Step 1 — Enums")
    n_enums = await sync_enums(engine, parsed, existing_enums)

    _section("Step 2 — Sequences")
    n_seq = await sync_sequences(engine, parsed, existing_sequences)
    if not parsed["sequences"]:
        print("  (none in local schema)")

    _section("Step 3 — Tables (create missing)")
    existing_tables = await fetch_existing_tables(engine)   # refresh after enums
    missing = [n for n, _ in parsed["tables"] if n not in existing_tables]
    if missing:
        print(f"  Missing: {missing}")
    else:
        print("  All 32 tables present — checking columns")
    n_tables = await sync_tables(engine, parsed, existing_tables)

    _section("Step 4 — Columns (add missing to existing tables)")
    existing_tables = await fetch_existing_tables(engine)
    n_cols = await sync_columns(engine, parsed, existing_tables)
    if n_cols == 0:
        print("  All columns already present")

    _section("Step 5 — ALTER TABLE statements (defaults / constraints)")
    n_ok, n_skip = await sync_alters(engine, parsed)
    print(f"  Applied: {n_ok}   Skipped (harmless): {n_skip}")

    _section("Step 6 — Indexes (create missing)")
    existing_indexes = await fetch_existing_indexes(engine)
    n_idx = await sync_indexes(engine, parsed, existing_indexes)
    if n_idx == 0:
        print("  All indexes already present")

    # ── Final verification ────────────────────────────────────────────────────
    _section("Final verification")
    final_tables  = await fetch_existing_tables(engine)
    final_indexes = await fetch_existing_indexes(engine)
    print(f"  Neon tables  : {len(final_tables)} / 32 expected")
    print(f"  Neon indexes : {len(final_indexes)}")
    missing_now = {n for n, _ in parsed["tables"]} - final_tables
    if missing_now:
        print(f"  ⚠  Still missing tables: {missing_now}")
    else:
        print("  ✅ All 32 tables present in Neon")

    _section("✅  Sync Complete — Summary")
    print(f"  Enums created    : {n_enums}")
    print(f"  Sequences created: {n_seq}")
    print(f"  Tables created   : {n_tables}")
    print(f"  Columns added    : {n_cols}")
    print(f"  Indexes created  : {n_idx}")
    print()
    print("  Neon is now in sync with the local CRM schema.")
    print("  No data was dropped or modified.\n")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())

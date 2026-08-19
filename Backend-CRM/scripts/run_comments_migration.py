"""
run_comments_migration.py
=========================
Creates the agreement_document_comments table (and its indexes / constraints).

Uses the same DATABASE_URL as the running backend — reads it from the app's
Settings (i.e. your .env file or environment variables), so:

  • Local dev   → connects to your local Postgres (whatever DATABASE_URL is in .env)
  • Production  → connects to Neon (DATABASE_URL set in Azure App Service)

The script is fully idempotent — safe to run multiple times.

Usage (run from the Backend-CRM/ directory):

  # Inside Docker container:
  docker exec backend-crm-backend-1 python /app/scripts/run_comments_migration.py

  # Or directly (with .env loaded):
  python scripts/run_comments_migration.py
"""

import asyncio
import pathlib
import sys

# ── Ensure Backend-CRM/ is on sys.path so `app` package is importable ────────
_here = pathlib.Path(__file__).parent.parent   # Backend-CRM/
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

# ── Load DATABASE_URL from the same settings the app uses ────────────────────
try:
    from app.config import settings
    DATABASE_URL = settings.database_url
except Exception as exc:
    print(f"[ERROR] Could not load app settings: {exc}")
    print("  Make sure DATABASE_URL is set in .env or as an environment variable.")
    sys.exit(1)

# Normalise scheme for asyncpg
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)

# When running this script outside Docker, the hostname "postgres" (Docker
# service name) can't be resolved.  Swap it for "localhost" automatically.
import socket as _socket
_is_neon = "neon.tech" in DATABASE_URL

if not _is_neon and "@postgres:" in DATABASE_URL:
    try:
        _socket.getaddrinfo("postgres", 5432)
    except _socket.gaierror:
        # "postgres" host not reachable → we are outside Docker, use localhost
        DATABASE_URL = DATABASE_URL.replace("@postgres:", "@localhost:", 1)

# SSL is only required for Neon / cloud Postgres
CONNECT_ARGS = {"ssl": "require"} if _is_neon else {}

MIGRATION_SQL = (
    pathlib.Path(__file__).parent.parent
    / "migrations"
    / "add_agreement_document_comments.sql"
)


async def main() -> None:
    # Mask the password in the printed URL
    display_url = DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL

    print("\n[INFO] Migration: add_agreement_document_comments")
    print(f"  Database : {display_url}")
    print(f"  SQL file : {MIGRATION_SQL}\n")

    if not MIGRATION_SQL.exists():
        print(f"[ERROR] Migration file not found: {MIGRATION_SQL}")
        sys.exit(1)

    sql = MIGRATION_SQL.read_text(encoding="utf-8")

    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError:
        print("[ERROR] sqlalchemy / asyncpg not installed.")
        sys.exit(1)

    engine = create_async_engine(
        DATABASE_URL,
        connect_args=CONNECT_ARGS,
        echo=False,
        pool_pre_ping=True,
    )

    # asyncpg does not support multi-statement SQL in a single execute() call.
    # Split the migration file into individual DO $$ ... END $$; blocks and run
    # each one in its own transaction.
    import re
    # Find every complete DO $$ ... END $$; block (case-insensitive, dot-all)
    blocks = re.findall(
        r'DO\s*\$\$.*?END\s*\$\$\s*;',
        sql,
        flags=re.DOTALL | re.IGNORECASE,
    )
    if not blocks:
        # Fallback: split on semicolons (for plain SQL files without DO blocks)
        blocks = [s.strip() for s in sql.split(';') if s.strip() and not s.strip().startswith('--')]

    print(f"  Running {len(blocks)} statement block(s)...")
    for i, block in enumerate(blocks, 1):
        async with engine.begin() as conn:
            try:
                await conn.execute(text(block))
                print(f"  Block {i}: OK")
            except Exception as exc:
                msg = str(exc)
                if any(k in msg.lower() for k in ("already exists", "does not exist", "duplicate")):
                    print(f"  Block {i}: already applied -- skipped")
                else:
                    print(f"  Block {i}: ERROR -- {msg[:300]}")
                    await engine.dispose()
                    sys.exit(1)

    # ── Verify ────────────────────────────────────────────────────────────────
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_schema='public' AND table_name='agreement_document_comments'"
        ))
        table_exists = r.scalar() == 1

    if not table_exists:
        print("[ERROR] Verification failed: table still not found after migration.")
        await engine.dispose()
        sys.exit(1)

    # ── Show created indexes ──────────────────────────────────────────────────
    async with engine.connect() as conn:
        r = await conn.execute(text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname='public' AND tablename='agreement_document_comments'"
        ))
        indexes = [row[0] for row in r]

    print(f"[OK] Table verified.  Indexes ({len(indexes)}):")
    for idx in indexes:
        print(f"     - {idx}")

    await engine.dispose()
    print("\n[DONE] agreement_document_comments is ready.\n")


if __name__ == "__main__":
    asyncio.run(main())

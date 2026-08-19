import os
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from app.config import settings

Base = declarative_base()

# ── Pool sizing ──────────────────────────────────────────────────────────────
# Tunable per-environment via env vars. The defaults below assume the May 2026
# audit baseline: one container, ~8 uvicorn workers expected at scale, dashboard
# endpoints that may run 4 parallel sub-queries via asyncio.gather. With
# pool_size=20 each worker can comfortably hold ~2-3 concurrent checkouts
# before reaching for overflow; max_overflow=40 absorbs bursts (e.g. monitoring
# dashboard fan-out under traffic spike).
#
# Critical caveat: total PG connections = (pool_size + max_overflow) * workers.
# At the defaults below that is 60 * 8 = 480, which exceeds free-tier Postgres
# limits. The Hunt 3 plan recommends pgBouncer (transaction pooling) when
# scaling past 2 workers; until pgBouncer is in place, keep DB_POOL_SIZE and
# DB_MAX_OVERFLOW lower (the values below leave room — they're not hard caps,
# they're just better defaults for a single instance).
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "20"))
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "40"))
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30"))
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "600"))

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    # ── Connection-pool resilience (critical for Neon / cloud Postgres) ──────
    # Neon closes idle connections after ~5 min. pool_pre_ping sends a cheap
    # "SELECT 1" before each checkout; if the connection is dead it is
    # transparently replaced, eliminating the InterfaceError: connection is
    # closed crash.
    pool_pre_ping=True,
    # Recycle connections older than DB_POOL_RECYCLE seconds regardless of
    # activity, so the pool never hands out a connection that Neon might have
    # reaped.
    pool_recycle=DB_POOL_RECYCLE,
    # Sized for ~8 concurrent uvicorn workers running gather-style dashboards.
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    # How long to wait for a free connection before raising TimeoutError.
    pool_timeout=DB_POOL_TIMEOUT,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """
    FastAPI dependency that yields an AsyncSession.

    If the checkout fails with a closed-connection error (can still happen on
    the very first request after a long idle period, before pool_pre_ping has
    had a chance to replace the connection) we invalidate the engine's pool
    and retry once with a fresh connection.
    """
    from sqlalchemy.exc import InterfaceError as SAInterfaceError
    try:
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()
    except SAInterfaceError as exc:
        # Stale connection slipped through – dispose the pool so the next
        # caller always gets a fresh connection.
        await engine.dispose()
        async with AsyncSessionLocal() as session:
            try:
                yield session
            finally:
                await session.close()


@asynccontextmanager
async def transactional(db: AsyncSession):
    """
    Scope a mutation block to a single transaction.

    Use this in route handlers (the transaction boundary) wrapping any call
    that mutates the database. Services receiving `db` should NOT call
    `db.commit()` / `db.rollback()` themselves — the boundary lives here.

    Usage:
        async with transactional(db):
            await agreement_service.submit(db, ...)
            # commits on exit; rolls back on any exception
    """
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        raise


async def init_db():
    # Import all models so they register on Base.metadata before create_all.
    import app.models  # noqa: F401
    from app.db import Base

    try:
        async with engine.begin() as conn:
            # create_all is idempotent: only creates tables that do not exist yet.
            await conn.run_sync(Base.metadata.create_all)
            print("✅ Database schema ensured (missing tables created if needed)")
    except Exception as e:
        error_msg = str(e).lower()
        if any(keyword in error_msg for keyword in [
            "already exists", "duplicate", "does not exist",
            "no schema", "schema", "relation",
        ]):
            print(f"⚠️  Database initialization skipped (tables may already exist): {type(e).__name__}")
        else:
            print(f"❌ Error initializing database: {e}")


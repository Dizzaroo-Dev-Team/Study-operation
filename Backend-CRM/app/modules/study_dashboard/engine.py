"""
Read-only async engine for the per-study SDTM Postgres (study_db_01).

Production normally uses a SEPARATE database from the main CRM Postgres, via
settings.study_db_01_* (host/port/name/user/password). The password may contain
reserved URL chars (@, &, +) so we build that URL with sqlalchemy.URL.create.

When STUDY_DB_01_HOST / STUDY_DB_01_USER are unset (typical local Docker), we
reuse ``settings.database_url`` so the API boots without extra env wiring; routes
still return empty SDTM payloads if the CRM database has no SDTM tables.

Usage in a route:
    async with get_study_db_session() as session:
        result = await session.execute(text("SELECT ..."))

Registry studies (Data Platform) get their own engines, cached per connection
string via get_registry_study_session(); the default study_db_01 engine above
is untouched by that path.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import URL
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None

# Engines for Data Platform registry studies, keyed by the raw connection
# string so a changed password/host in the registry yields a fresh engine.
_registry_engines: dict[str, tuple[object, async_sessionmaker[AsyncSession]]] = {}


def _build_url() -> URL:
    if settings.study_db_01_host and settings.study_db_01_user:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=settings.study_db_01_user,
            password=settings.study_db_01_password,
            host=settings.study_db_01_host,
            port=settings.study_db_01_port,
            database=settings.study_db_01_name,
        )
    return make_url(settings.database_url)


def get_study_engine():
    global _engine, _session_factory
    if _engine is None:
        _engine = create_async_engine(
            _build_url(),
            echo=False,
            future=True,
            pool_pre_ping=True,
            pool_recycle=600,
            pool_size=3,
            max_overflow=5,
            pool_timeout=30,
        )
        _session_factory = async_sessionmaker(
            _engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _engine


@asynccontextmanager
async def get_study_db_session() -> AsyncIterator[AsyncSession]:
    get_study_engine()
    assert _session_factory is not None
    async with _session_factory() as session:
        try:
            yield session
        finally:
            await session.close()


def _url_from_connection_string(conn: str) -> URL:
    """Build an asyncpg URL from a registry ``postgresql://`` connection string.

    Registry passwords are not URL-encoded and may contain reserved chars —
    e.g. ``postgresql://data_layer_ro:DataLayer@123@postgres:5432/study_10011``
    has an ``@`` inside the password, which make_url() would mis-split. So we
    take the string apart positionally: scheme, then rsplit the authority on
    the LAST ``@`` (host:port never contains one), then the first ``:`` splits
    user from password.
    """
    scheme, sep, rest = conn.partition("://")
    if not sep or not scheme.lower().startswith("postgres"):
        raise ValueError(f"Unsupported study connection string scheme: {scheme!r}")

    authority, _, dbname = rest.partition("/")
    dbname = dbname.split("?", 1)[0] or None

    username = password = None
    hostport = authority
    if "@" in authority:
        userinfo, _, hostport = authority.rpartition("@")
        username, colon, password = userinfo.partition(":")
        if not colon:
            password = None

    host, _, port = hostport.partition(":")

    # Registry connection strings use the Data Platform's Docker-internal
    # Postgres hostname; substitute the reachable one when configured.
    override = (settings.study_registry_db_host_override or "").strip()
    if override:
        host, _, override_port = override.partition(":")
        if override_port:
            port = override_port

    return URL.create(
        drivername="postgresql+asyncpg",
        username=username or None,
        password=password,
        host=host or None,
        port=int(port) if port else None,
        database=dbname,
    )


@asynccontextmanager
async def get_registry_study_session(connection_string: str) -> AsyncIterator[AsyncSession]:
    """Session against a Data Platform registry study database.

    Engines are created lazily per connection string and cached with small
    pools (dashboards are read-only and bursty, not sustained).
    """
    entry = _registry_engines.get(connection_string)
    if entry is None:
        engine = create_async_engine(
            _url_from_connection_string(connection_string),
            echo=False,
            future=True,
            pool_pre_ping=True,
            pool_recycle=600,
            pool_size=2,
            max_overflow=4,
            pool_timeout=30,
            # Data Platform study DBs keep SDTM domains in an `sdtm` schema
            # (study_db_01 keeps them in `public`). The dashboard services use
            # unqualified table names, so put both on the search path — public
            # first; schemas that don't exist or aren't readable are skipped.
            connect_args={"server_settings": {"search_path": "public,sdtm"}},
        )
        factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
        entry = (engine, factory)
        _registry_engines[connection_string] = entry
    _, session_factory = entry
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.close()

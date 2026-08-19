"""Database connectivity package.

Postgres + two Mongo databases. Each engine lives in its own submodule;
this `__init__` re-exports the public surface so existing imports keep
working:

    from app.db import get_db, AsyncSessionLocal, Base, engine, init_db
    from app.db import transactional

For Mongo, import from the submodule directly:

    from app.db.mongo import get_mongo_db, close_mongo_client, next_sequence
    from app.db.feasibility_mongo import get_feasibility_mongo_db
"""
from app.db.postgres import (
    AsyncSessionLocal,
    Base,
    engine,
    get_db,
    init_db,
    transactional,
)

__all__ = [
    "AsyncSessionLocal",
    "Base",
    "engine",
    "get_db",
    "init_db",
    "transactional",
]

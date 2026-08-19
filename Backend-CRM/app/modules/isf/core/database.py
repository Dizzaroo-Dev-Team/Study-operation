"""
ISF Database adapter for CRM integration.

Instead of opening a second MongoDB connection, this module delegates
entirely to the CRM's existing `app.db.mongo` singleton.  All ISF
collections will therefore land inside `crm_db` alongside every other
CRM collection — no separate `isf_db` is created.
"""
from app.db.mongo import get_mongo_db, get_mongo_client, close_mongo_client
import logging

logger = logging.getLogger(__name__)


async def get_isf_database():
    """
    Return the CRM's MongoDB database handle (crm_db).
    ISF collections (isf_documents, isfworkflows, …) are stored there.
    """
    db = await get_mongo_db()
    logger.debug(f"[ISF] Using CRM database: {db.name}")
    return db


async def connect_to_mongo():
    """Called at app startup — CRM's lifespan already manages this."""
    await get_mongo_db()
    logger.info("[ISF] Database ready (reusing CRM MongoDB connection)")


async def disconnect_from_mongo():
    """Called at app shutdown — CRM's lifespan already manages this."""
    logger.info("[ISF] Not closing MongoDB — managed by CRM lifespan")


# Alias used throughout the copied ISF router/service files:
#   from ..core.database import get_database
get_database = get_isf_database

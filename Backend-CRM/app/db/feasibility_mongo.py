"""
Separate MongoDB connection for external feasibility questionnaire database.
This is READ-ONLY access to an external MongoDB collection.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from app.config import settings
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Separate MongoDB client for feasibility questionnaires (external DB)
_feasibility_mongo_client: Optional[AsyncIOMotorClient] = None
_feasibility_mongo_db = None


async def get_feasibility_mongo_client() -> Optional[AsyncIOMotorClient]:
    """
    Get or create MongoDB client for external feasibility database.
    Returns None if FEASIBILITY_MONGO_URI is not configured.
    READ-ONLY access only.
    """
    global _feasibility_mongo_client
    
    if not settings.feasibility_mongo_uri:
        logger.warning("[FEASIBILITY_MONGO] FEASIBILITY_MONGO_URI not configured - feasibility questionnaires will be unavailable")
        return None
    
    if _feasibility_mongo_client is None:
        logger.info("[FEASIBILITY_MONGO] Connecting to external feasibility MongoDB")
        try:
            _feasibility_mongo_client = AsyncIOMotorClient(
                settings.feasibility_mongo_uri,
                serverSelectionTimeoutMS=5000,  # 5 second timeout
                connectTimeoutMS=5000,
                socketTimeoutMS=15000,  # 15 second socket timeout
                maxPoolSize=5,  # Smaller pool for read-only access
                minPoolSize=1
            )
            # Test connection
            import asyncio
            await asyncio.wait_for(_feasibility_mongo_client.admin.command('ping'), timeout=5.0)
            logger.info("[FEASIBILITY_MONGO] External feasibility MongoDB connection successful")
        except asyncio.TimeoutError:
            logger.warning("[FEASIBILITY_MONGO] Connection timed out - will retry on use")
        except Exception as e:
            logger.warning(f"[FEASIBILITY_MONGO] Connection failed: {e} - will retry on use")
    
    return _feasibility_mongo_client


async def get_feasibility_mongo_db():
    """
    Get MongoDB database instance for feasibility questionnaires.
    Returns None if not configured.
    """
    global _feasibility_mongo_db
    
    if not settings.feasibility_mongo_uri:
        return None
    
    if _feasibility_mongo_db is None:
        client = await get_feasibility_mongo_client()
        if client is not None:
            # Extract database name from URI
            # For mongodb+srv:// URIs, database name might be in the path or we need to use default
            # Format: mongodb+srv://user:pass@host/dbname?options
            uri_parts = settings.feasibility_mongo_uri.split('/')
            db_name = None
            
            # Check if database name is in the URI path
            if len(uri_parts) > 3:
                potential_db = uri_parts[-1].split('?')[0]  # Remove query params
                if potential_db and potential_db not in ['', '?']:
                    db_name = potential_db
            
            # If no database in URI, search all databases for 'feasibilityquestionnaires' collection
            if not db_name:
                db_name = None
                target_collection = "feasibilityquestionnaires"
                try:
                    db_list = await client.list_database_names()
                    logger.info(f"[FEASIBILITY_MONGO] Available databases: {db_list}")
                    
                    # Search each database for the target collection
                    # Prioritize 'test' database first (user confirmed questions are there)
                    db_search_order = ['test'] + [db for db in db_list if db != 'test' and db not in ['admin', 'local', 'config']]
                    
                    for db_candidate in db_search_order:
                        try:
                            db_test = client[db_candidate]
                            collections = await db_test.list_collection_names()
                            logger.info(f"[FEASIBILITY_MONGO] Database '{db_candidate}' has collections: {collections}")
                            if target_collection in collections:
                                db_name = db_candidate
                                logger.info(f"[FEASIBILITY_MONGO] ✅ Found '{target_collection}' in database '{db_name}'")
                                break
                        except Exception as e:
                            logger.debug(f"[FEASIBILITY_MONGO] Error checking database '{db_candidate}': {e}")
                    
                    # Fallback: prioritize 'test' database if collection not found
                    if not db_name:
                        if 'test' in db_list:
                            db_name = 'test'
                            logger.info("[FEASIBILITY_MONGO] Using 'test' database (user confirmed questions are here)")
                        elif db_list:
                            non_system_dbs = [db for db in db_list if db not in ['admin', 'local', 'config']]
                            if non_system_dbs:
                                db_name = non_system_dbs[0]
                                logger.warning(f"[FEASIBILITY_MONGO] Collection '{target_collection}' not found. Using database: {db_name}")
                except Exception as e:
                    logger.warning(f"[FEASIBILITY_MONGO] Could not search databases: {e}")
                    db_name = "llm-compare"  # Fallback
            
            _feasibility_mongo_db = client[db_name]
            logger.info(f"[FEASIBILITY_MONGO] Using database: {db_name}")
    
    return _feasibility_mongo_db


async def close_feasibility_mongo_client():
    """Close feasibility MongoDB client connection."""
    global _feasibility_mongo_client, _feasibility_mongo_db
    if _feasibility_mongo_client:
        _feasibility_mongo_client.close()
        _feasibility_mongo_client = None
        _feasibility_mongo_db = None
        logger.info("[FEASIBILITY_MONGO] Connection closed")

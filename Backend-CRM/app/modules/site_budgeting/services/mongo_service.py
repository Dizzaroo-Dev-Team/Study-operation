"""
SoA (Schedule of Activities) MongoDB service.
Connects to the external llm-compare Atlas cluster to fetch SoA documents.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from motor.motor_asyncio import AsyncIOMotorClient

from app.utils.log_sanitize import sfmt

logger = logging.getLogger(__name__)

SOA_DB_NAME = "test"
SOA_COLLECTION = "scheduleofactivities"

_soa_client: Optional[AsyncIOMotorClient] = None


async def _get_client() -> AsyncIOMotorClient:
    global _soa_client
    if _soa_client is None:
        from app.config import settings

        # Credential comes from the SOA_MONGO_URI env var — never hard-code it.
        if not settings.soa_mongo_uri:
            raise RuntimeError(
                "SOA_MONGO_URI is not configured — cannot reach the SoA cluster"
            )
        logger.info("[SOA_MONGO] Connecting to SoA MongoDB cluster")
        _soa_client = AsyncIOMotorClient(
            settings.soa_mongo_uri,
            serverSelectionTimeoutMS=8000,
            connectTimeoutMS=8000,
            socketTimeoutMS=20000,
            maxPoolSize=5,
        )
        try:
            import asyncio
            await asyncio.wait_for(_soa_client.admin.command("ping"), timeout=8.0)
            logger.info("[SOA_MONGO] SoA MongoDB connection OK")
        except Exception as exc:
            logger.warning("[SOA_MONGO] Ping failed: %s — will retry on first use", exc)
    return _soa_client


async def fetch_soa(study_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a Schedule of Activities document.
    Tries all known field name variations including camelCase protocolId.
    Also supports raw MongoDB ObjectId hex strings.
    """
    client = await _get_client()
    db = client[SOA_DB_NAME]
    col = db[SOA_COLLECTION]

    # Try every known id field (exact match first)
    for field in ("protocolId", "study_id", "protocol_id", "studyId", "trial_id"):
        doc = await col.find_one({field: study_id})
        if doc:
            doc.pop("_id", None)
            logger.info("[SOA_MONGO] Found SoA via field '%s' for id=%s", field, sfmt(study_id))
            return doc

    # Try by MongoDB ObjectId if input looks like a 24-char hex string
    import re as _re
    if _re.fullmatch(r"[0-9a-fA-F]{24}", study_id):
        from bson import ObjectId
        doc = await col.find_one({"_id": ObjectId(study_id)})
        if doc:
            doc.pop("_id", None)
            logger.info("[SOA_MONGO] Found SoA via _id ObjectId for id=%s", study_id)
            return doc

    # Fallback: case-insensitive regex across all id fields
    pattern = _re.compile(_re.escape(study_id), _re.IGNORECASE)
    for field in ("protocolId", "study_id", "protocol_id", "studyId"):
        doc = await col.find_one({field: {"$regex": pattern}})
        if doc:
            doc.pop("_id", None)
            logger.info("[SOA_MONGO] Found SoA (regex) via '%s' for id=%s", field, study_id)
            return doc

    logger.warning("[SOA_MONGO] No SoA document found for id=%s", study_id)
    return None


async def debug_scan() -> Dict[str, Any]:
    """Scan the Atlas cluster: list databases, find scheduleofactivities, show a sample doc's keys."""
    client = await _get_client()
    result: Dict[str, Any] = {"databases": [], "collection_found_in": None, "sample_keys": [], "sample_doc": {}}

    try:
        db_names = await client.list_database_names()
        result["databases"] = db_names
    except Exception as exc:
        result["error"] = str(exc)
        return result

    for db_name in db_names:
        if db_name in ("admin", "local", "config"):
            continue
        try:
            db = client[db_name]
            cols = await db.list_collection_names()
            if SOA_COLLECTION in cols:
                result["collection_found_in"] = db_name
                doc = await db[SOA_COLLECTION].find_one({})
                if doc:
                    doc.pop("_id", None)
                    result["sample_keys"] = list(doc.keys())
                    # Show first value of each key (truncated)
                    result["sample_doc"] = {k: str(v)[:80] for k, v in doc.items()}
                break
        except Exception as exc:
            logger.warning("[SOA_MONGO] Error scanning db %s: %s", db_name, exc)

    return result


_SOA_ID_NOISE = {"", "not provided", "n/a", "none", "unknown"}


async def list_soa_ids(limit: int | None = None) -> list[str]:
    """
    Distinct protocol/study IDs present in the SoA collection, for UI autocomplete
    + presence checks.

    Uses ``distinct`` so versioned duplicates collapse to one entry each, drops
    obvious noise ("Not Provided", empty), and returns them sorted. ``limit`` caps
    the result when given (None = all).
    """
    client = await _get_client()
    db = client[SOA_DB_NAME]
    col = db[SOA_COLLECTION]

    raw = await col.distinct("protocolId")
    ids = sorted(
        {
            str(v).strip()
            for v in raw
            if v is not None and str(v).strip().lower() not in _SOA_ID_NOISE
        },
        key=str.lower,
    )
    return ids[:limit] if limit else ids

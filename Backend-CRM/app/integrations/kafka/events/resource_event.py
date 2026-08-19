"""
Port of ``events/resourceEvent.js`` — iam.resources.events.

IAM emits three actions with this flat payload:
  created / updated / deleted →
    { id, externalId, name, level, parentId, isUnassignedNode, metadata,
      application_ids, application_keys, application_resources,
      [removed_application_id] }

No field aliases, no envelope merging, no app-allowlist filtering. A
removed_application_id signal is an unlink → treated as a delete.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.mongo import get_mongo_db

from ..models.sync_models import COLL_LOCAL_RESOURCES
from ..utils.logger import create_module_logger
from .helpers import dispatch_by_action

log = create_module_logger("KafkaConsumer")


def _notify_level3_resource_changed() -> None:
    """Neurodoc-specific level-3 change hook — no-op in this app."""
    return None


def _get_payload(envelope: dict) -> dict:
    p = (envelope or {}).get("payload")
    return p if isinstance(p, dict) else {}


def _resource_metadata(p: dict) -> dict:
    """Resource metadata (prefers the linked application_resources entry)."""
    ar_list = p.get("application_resources")
    ar = ar_list[0] if isinstance(ar_list, list) and ar_list else None
    if isinstance(ar, dict) and ar.get("metadata") is not None:
        return ar["metadata"]
    return p.get("metadata") or {}


async def upsert_resource(envelope: dict) -> None:
    """created / updated → upsert the resource row."""
    p = _get_payload(envelope)
    if not p.get("id"):
        log.warning("Resource event missing id; skip")
        return

    # An unlink rides on the resource event as removed_application_id → delete.
    if p.get("removed_application_id"):
        await delete_resource(envelope)
        return

    mongo_db = await get_mongo_db()
    await mongo_db[COLL_LOCAL_RESOURCES].update_one(
        {"_id": p["id"]},
        {
            "$set": {
                "resourceExternalId": p.get("externalId"),
                "name": p.get("name"),
                "level": int(p.get("level") or 0),
                "parentId": p.get("parentId") if p.get("parentId") is not None else None,
                "metadata": _resource_metadata(p),
                "syncedAt": datetime.now(timezone.utc),
            },
            # applicationId / appKey no longer stored; clean them off existing rows.
            "$unset": {"appKey": "", "applicationId": ""},
        },
        upsert=True,
    )
    if int(p.get("level") or 0) == 3:
        _notify_level3_resource_changed()
    log.info("Upserted local_resources from Kafka resourceId=%s externalId=%s", p["id"], p.get("externalId"))


async def delete_resource(envelope: dict) -> None:
    """deleted → remove the resource row."""
    p = _get_payload(envelope)
    resource_id = p.get("id")
    if not resource_id:
        log.warning("Resource delete event missing id; skip")
        return

    mongo_db = await get_mongo_db()
    existing = await mongo_db[COLL_LOCAL_RESOURCES].find_one({"_id": resource_id}, {"level": 1})
    await mongo_db[COLL_LOCAL_RESOURCES].delete_one({"_id": resource_id})
    if existing and int(existing.get("level") or 0) == 3:
        _notify_level3_resource_changed()
    log.info("Removed local_resources from Kafka resourceId=%s", resource_id)


async def handle_resource_message(envelope: dict) -> None:
    """iam.resources.events — dispatch to created/updated/deleted."""
    await dispatch_by_action(
        envelope,
        on_created=upsert_resource,
        on_updated=upsert_resource,
        on_deleted=delete_resource,
    )

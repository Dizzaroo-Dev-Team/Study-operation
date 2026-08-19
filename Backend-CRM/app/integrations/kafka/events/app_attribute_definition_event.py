"""
Port of ``events/appAttributeDefinitionEvent.js`` — iam.app_attribute_definition.events.

IAM emits three actions with this flat payload:
  created / updated / deleted →
    { id, application_id, application_key, key, namespace, displayName,
      dataType, constraints, isRequired, isMultiValued, isUserRequestable,
      parentId, description }

applicationId is no longer part of the sync contract — uniqueness is
{ namespace, key } and application_id from the payload is ignored.

No field aliases, no envelope merging — read the documented fields and write them
straight to local_app_attribute_definitions.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.mongo import get_mongo_db

from ..models.sync_models import COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS
from ..utils.logger import create_module_logger
from .helpers import dispatch_by_action

log = create_module_logger("KafkaConsumer")


def _get_payload(envelope: dict) -> dict:
    p = (envelope or {}).get("payload")
    return p if isinstance(p, dict) else {}


async def upsert_app_attribute_definition(envelope: dict) -> None:
    """created / updated → upsert the definition row."""
    p = _get_payload(envelope)
    if not p.get("id"):
        log.warning("App attribute definition event missing id; skip")
        return

    mongo_db = await get_mongo_db()
    await mongo_db[COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS].update_one(
        {"_id": p["id"]},
        {
            # applicationId no longer stored; clean it off existing rows.
            "$unset": {"applicationId": ""},
            "$set": {
                "namespace": p.get("namespace"),
                "key": p.get("key"),
                "displayName": p.get("displayName"),
                "dataType": p.get("dataType"),
                "constraints": p.get("constraints"),
                "isRequired": bool(p.get("isRequired")),
                "isMultiValued": bool(p.get("isMultiValued")),
                "parentId": p.get("parentId") if p.get("parentId") is not None else None,
                "description": p.get("description"),
                "syncedAt": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    log.info("Upserted local_app_attribute_definitions from Kafka defId=%s key=%s", p["id"], p.get("key"))


async def delete_app_attribute_definition(envelope: dict) -> None:
    """deleted → remove the definition row."""
    p = _get_payload(envelope)
    def_id = p.get("id")
    if not def_id:
        log.warning("App attribute definition delete event missing id; skip")
        return

    mongo_db = await get_mongo_db()
    await mongo_db[COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS].delete_one({"_id": def_id})
    log.info("Removed local_app_attribute_definitions from Kafka defId=%s", def_id)


async def handle_app_attribute_definition_message(envelope: dict) -> None:
    """iam.app_attribute_definition.events — dispatch to created/updated/deleted."""
    await dispatch_by_action(
        envelope,
        on_created=upsert_app_attribute_definition,
        on_updated=upsert_app_attribute_definition,
        on_deleted=delete_app_attribute_definition,
    )

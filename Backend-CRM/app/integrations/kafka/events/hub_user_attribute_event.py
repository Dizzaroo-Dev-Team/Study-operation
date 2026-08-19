"""
Port of ``events/hubUserAttributeEvent.js`` — iam.hub_user_attributes.events.

IAM emits three actions with this flat payload:
  created / updated → { id, user_id, attribute_key, value }
  deleted          → { id, user_id, attribute_key, value: null }

No field aliases, no envelope merging — read the documented fields and write them
straight to local_hub_user_attributes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.mongo import get_mongo_db

from ..models.sync_models import COLL_LOCAL_HUB_USER_ATTRIBUTES
from ..utils.logger import create_module_logger
from ..utils.policy_evaluation_cache import invalidate_expanded_subject_cache_for_user
from .helpers import dispatch_by_action

log = create_module_logger("HubUserAttributeEvent")


def _get_payload(envelope: dict) -> dict:
    p = (envelope or {}).get("payload")
    return p if isinstance(p, dict) else {}


async def upsert_hub_attribute(envelope: dict) -> None:
    """created / updated → upsert the hub attribute row."""
    p = _get_payload(envelope)
    user_id = p.get("user_id")
    attribute_key = p.get("attribute_key")
    value = p.get("value")
    if not user_id or not attribute_key:
        log.warning("Hub attribute event missing user_id or attribute_key; skip")
        return

    mongo_db = await get_mongo_db()
    # Filter equality fields (userId, attributeKey) are applied to the doc on
    # upsert-insert automatically, mirroring mongoose findOneAndUpdate.
    await mongo_db[COLL_LOCAL_HUB_USER_ATTRIBUTES].update_one(
        {"userId": user_id, "attributeKey": attribute_key},
        {"$set": {"value": value if value is not None else None, "syncedAt": datetime.now(timezone.utc)}},
        upsert=True,
    )
    invalidate_expanded_subject_cache_for_user(user_id)
    log.info("Upserted local_hub_user_attributes from Kafka userId=%s key=%s", user_id, attribute_key)


async def delete_hub_attribute(envelope: dict) -> None:
    """deleted → remove the hub attribute row."""
    p = _get_payload(envelope)
    user_id = p.get("user_id")
    attribute_key = p.get("attribute_key")
    if not user_id or not attribute_key:
        log.warning("Hub attribute delete event missing user_id or attribute_key; skip")
        return

    mongo_db = await get_mongo_db()
    await mongo_db[COLL_LOCAL_HUB_USER_ATTRIBUTES].delete_one(
        {"userId": user_id, "attributeKey": attribute_key}
    )
    invalidate_expanded_subject_cache_for_user(user_id)
    log.info("Removed local_hub_user_attributes from Kafka userId=%s key=%s", user_id, attribute_key)


async def handle_hub_attribute_message(envelope: dict) -> None:
    """iam.hub_attributes.events — dispatch to created/updated/deleted."""
    await dispatch_by_action(
        envelope,
        on_created=upsert_hub_attribute,
        on_updated=upsert_hub_attribute,
        on_deleted=delete_hub_attribute,
    )

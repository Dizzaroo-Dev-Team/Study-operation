"""
Port of ``events/appUserAttributeEvent.js`` — iam.app_user_attributes.events.

IAM emits three actions with this flat payload:
  created / updated → { id, application_id, user_id, attribute_def_id,
                        attribute_name, value, status, created_by }
  deleted          → { id, user_id, attribute_name }  (delete matches on
                     { userId, attributeName }; iamId is no longer stored)

No field aliases, no envelope merging — read the documented fields and write them
straight to local_app_user_attributes.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.mongo import get_mongo_db

from ..models.sync_models import COLL_LOCAL_APP_USER_ATTRIBUTES
from ..utils.logger import create_module_logger
from ..utils.policy_evaluation_cache import (
    invalidate_expanded_subject_cache_for_user,
    invalidate_policy_evaluation_caches,
)
from .helpers import dispatch_by_action

log = create_module_logger("AppUserAttributeEvent")


def _get_payload(envelope: dict) -> dict:
    p = (envelope or {}).get("payload")
    return p if isinstance(p, dict) else {}


async def upsert_app_attribute(envelope: dict) -> None:
    """created / updated → upsert the app-scoped user attribute row."""
    p = _get_payload(envelope)
    user_id = p.get("user_id")
    attribute_name = p.get("attribute_name")
    value = p.get("value")
    parent_id = p.get("parent_id")
    if not user_id or not attribute_name:
        log.warning("App attribute event missing user_id or attribute_name; skip")
        return

    # Only persist parentId when the payload carries one; otherwise remove the field.
    has_parent_id = parent_id is not None and parent_id != ""
    set_doc: dict = {"value": value if value is not None else None, "syncedAt": datetime.now(timezone.utc)}
    update: dict = {"$set": set_doc}
    unset_doc: dict = {"iamId": ""}  # iamId dropped from the sync contract; scrub old rows.
    if has_parent_id:
        set_doc["parentId"] = parent_id
    else:
        unset_doc["parentId"] = ""
    update["$unset"] = unset_doc

    mongo_db = await get_mongo_db()
    await mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].update_one(
        {"userId": user_id, "attributeName": attribute_name},
        update,
        upsert=True,
    )
    invalidate_expanded_subject_cache_for_user(user_id)
    invalidate_policy_evaluation_caches()
    log.info("Upserted local_app_user_attributes from Kafka userId=%s name=%s", user_id, attribute_name)


async def delete_app_attribute(envelope: dict) -> None:
    """
    deleted → remove the app-scoped user attribute row.

    Delete events must carry user_id + attribute_name; the row is matched on
    { userId, attributeName } (iamId is no longer stored).
    """
    p = _get_payload(envelope)
    user_id = p.get("user_id")
    attribute_name = p.get("attribute_name")

    if not user_id or not attribute_name:
        log.warning("App attribute delete event missing user_id or attribute_name; skip")
        return

    mongo_db = await get_mongo_db()
    res = await mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].delete_one(
        {"userId": user_id, "attributeName": attribute_name}
    )

    invalidate_expanded_subject_cache_for_user(user_id)
    invalidate_policy_evaluation_caches()
    log.info(
        "Removed local_app_user_attributes from Kafka userId=%s name=%s deleted=%d",
        user_id, attribute_name, res.deleted_count,
    )


async def handle_app_attribute_message(envelope: dict) -> None:
    """iam.app_user_attributes.events — dispatch to created/updated/deleted."""
    await dispatch_by_action(
        envelope,
        on_created=upsert_app_attribute,
        on_updated=upsert_app_attribute,
        on_deleted=delete_app_attribute,
    )

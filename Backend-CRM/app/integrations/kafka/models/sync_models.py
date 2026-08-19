"""
Port of ``models/syncModels.js`` (Mongoose schemas).

Motor is schema-less, so this module declares the same six collection names the
Node ``syncModels.js`` did, plus a startup helper that creates the indexes those
Mongoose schemas relied on. Collection names are byte-for-byte identical to the
reference so any Mongo DB previously fed by the Node consumer keeps working.

The IAM read path (``app.integrations.iam.users`` / ``membership`` /
``auth_profiles.routes.profiles``) imports the ``COLL_LOCAL_*`` names from here.
"""
from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorDatabase

logger = logging.getLogger("kafka.sync_models")

# ─── Collection names (1:1 with models/syncModels.js) ────────────────────────
COLL_LOCAL_USERS = "local_users"
COLL_LOCAL_HUB_USER_ATTRIBUTES = "local_hub_user_attributes"
COLL_LOCAL_APP_USER_ATTRIBUTES = "local_app_user_attributes"
COLL_LOCAL_POLICIES = "local_policies"
COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS = "local_app_attribute_definitions"
COLL_LOCAL_RESOURCES = "local_resources"


async def ensure_indexes(mongo_db: AsyncIOMotorDatabase) -> None:
    """
    Create the indexes the Mongoose schemas declared. Idempotent. Called once at
    startup from the consumer bootstrap (mirrors mongoose building indexes on
    model registration).
    """
    try:
        # localUserSchema — organization/tenant_id/status were dropped from the
        # sync contract; user status lives in local_hub_user_attributes
        # (attributeKey 'user_status').
        await mongo_db[COLL_LOCAL_USERS].create_index("email")

        # localHubUserAttributeSchema
        await mongo_db[COLL_LOCAL_HUB_USER_ATTRIBUTES].create_index("userId")
        await mongo_db[COLL_LOCAL_HUB_USER_ATTRIBUTES].create_index(
            [("userId", 1), ("attributeKey", 1)], unique=True
        )

        # localAppUserAttributeSchema
        await mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].create_index("userId")
        await mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].create_index("attributeName")
        await mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].create_index("parentId")
        await mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].create_index(
            [("userId", 1), ("attributeName", 1)], unique=True
        )

        # localPolicySchema — compound indexes for the policy-evaluation hot path.
        await mongo_db[COLL_LOCAL_POLICIES].create_index([("status", 1), ("priority", 1)])
        await mongo_db[COLL_LOCAL_POLICIES].create_index([("status", 1), ("app_id", 1)])
        await mongo_db[COLL_LOCAL_POLICIES].create_index([("status", 1), ("policy_type", 1)])
        await mongo_db[COLL_LOCAL_POLICIES].create_index(
            [("status", 1), ("app_id", 1), ("priority", 1)]
        )

        # localAppAttributeDefinitionSchema — uniqueness is { namespace, key }
        # (applicationId is no longer part of the sync contract). NOTE: a DB
        # written under the old schema already has a NON-unique namespace_1_key_1
        # index; Mongo raises code 86 on this create until the old index is
        # dropped (run the index-repair step from SYNC_MODEL_CHANGES.md once).
        await mongo_db[COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS].create_index("key")
        await mongo_db[COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS].create_index("parentId")
        await mongo_db[COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS].create_index(
            [("namespace", 1), ("key", 1)], unique=True
        )
        await mongo_db[COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS].create_index(
            [("namespace", 1), ("parentId", 1)]
        )

        # localResourceSchema
        await mongo_db[COLL_LOCAL_RESOURCES].create_index("resourceExternalId")
        await mongo_db[COLL_LOCAL_RESOURCES].create_index("level")
        await mongo_db[COLL_LOCAL_RESOURCES].create_index("parentId")
        await mongo_db[COLL_LOCAL_RESOURCES].create_index(
            [("parentId", 1), ("level", 1), ("metadata.resource_status", 1)]
        )
        await mongo_db[COLL_LOCAL_RESOURCES].create_index(
            [("resourceExternalId", 1), ("level", 1), ("metadata.resource_status", 1)]
        )

        logger.info("[kafka] Mongo indexes ensured for 6 IAM sync collections")
    except Exception as exc:  # pragma: no cover — index errors must not block startup
        logger.warning("[kafka] ensure_indexes failed: %s", exc)

"""One-time Mongo index repair for the sync-model field cleanup.

The Kafka sync contract dropped several fields (see SYNC_MODEL_CHANGES.md):
  * local_users:                     organization, tenant_id, status
  * local_hub_user_attributes:       sourceAttributeKey
  * local_app_user_attributes:       iamId, organization
  * local_app_attribute_definitions: applicationId (uniqueness is now
                                     { namespace, key })

Mongo does not rename/alter existing physical indexes when the code changes,
so a DB written under the OLD schema still carries the stale indexes — and the
old NON-unique `namespace_1_key_1` blocks `ensure_indexes` from creating the
new UNIQUE index of the same name (error code 85/86). Run this once against
such a DB, then restart the app:

    docker compose exec backend python -m scripts.repair_sync_indexes

Idempotent: missing indexes are skipped silently.
"""
from __future__ import annotations

import asyncio

from app.db.mongo import get_mongo_db
from app.integrations.kafka.models.sync_models import (
    COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS,
    COLL_LOCAL_APP_USER_ATTRIBUTES,
    COLL_LOCAL_HUB_USER_ATTRIBUTES,
    COLL_LOCAL_USERS,
    ensure_indexes,
)

# (collection, index name) pairs that existed under the old schema only.
STALE_INDEXES = [
    (COLL_LOCAL_USERS, "organization_1"),
    (COLL_LOCAL_USERS, "status_1"),
    (COLL_LOCAL_HUB_USER_ATTRIBUTES, "sourceAttributeKey_1"),
    (COLL_LOCAL_HUB_USER_ATTRIBUTES, "userId_1_sourceAttributeKey_1"),
    (COLL_LOCAL_APP_USER_ATTRIBUTES, "iamId_1"),
    (COLL_LOCAL_APP_USER_ATTRIBUTES, "organization_1"),
    (COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS, "applicationId_1"),
    (COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS, "applicationId_1_namespace_1_key_1"),
    # Old NON-unique index; dropped so ensure_indexes can recreate it unique.
    (COLL_LOCAL_APP_ATTRIBUTE_DEFINITIONS, "namespace_1_key_1"),
]


async def main() -> None:
    db = await get_mongo_db()
    for coll, name in STALE_INDEXES:
        existing = {ix["name"] async for ix in db[coll].list_indexes()}
        if name not in existing:
            print(f"  skip {coll}.{name} (not present)")
            continue
        # Don't drop a namespace_1_key_1 that is already the new unique index.
        if name == "namespace_1_key_1":
            info = [ix async for ix in db[coll].list_indexes() if ix["name"] == name][0]
            if info.get("unique"):
                print(f"  keep {coll}.{name} (already unique)")
                continue
        await db[coll].drop_index(name)
        print(f"  dropped {coll}.{name}")

    print("Recreating current indexes…")
    await ensure_indexes(db)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())

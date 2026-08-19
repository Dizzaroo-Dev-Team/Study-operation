"""Idempotent E2E seed for Playwright Communications specs.

Run INSIDE the backend container so it uses the same Mongo (crm_e2e_test) and
the same bcrypt config as the running app:

    docker compose exec backend python -m scripts.seed_e2e

Seeds, into Mongo `local_resources` / `local_users` / `local_app_user_attributes`:
  * one study resource the member can access
  * a MEMBER user (dev@gmail.com / 123456) WITH resource_access to that study
  * a NON-MEMBER user (nonmember@e2e.test / 123456) with NO access

Safe to re-run: everything is upserted by stable _id / email. Prints the ids the
Playwright env vars need. Touches only the local test DB — never the shared hub.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

from sqlalchemy import select

from app.auth import get_password_hash
from app.config import settings
from app.db import AsyncSessionLocal, engine
from app.db.mongo import get_mongo_db
from app.models.site import Site
from app.models.study import Study, StudySite

# Stable ids so the seed is idempotent and the JWT `sub` is predictable.
STUDY_ID = "e2e-study-0000-0000-0000-000000000001"   # Mongo local_resources._id (== conversation.study_id)
MEMBER_ID = "e2e-user-member-0000-0000-00000001"
NONMEMBER_ID = "e2e-user-nonmember-0000-0000-0001"

# Postgres UUIDs (the studies/sites tables require real UUIDs). The Postgres
# Study.study_id string is set to STUDY_ID so GET /api/sites?study_id=<mongo_id>
# resolves to this study.
PG_STUDY_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")
PG_SITE_UUID = uuid.UUID("22222222-2222-2222-2222-222222222222")

MEMBER_EMAIL = "dev@gmail.com"
NONMEMBER_EMAIL = "nonmember@e2e.test"
# Test-fixture password — comes from the same env var Playwright logs in with
# (E2E_USER_PASSWORD in Frontend-CRM/e2e/.env.e2e) so seed and specs never drift.
PASSWORD = os.environ.get("E2E_USER_PASSWORD") or os.environ.get("E2E_PASSWORD") or ""
if not PASSWORD:
    raise SystemExit(
        "E2E_USER_PASSWORD is not set. Export the same password the Playwright "
        "specs use (Frontend-CRM/e2e/.env.e2e) before seeding."
    )


async def main() -> None:
    db = await get_mongo_db()
    app_key = (settings.iam_application_id or "study_operations").strip().lower()
    pw_hash = get_password_hash(PASSWORD)

    # ── Study resource (what GET /api/studies returns) ────────────────────
    await db["local_resources"].update_one(
        {"_id": STUDY_ID},
        {"$set": {
            "_id": STUDY_ID,
            "appKey": app_key,
            "level": 3,
            "isActive": True,
            "name": "E2E Test Study",
            "resourceExternalId": "E2E-STUDY-001",
            "metadata": {"type": "study", "description": "Seeded for Playwright E2E", "resource_status": "active"},
        }},
        upsert=True,
    )

    # ── Users ─────────────────────────────────────────────────────────────
    await db["local_users"].update_one(
        {"_id": MEMBER_ID},
        {"$set": {
            "_id": MEMBER_ID,
            "email": MEMBER_EMAIL,
            "password_hash": pw_hash,
            "displayName": "E2E Member",
            "role": "coordinator",
        }},
        upsert=True,
    )
    await db["local_users"].update_one(
        {"_id": NONMEMBER_ID},
        {"$set": {
            "_id": NONMEMBER_ID,
            "email": NONMEMBER_EMAIL,
            "password_hash": pw_hash,
            "displayName": "E2E Non-Member",
            "role": "participant",
        }},
        upsert=True,
    )

    # Status lives in local_hub_user_attributes (attributeKey 'user_status'),
    # not on local_users — mirror the Kafka sync contract.
    for uid in (MEMBER_ID, NONMEMBER_ID):
        await db["local_hub_user_attributes"].update_one(
            {"userId": uid, "attributeKey": "user_status"},
            {"$set": {"userId": uid, "attributeKey": "user_status", "value": "active"}},
            upsert=True,
        )

    # ── Membership: member gets resource_access to the study; non-member none.
    # Unique index is on (userId, attributeName), so upsert one doc per user.
    await db["local_app_user_attributes"].update_one(
        {"userId": MEMBER_ID, "attributeName": "resource_access"},
        {"$set": {
            "userId": MEMBER_ID,
            "attributeName": "resource_access",
            "value": [{"resource_id": STUDY_ID, "role": "coordinator"}],
        }},
        upsert=True,
    )
    # Defensive: make sure the non-member has NO resource_access for this study.
    await db["local_app_user_attributes"].delete_one(
        {"userId": NONMEMBER_ID, "attributeName": "resource_access"}
    )

    await seed_postgres()

    print("=== E2E seed complete (Mongo DB: %s) ===" % settings.mongodb_database)
    print(f"E2E_STUDY_ID={STUDY_ID}")
    print(f"E2E_SITE_ID={PG_SITE_UUID}")
    print(f"E2E_USER_EMAIL={MEMBER_EMAIL}  E2E_USER_PASSWORD={PASSWORD}  (id={MEMBER_ID})")
    print(f"E2E_NONMEMBER_EMAIL={NONMEMBER_EMAIL}  E2E_NONMEMBER_PASSWORD={PASSWORD}  (id={NONMEMBER_ID})")


async def seed_postgres() -> None:
    """Seed Postgres studies/sites/study_sites so the site picker has a site.

    Idempotent: looks up by the unique string ids before inserting.
    """
    async with AsyncSessionLocal() as db:
        study = (
            await db.execute(select(Study).where(Study.study_id == STUDY_ID))
        ).scalar_one_or_none()
        if study is None:
            study = Study(
                id=PG_STUDY_UUID,
                study_id=STUDY_ID,
                name="E2E Test Study",
                description="Seeded for Playwright E2E",
                status="active",
            )
            db.add(study)

        site = (
            await db.execute(select(Site).where(Site.site_id == "E2E-SITE-001"))
        ).scalar_one_or_none()
        if site is None:
            site = Site(
                id=PG_SITE_UUID,
                site_id="E2E-SITE-001",
                name="E2E Test Site",
                code="E2E1",
                location="Test City",
                status="active",
            )
            db.add(site)

        await db.flush()

        link = (
            await db.execute(
                select(StudySite).where(
                    StudySite.study_id == study.id, StudySite.site_id == site.id
                )
            )
        ).scalar_one_or_none()
        if link is None:
            db.add(StudySite(study_id=study.id, site_id=site.id))

        await db.commit()


async def teardown() -> None:
    """Delete the e2e seed (and e2e-scoped data), scoped by the known ids.

    SAFETY: Mongo deletes run only when the target DB name contains "test".
    Postgres deletes run only when the Postgres DB name contains "test" — the
    local dev DB is `crm_db` (no "test"), so the Postgres rows are intentionally
    NOT touched here and are reported instead.
    """
    mongo_db_name = settings.mongodb_database or ""
    if "test" not in mongo_db_name.lower():
        print(f"ABORT: Mongo target '{mongo_db_name}' is not a test DB — refusing to delete.")
        return

    e2e_study_ids = [STUDY_ID, str(PG_STUDY_UUID)]
    db = await get_mongo_db()
    print(f"=== E2E TEARDOWN — Mongo target: {mongo_db_name} ===")

    # Snapshot NON-e2e counts (must be unchanged afterwards).
    users_total_before = await db["local_users"].count_documents({})
    res_total_before = await db["local_resources"].count_documents({})
    e2e_user_ids = [MEMBER_ID, NONMEMBER_ID]
    nonE2E_users_before = await db["local_users"].count_documents({"_id": {"$nin": e2e_user_ids}})
    nonE2E_res_before = await db["local_resources"].count_documents({"_id": {"$nin": [STUDY_ID]}})

    # Collect e2e-scoped conversation / thread ids so dependent docs can be
    # removed by those ids (no blanket wipe).
    conv_ids = [
        str(c.get("id"))
        async for c in db["conversations"].find({"study_id": {"$in": e2e_study_ids}}, {"id": 1})
        if c.get("id") is not None
    ]
    thread_ids = [
        str(t.get("id"))
        async for t in db["threads"].find({"related_study_id": {"$in": e2e_study_ids}}, {"id": 1})
        if t.get("id") is not None
    ]

    deleted = {}

    async def _del(coll, query, label):
        res = await db[coll].delete_many(query)
        deleted[label] = res.deleted_count

    # Dependent docs first (by the scoped conv/thread ids).
    await _del("messages", {"conversation_id": {"$in": conv_ids}}, "messages")
    await _del("attachments", {"conversation_id": {"$in": conv_ids}}, "attachments")
    await _del("thread_messages", {"thread_id": {"$in": thread_ids}}, "thread_messages")
    await _del("thread_attachments", {"thread_id": {"$in": thread_ids}}, "thread_attachments")
    await _del("thread_participants", {"thread_id": {"$in": thread_ids}}, "thread_participants")
    await _del("thread_from_conversations", {"thread_id": {"$in": thread_ids}}, "thread_from_conversations")
    # The conversations / threads themselves.
    await _del("conversations", {"study_id": {"$in": e2e_study_ids}}, "conversations")
    await _del("threads", {"related_study_id": {"$in": e2e_study_ids}}, "threads")
    # Users, memberships, study resource — by exact known ids.
    await _del("local_app_user_attributes", {"userId": {"$in": e2e_user_ids}}, "local_app_user_attributes")
    await _del("local_hub_user_attributes", {"userId": {"$in": e2e_user_ids}}, "local_hub_user_attributes")
    await _del("local_users", {"_id": {"$in": e2e_user_ids}}, "local_users(by_id)")
    await _del("local_users", {"email": {"$in": [MEMBER_EMAIL, NONMEMBER_EMAIL]}}, "local_users(by_email)")
    await _del("local_resources", {"_id": STUDY_ID}, "local_resources")

    print("Mongo deleted (by e2e id scope):")
    for k, v in deleted.items():
        print(f"  {k}: {v}")

    # Prove nothing outside the e2e scope was removed.
    nonE2E_users_after = await db["local_users"].count_documents({"_id": {"$nin": e2e_user_ids}})
    nonE2E_res_after = await db["local_resources"].count_documents({"_id": {"$nin": [STUDY_ID]}})
    users_total_after = await db["local_users"].count_documents({})
    res_total_after = await db["local_resources"].count_documents({})
    print("\nScope check (non-e2e records must be unchanged):")
    print(f"  local_users  total {users_total_before}->{users_total_after}  | non-e2e {nonE2E_users_before}->{nonE2E_users_after}")
    print(f"  local_resources total {res_total_before}->{res_total_after}  | non-e2e {nonE2E_res_before}->{nonE2E_res_after}")
    assert nonE2E_users_before == nonE2E_users_after, "non-e2e users changed!"
    assert nonE2E_res_before == nonE2E_res_after, "non-e2e resources changed!"

    # ── Postgres: self-guard. Only delete from a *test* Postgres DB. ──────────
    pg_db_name = (engine.url.database or "")
    if "test" not in pg_db_name.lower():
        print(
            f"\nPostgres SKIPPED (safety): target DB '{pg_db_name}' is not a test DB. "
            f"The e2e Postgres rows were NOT deleted. To remove them manually, delete "
            f"(in this order) from '{pg_db_name}': "
            f"study_sites where study_id='{PG_STUDY_UUID}', "
            f"sites where id='{PG_SITE_UUID}' (site_id='E2E-SITE-001'), "
            f"studies where id='{PG_STUDY_UUID}' (study_id='{STUDY_ID}')."
        )
    else:
        async with AsyncSessionLocal() as pg:
            await pg.execute(StudySite.__table__.delete().where(StudySite.study_id == PG_STUDY_UUID))
            await pg.execute(Site.__table__.delete().where(Site.id == PG_SITE_UUID))
            await pg.execute(Study.__table__.delete().where(Study.id == PG_STUDY_UUID))
            await pg.commit()
        print(f"\nPostgres deleted e2e study/site/link from '{pg_db_name}'.")

    print("\n=== E2E TEARDOWN complete ===")


if __name__ == "__main__":
    if "--teardown" in sys.argv:
        asyncio.run(teardown())
    else:
        asyncio.run(main())

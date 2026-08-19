"""One-off diagnostic: dump notice-board docs for the (site, study) combo
that the unique-index build keeps rejecting, plus list existing indexes
and drop any stale failed-build attempt of the notice-board unique index.

Run:
    docker exec -i backend-crm-backend-1 python -m scripts.debug_notice_board
"""
import asyncio
from app.db.mongo import get_mongo_db, close_mongo_client


async def main():
    db = await get_mongo_db()
    target_site = "SITE- DP-5K0-A41-1D02"
    target_study = "841a0274-c446-4e49-a92c-551008aa9668"

    cursor = db["conversations"].find({
        "site_id": target_site,
        "study_id": target_study,
        "conversation_type": "notice_board",
    })
    docs = await cursor.to_list(length=None)
    print(f"notice_board docs for ({target_site}, {target_study}): {len(docs)}")
    for d in docs:
        print(f"  id={d.get('id')} is_pinned={d.get('is_pinned')!r} "
              f"created_at={d.get('created_at')}")

    info = await db["conversations"].index_information()
    print("\nexisting indexes:")
    for name, meta in info.items():
        print(f"  {name}: {meta}")

    if "notice_board_unique_per_site_study" in info:
        try:
            await db["conversations"].drop_index("notice_board_unique_per_site_study")
            print("\ndropped notice_board_unique_per_site_study (stale attempt)")
        except Exception as e:
            print(f"\ndrop failed: {e}")

    await close_mongo_client()


if __name__ == "__main__":
    asyncio.run(main())

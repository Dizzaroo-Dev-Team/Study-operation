"""Show the live notice_board_unique index spec + count docs in/out of filter."""
import asyncio
from app.db.mongo import get_mongo_db, close_mongo_client


async def main():
    db = await get_mongo_db()
    info = await db["conversations"].index_information()
    nb = info.get("notice_board_unique_per_site_study")
    print("notice_board_unique_per_site_study:", nb)

    # Count docs that should be IN the index (per the partial filter)
    in_filter = await db["conversations"].count_documents({
        "conversation_type": "notice_board",
        "is_pinned": {"$in": ["true", True]},
    })
    print(f"docs matching partial filter (should be in index): {in_filter}")

    # Count notice_board docs with is_pinned='false' (should be OUT of index)
    out_filter = await db["conversations"].count_documents({
        "conversation_type": "notice_board",
        "is_pinned": {"$nin": ["true", True]},
    })
    print(f"notice_board docs with is_pinned NOT true (should be out of index): {out_filter}")

    # The specific (site, study) that's failing right now
    target = await db["conversations"].count_documents({
        "site_id": "SITE-482-5K0-A41-580E",
        "study_id": "f29f2acc-f534-4e6d-af5b-3860930b9cc1",
        "conversation_type": "notice_board",
    })
    print(f"docs at (SITE-482-..., f29f2acc-...) with conversation_type=notice_board: {target}")

    # Show each by is_pinned
    async for d in db["conversations"].find({
        "site_id": "SITE-482-5K0-A41-580E",
        "study_id": "f29f2acc-f534-4e6d-af5b-3860930b9cc1",
        "conversation_type": "notice_board",
    }):
        print(f"  id={d.get('id')} is_pinned={d.get('is_pinned')!r} created_at={d.get('created_at')}")

    await close_mongo_client()


if __name__ == "__main__":
    asyncio.run(main())

"""Merge duplicate Public Notice Board conversations.

Why
---
The previous `ensure_public_notice_board` helper used a check-then-create
pattern that wasn't atomic. Two concurrent calls (two browser tabs, two
route mounts) could both see "no notice board" and both insert, leaving a
trail of duplicate `Public Notice Board` entries in the user's inbox
sidebar.

The application code now uses an atomic upsert (and a unique partial-filter
index will enforce it at the storage layer), but this script cleans up
duplicates that already landed in Mongo.

Strategy per (site_id, study_id) group with > 1 pinned notice_board:
  1. Pick the WINNER:
       - Conversation with the most messages, OR
       - Tie-break by oldest `created_at`, OR
       - Final tie-break by `id` (deterministic).
  2. Re-point any messages / attachments / etc. that reference the losing
     conversation IDs at the winner. (Messages collection: update
     `conversation_id`.)
  3. Delete the losing conversation rows.

Idempotent — re-runnable. Does nothing when no duplicates remain.

Run
---
    docker exec -i backend-crm-backend-1 \
        python -m scripts.dedupe_notice_boards [--dry-run]

(or against prod by passing MONGODB_URI via env)
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from collections import defaultdict
from typing import Any, Dict, List

from app.db.mongo import get_mongo_db, close_mongo_client


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("dedupe_notice_boards")


async def find_duplicate_groups(db) -> Dict[tuple, List[Dict[str, Any]]]:
    """Return groups of pinned notice boards keyed by (site_id, study_id)
    that have > 1 doc.
    """
    cursor = db["conversations"].find(
        {
            "conversation_type": "notice_board",
            "is_pinned": {"$in": ["true", True]},
        }
    )
    groups: Dict[tuple, List[Dict[str, Any]]] = defaultdict(list)
    async for doc in cursor:
        key = (doc.get("site_id"), doc.get("study_id"))
        groups[key].append(doc)
    return {k: v for k, v in groups.items() if len(v) > 1}


async def count_messages_for(db, conv_id: Any) -> int:
    return await db["messages"].count_documents({"conversation_id": str(conv_id)})


async def pick_winner(db, candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    # Annotate each with its message count, then sort: most-messages first,
    # oldest created_at next, lexicographic id last.
    with_counts: List[tuple] = []
    for c in candidates:
        msg_count = await count_messages_for(db, c.get("id"))
        with_counts.append((msg_count, c))
    with_counts.sort(
        key=lambda pair: (
            -pair[0],
            pair[1].get("created_at") or "",
            str(pair[1].get("id") or ""),
        )
    )
    return with_counts[0][1]


async def merge_group(db, winner: Dict[str, Any], losers: List[Dict[str, Any]],
                      dry_run: bool) -> Dict[str, int]:
    winner_id = str(winner.get("id"))
    moved_messages = 0
    moved_attachments = 0
    deleted_convs = 0

    for loser in losers:
        loser_id = str(loser.get("id"))
        if loser_id == winner_id:
            continue

        # Move messages
        if dry_run:
            n = await db["messages"].count_documents({"conversation_id": loser_id})
        else:
            res = await db["messages"].update_many(
                {"conversation_id": loser_id},
                {"$set": {"conversation_id": winner_id}},
            )
            n = res.modified_count
        moved_messages += n

        # Move attachments (if a separate collection — some setups embed
        # attachments in messages).
        if "attachments" in await db.list_collection_names():
            if dry_run:
                m = await db["attachments"].count_documents({"conversation_id": loser_id})
            else:
                res = await db["attachments"].update_many(
                    {"conversation_id": loser_id},
                    {"$set": {"conversation_id": winner_id}},
                )
                m = res.modified_count
            moved_attachments += m

        # Delete the loser conversation row.
        if dry_run:
            deleted_convs += 1
        else:
            await db["conversations"].delete_one({"id": loser_id})
            deleted_convs += 1

    return {
        "moved_messages": moved_messages,
        "moved_attachments": moved_attachments,
        "deleted_convs": deleted_convs,
    }


async def main(dry_run: bool) -> None:
    db = await get_mongo_db()
    groups = await find_duplicate_groups(db)

    if not groups:
        logger.info("No duplicate notice boards found. Nothing to do.")
        await close_mongo_client()
        return

    logger.info("Found %d (site, study) groups with duplicates", len(groups))
    totals = {"moved_messages": 0, "moved_attachments": 0, "deleted_convs": 0}
    for key, candidates in groups.items():
        site_id, study_id = key
        logger.info(
            "Group site_id=%s study_id=%s: %d candidates",
            site_id, study_id, len(candidates),
        )
        winner = await pick_winner(db, candidates)
        winner_id = str(winner.get("id"))
        losers = [c for c in candidates if str(c.get("id")) != winner_id]
        logger.info("  winner=%s losers=%s", winner_id, [str(l.get("id")) for l in losers])

        stats = await merge_group(db, winner, losers, dry_run=dry_run)
        for k, v in stats.items():
            totals[k] += v
        logger.info(
            "  moved_messages=%d moved_attachments=%d deleted_convs=%d",
            stats["moved_messages"], stats["moved_attachments"], stats["deleted_convs"],
        )

    label = "(dry-run, no writes)" if dry_run else "(applied)"
    logger.info(
        "Done %s — total moved_messages=%d moved_attachments=%d deleted_convs=%d",
        label, totals["moved_messages"], totals["moved_attachments"], totals["deleted_convs"],
    )

    await close_mongo_client()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing.",
    )
    args = parser.parse_args()
    # Exit 0 on success; an exception propagates and exits non-zero as before.
    asyncio.run(main(dry_run=args.dry_run))

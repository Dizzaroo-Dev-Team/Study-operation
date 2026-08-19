"""
MongoDB database connection and client setup.
This module handles MongoDB connections for conversation, message, and thread data.
"""
import os
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import NetworkTimeout, OperationFailure, ServerSelectionTimeoutError
from app.config import settings
import logging

# MongoDB error code for "an existing index has the same name but a different
# spec" (covers both IndexOptionsConflict and IndexKeySpecsConflict). When we
# tighten the spec of a long-lived partial-filter index, the old index doesn't
# get auto-replaced — Mongo just refuses the new create_index call. Treat as
# benign when the old index's invariant is a superset of the new one.
_MONGO_INDEX_SPECS_CONFLICT = 86

logger = logging.getLogger(__name__)

# Pool sizing — tunable per environment. The previous default of maxPoolSize=10
# starves under modest concurrency; the audit measured >200ms tail latency on
# Mongo conversation reads when 4+ requests hit the same collection in
# parallel because new connections were being negotiated mid-request.
MONGO_MAX_POOL = int(os.getenv("MONGO_MAX_POOL", "50"))
MONGO_MIN_POOL = int(os.getenv("MONGO_MIN_POOL", "5"))

# MongoDB client singleton
_mongo_client: AsyncIOMotorClient = None
_mongo_db = None

# Strong references to fire-and-forget tasks so the event loop can't GC them
# before they finish (tasks remove themselves on completion).
_background_tasks: set = set()


async def get_mongo_client() -> AsyncIOMotorClient:
    """Get or create MongoDB client singleton. Lazy initialization - only connects when needed."""
    global _mongo_client
    if _mongo_client is None:
        logger.info(f"[MONGO] Connecting to MongoDB at {settings.mongodb_uri}")
        # Add connection timeout and server selection timeout to prevent hanging
        _mongo_client = AsyncIOMotorClient(
            settings.mongodb_uri,
            serverSelectionTimeoutMS=3000,  # 3 second timeout - fail fast
            connectTimeoutMS=3000,
            socketTimeoutMS=10000,  # 10 second socket timeout
            maxPoolSize=MONGO_MAX_POOL,
            minPoolSize=MONGO_MIN_POOL,
        )
        # Test connection with timeout - but don't block if it fails
        try:
            import asyncio
            await asyncio.wait_for(_mongo_client.admin.command('ping'), timeout=3.0)
            logger.info("[MONGO] MongoDB connection successful")
        except asyncio.TimeoutError:
            logger.warning("[MONGO] MongoDB connection timed out - will retry on use")
            # Keep client but mark as potentially unavailable
        except Exception as e:
            logger.warning(f"[MONGO] MongoDB connection failed: {e} - will retry on use")
            # Don't raise - allow app to continue
    return _mongo_client


_indexes_ensured = False


async def _ensure_conversation_indexes(db) -> None:
    """Idempotent index creation for the conversations + threads alias lookups.

    Called once on first DB access. Mongo's create_index is idempotent so we
    can call it on every cold start without risk.
    """
    global _indexes_ensured
    if _indexes_ensured:
        return
    try:
        await db["conversations"].create_index(
            "email_alias",
            sparse=True,
            name="email_alias_idx",
        )
        await db["threads"].create_index(
            "email_alias",
            sparse=True,
            name="email_alias_idx",
        )
        await db["conversations"].create_index(
            "email_alias_base",
            sparse=True,
            name="email_alias_base_idx",
        )
        await db["threads"].create_index(
            "email_alias_base",
            sparse=True,
            name="email_alias_base_idx",
        )
        # Compound index that powers `ConversationRepository.list()`:
        # notice_board first (alphabetically < 'thread'), newest within each
        # bucket. Lets Mongo do sort + skip + limit at the DB layer instead
        # of fetch-all-then-sort-in-Python.
        await db["conversations"].create_index(
            [("conversation_type", ASCENDING), ("created_at", DESCENDING)],
            name="conversations_type_then_recent_idx",
        )
        _indexes_ensured = True
        logger.info("[MONGO] Ensured email_alias + conversations_type_then_recent indexes")
    except Exception as e:
        logger.warning(f"[MONGO] Failed to create email_alias / conversations_type_then_recent index: {e}")

    # Unique partial-filter index: at most ONE pinned Notice Board per
    # (site, study). Closes the race that produced duplicate boards in the
    # inbox sidebar. Partial-filter scope keeps the constraint from blocking
    # ordinary conversations.
    #
    # The index creation can fail if existing duplicates are present (Mongo
    # refuses to create a unique index that would already be violated). In
    # that case we log a warning and continue — operator must first run
    # `Backend-CRM/scripts/dedupe_notice_boards.py` to merge duplicates,
    # then restart the app for the index to land.
    try:
        # Uniqueness invariant is "one notice_board per (site, study)" —
        # `is_pinned` used to be in the partial filter as a workaround for
        # the legacy string-mess (`'true'` vs `True`), but pinning is now
        # implied by `conversation_type == 'notice_board'`. Dropping the
        # is_pinned clause tightens the constraint and removes the need
        # for the `["true", True]` $in workaround.
        await db["conversations"].create_index(
            [("site_id", 1), ("study_id", 1), ("conversation_type", 1)],
            unique=True,
            partialFilterExpression={"conversation_type": "notice_board"},
            name="notice_board_unique_per_site_study",
        )
        logger.info("[MONGO] Ensured unique notice_board index")
    except OperationFailure as e:
        if getattr(e, "code", None) == _MONGO_INDEX_SPECS_CONFLICT:
            # The old index already exists with the legacy partial filter
            # `{conversation_type: "notice_board", is_pinned: {$in: ["true", true]}}`.
            # Every valid notice_board doc has `is_pinned: "true"` by contract,
            # so the legacy index still enforces uniqueness for us — no need
            # to drop+recreate during normal startup (which would briefly leave
            # the collection without a unique constraint).
            #
            # To migrate to the simplified spec, run this in a maintenance window
            # then redeploy:
            #
            #     db.conversations.dropIndex('notice_board_unique_per_site_study')
            #
            # Until then, log INFO and continue — this is not a startup-blocking
            # condition.
            logger.info(
                "[MONGO] notice_board unique index already exists with the legacy "
                "partial-filter spec (includes is_pinned clause); keeping it. "
                "Uniqueness invariant is still enforced for all conformant docs. "
                "To migrate to the simplified spec, drop the index in a "
                "maintenance window then redeploy."
            )
        else:
            logger.exception(
                "[MONGO] Could not create notice_board unique index "
                "(existing duplicates? run scripts/dedupe_notice_boards.py): %s", e,
            )
            raise
    except (ServerSelectionTimeoutError, NetworkTimeout) as e:
        logger.warning(
            "[MONGO] Skipping notice_board unique index — MongoDB unreachable: %s", e
        )
        return
    except Exception as e:
        logger.exception(
            "[MONGO] Could not create notice_board unique index "
            "(existing duplicates? run scripts/dedupe_notice_boards.py): %s", e,
        )
        raise


async def get_mongo_db():
    """Get MongoDB database instance."""
    global _mongo_db
    if _mongo_db is None:
        client = await get_mongo_client()
        _mongo_db = client[settings.mongodb_database]
        # Best-effort: kick off index creation but don't block the caller.
        # Preferred path is `ensure_mongo_indexes()` from main.py lifespan,
        # which awaits the creation before traffic is served. This branch
        # remains a safety net for any code path that touches Mongo before
        # lifespan finishes (workers, scripts, tests).
        try:
            import asyncio

            async def _ensure_conversation_indexes_task() -> None:
                try:
                    await _ensure_conversation_indexes(_mongo_db)
                except Exception as exc:
                    logger.warning(
                        "[MONGO] Background index ensure failed (will retry on next access): %s",
                        exc,
                    )

            # Keep a strong reference until done — a bare create_task() result
            # can be garbage-collected mid-flight, silently dropping the task.
            task = asyncio.create_task(_ensure_conversation_indexes_task())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        except Exception:
            pass
    return _mongo_db


async def ensure_mongo_indexes() -> None:
    """Block-and-await Mongo index creation.

    Call from FastAPI's lifespan startup so the first request after a deploy
    never pays index-build latency (~50-500ms on cold collections). The
    fire-and-forget path inside `get_mongo_db()` remains for safety.

    Note: a failure to create the load-bearing `notice_board_unique_per_site_study`
    index will now propagate — booting without it lets duplicate notice
    boards land under concurrency. Operator must clean duplicates with
    `Backend-CRM/scripts/dedupe_notice_boards.py` and redeploy.
    """
    client = await get_mongo_client()
    db = client[settings.mongodb_database]
    await _ensure_conversation_indexes(db)


async def next_sequence(name: str) -> int:
    """Atomically increment and return the next integer for a named counter.

    Used to assign a per-(study,site) sequential number to new conversations
    and threads, so their email alias can be short and human-readable
    (``studyx-site009-c1`` rather than UUID hex). The increment is atomic at
    the MongoDB level — concurrent creates cannot get the same number.
    """
    from pymongo import ReturnDocument

    db = await get_mongo_db()
    doc = await db["counters"].find_one_and_update(
        {"_id": name},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )
    return int(doc.get("seq") or 1)


async def close_mongo_client():
    """Close MongoDB client connection."""
    global _mongo_client, _mongo_db
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
        _mongo_db = None
        logger.info("[MONGO] MongoDB connection closed")

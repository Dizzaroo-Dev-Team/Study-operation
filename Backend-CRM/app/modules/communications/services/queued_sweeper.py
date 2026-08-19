"""Stuck-QUEUED message sweeper (Batch-6 MSG-QUEUED-NOSWEEP, Job C STEP 3).

If a send enqueue was ever dropped (the FF-1 bug), the message sits ``QUEUED``
forever with no worker ever re-scanning it. This sweeper finds those and
re-enqueues ``send_message_task``.

Safety (two-phase Option B):
  * It selects ONLY messages that are ``status == 'queued'`` AND have NO
    ``send_attempted_at`` (a true dropped-enqueue that was never sent) AND are
    older than ``threshold_minutes``. A message that was ever attempted carries
    ``send_attempted_at`` and is excluded here — the task escalates those to
    NEEDS_REVIEW; the sweeper never re-sends them.
  * ``dry_run=True`` (default) → list only, never re-enqueue. Actual re-enqueue
    requires an explicit ``dry_run=False`` invocation; the sweep never
    re-enqueues on its own.
  * The re-enqueued task itself does an atomic queued→sending claim, so even a
    double-enqueue cannot double-send.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import logging

from app.db.mongo import get_mongo_db

logger = logging.getLogger(__name__)

_CONV_COLLECTION = "messages"
_THREAD_COLLECTION = "thread_messages"
_MAX_PER_SWEEP = 1000


async def _find_stuck(collection, cutoff) -> List[str]:
    query = {
        "status": "queued",
        "send_attempted_at": {"$exists": False},
        "created_at": {"$lt": cutoff},
    }
    docs = await collection.find(query, {"id": 1}).limit(_MAX_PER_SWEEP).to_list(length=_MAX_PER_SWEEP)
    return [str(d.get("id")) for d in docs if d.get("id")]


async def sweep_stuck_queued_messages(threshold_minutes: int = 15, dry_run: bool = True) -> Dict:
    """Find (and, when enabled, re-enqueue) never-attempted stuck-QUEUED messages.

    Returns a report dict: threshold_minutes, dry_run, sweep_enabled,
    candidates[], would_reenqueue[], reenqueued[].
    """
    db = await get_mongo_db()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)

    conv_ids = await _find_stuck(db[_CONV_COLLECTION], cutoff)
    thread_ids = await _find_stuck(db[_THREAD_COLLECTION], cutoff)
    candidates = (
        [{"id": i, "source_type": "conversation"} for i in conv_ids]
        + [{"id": i, "source_type": "thread"} for i in thread_ids]
    )

    report: Dict = {
        "threshold_minutes": threshold_minutes,
        "dry_run": dry_run,
        "candidates": candidates,
        "would_reenqueue": [],
        "reenqueued": [],
    }

    if dry_run:
        report["would_reenqueue"] = list(candidates)
        return report

    from app.workers.tasks import send_message_task
    for c in candidates:
        try:
            if c["source_type"] == "thread":
                send_message_task.delay(c["id"], source_type="thread")
            else:
                send_message_task.delay(c["id"])
            report["reenqueued"].append(c)
        except Exception as e:
            logger.warning("sweep_stuck_queued_messages: re-enqueue failed for %s: %s", c["id"], e)
    return report

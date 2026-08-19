"""CLI for the stuck-QUEUED message sweeper.

Dry-run by default (lists only). Actual re-enqueue requires BOTH ``--apply``
AND ``COMMS_QUEUED_SWEEP=true`` in the environment. Only ever re-enqueues
messages that were QUEUED past the threshold with NO prior send attempt.

    python scripts/sweep_stuck_queued.py --threshold-minutes 15
    COMMS_QUEUED_SWEEP=true python scripts/sweep_stuck_queued.py --apply
"""
import argparse
import asyncio
import json

from app.modules.communications.services.queued_sweeper import (
    sweep_stuck_queued_messages,
)


async def _run(threshold_minutes: int, apply: bool) -> None:
    report = await sweep_stuck_queued_messages(
        threshold_minutes=threshold_minutes, dry_run=not apply
    )
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-enqueue never-attempted stuck-QUEUED messages.")
    parser.add_argument("--threshold-minutes", type=int, default=15)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually re-enqueue (also requires COMMS_QUEUED_SWEEP=true)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.threshold_minutes, args.apply))

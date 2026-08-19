"""
Manual end-to-end check for the site-milestone Kafka PRODUCER.

Publishes one `site_milestone.*` envelope to the Data Platform Kafka topic
using the same producer the app uses at runtime.

Requires these env vars (in Backend-CRM/.env or the shell):
    START_MILESTONES_PRODUCER=true
    KAFKA_BROKERS=<host:port>[,<host:port>...]

Usage (from Backend-CRM/):
    python -m scripts.send_sample_site_milestone_event
    python -m scripts.send_sample_site_milestone_event --milestone CTA_FULLY_EXECUTED
    python -m scripts.send_sample_site_milestone_event --event-type site_milestone.created
    python -m scripts.send_sample_site_milestone_event --event-type site_milestone.deleted
    python -m scripts.send_sample_site_milestone_event \
        --site-id 69b4a7f8-b6a9-44c1-9e71-477f296d7e12 --milestone SITE_SELECTED
"""
from __future__ import annotations

import argparse
import asyncio

from app.integrations.milestones_kafka import (
    SiteMilestone,
    delete_site_milestone,
    publish_site_milestone,
    start_milestones_producer,
    stop_milestones_producer,
)


async def _main() -> None:
    parser = argparse.ArgumentParser(description="Send a sample site-milestone event")
    parser.add_argument(
        "--event-type",
        default="created",
        choices=["created", "updated", "deleted"],
    )
    parser.add_argument("--site-id", default="69b4a7f8-b6a9-44c1-9e71-477f296d7e12")
    parser.add_argument(
        "--milestone",
        default="SIV_CONDUCTED",
        choices=[m.milestone_id for m in SiteMilestone],
        help="Milestone id (ignored for deleted)",
    )
    args = parser.parse_args()

    await start_milestones_producer()
    try:
        if args.event_type == "deleted":
            ok = await delete_site_milestone(site_id=args.site_id)
        else:
            ok = await publish_site_milestone(
                args.milestone,
                site_id=args.site_id,
                event_type=args.event_type,
            )
        print("published" if ok else "NOT published (producer disabled/unavailable — check env)")
    finally:
        await stop_milestones_producer()


if __name__ == "__main__":
    asyncio.run(_main())

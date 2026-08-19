"""CLI for the orphan-attachment-file reconciler.

Dry-run by default (lists only). Actual deletion requires BOTH
``--apply`` AND ``COMMS_ATTACHMENT_CLEANUP=true`` in the environment.

    python scripts/reconcile_orphan_attachments.py            # dry-run, list orphans
    COMMS_ATTACHMENT_CLEANUP=true python scripts/reconcile_orphan_attachments.py --apply
"""
import argparse
import asyncio
import json

from app.modules.communications.services.attachment_cleanup import (
    reconcile_orphan_attachment_files,
)


async def _run(apply: bool) -> None:
    report = await reconcile_orphan_attachment_files(dry_run=not apply)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reconcile orphan attachment files.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete orphans (also requires COMMS_ATTACHMENT_CLEANUP=true)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.apply))

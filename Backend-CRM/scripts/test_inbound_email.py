"""Simulate a Mailgun inbound-email webhook against a running CRM.

Why this exists
---------------
Mailgun can only POST to a publicly reachable URL, so a local backend never
receives real inbound mail unless you tunnel to it. That makes "replies don't
show up in the conversation" hard to diagnose: you cannot tell whether the
webhook, the Celery worker, the alias resolution, or Mailgun's Route is at
fault. This script forges a correctly-signed webhook so you can exercise the
whole inbound path — signature check, alias -> conversation resolution, message
insert, WebSocket broadcast — without Mailgun involved.

Usage (inside the backend container, where MAILGUN_SIGNING_KEY is set):

    docker exec backend-crm-backend-1 python scripts/test_inbound_email.py \
        --recipient mk-6482-site-482-5k0-a41-580e-c14@mg.dizzaroo.com \
        --sender you@example.com \
        --body "Hi crm team"

Then check the worker log for the outcome:

    docker logs --since 2m backend-crm-worker-1

A 200 here only means the webhook ACCEPTED and enqueued the job — the write
happens in Celery. If the worker is down, this still returns 200 and the message
is silently never stored. That asymmetry is the single most common cause of
"sending works, receiving doesn't", so always check the worker log too.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import sys
import time

import httpx


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--recipient", required=True, help="conversation alias address")
    parser.add_argument("--sender", default="test@example.com")
    parser.add_argument("--subject", default="Inbound webhook test")
    parser.add_argument("--body", default="Test inbound message")
    parser.add_argument("--url", default="http://localhost:8000/api/webhooks/email/mailgun")
    args = parser.parse_args()

    signing_key = os.getenv("MAILGUN_SIGNING_KEY")
    if not signing_key:
        print("ERROR: MAILGUN_SIGNING_KEY is not set — the webhook would reject this "
              "with 406. Run inside the backend container.", file=sys.stderr)
        return 2

    # Mailgun signs sha256_hmac(signing_key, timestamp + token). The route also
    # rejects stale timestamps, so sign 'now'.
    timestamp = str(int(time.time()))
    token = "0" * 50
    signature = hmac.new(
        signing_key.encode(), (timestamp + token).encode(), hashlib.sha256
    ).hexdigest()

    form = {
        "timestamp": timestamp,
        "token": token,
        "signature": signature,
        "recipient": args.recipient,
        "sender": args.sender,
        "subject": args.subject,
        "body-plain": args.body,
        "stripped-text": args.body,
        "Message-Id": f"<inbound-test-{timestamp}@example.com>",
    }

    try:
        resp = httpx.post(args.url, data=form, timeout=30.0)
    except Exception as exc:
        print(f"REQUEST FAILED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    print(f"HTTP {resp.status_code}: {resp.text[:400]}")
    if resp.status_code == 200:
        print("\nWebhook accepted and enqueued. Now confirm the WRITE actually "
              "happened:\n  docker logs --since 2m backend-crm-worker-1")
        print("Expect: 'Found conversation' then 'Created inbound message'.")
        print("If you see neither, the Celery worker is not consuming the queue.")
        return 0
    if resp.status_code == 406:
        print("\n406 means the signature/recipient fields were rejected — check "
              "MAILGUN_SIGNING_KEY matches the Mailgun account sending the Route.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

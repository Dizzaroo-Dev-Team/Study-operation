
from fastapi import APIRouter, HTTPException, Request
from typing import Optional
import hmac
import hashlib
import logging
import time

from app.config import settings
from app.utils.html_sanitize import escape_plaintext, strip_dangerous_html
from app.workers.tasks import process_webhook_task

router = APIRouter(prefix="/webhooks/email", tags=["email-webhook"])
logger = logging.getLogger(__name__)

# Mailgun webhooks are typically delivered within seconds; reject anything
# older than this window as a replay attempt. Five minutes matches the
# Mailgun-recommended freshness check.
MAILGUN_REPLAY_WINDOW_SECONDS: int = 300


def verify_mailgun_signature(timestamp: str, token: str, signature: str):
    if not settings.mailgun_signing_key:
        raise RuntimeError("MAILGUN_SIGNING_KEY must be set")

    # Reject stale timestamps before doing the HMAC dance: a replayed
    # payload still has a valid signature, so freshness is the only thing
    # that stops attackers from re-submitting captured webhooks.
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid Mailgun timestamp")
    now = int(time.time())
    if abs(now - ts_int) > MAILGUN_REPLAY_WINDOW_SECONDS:
        logger.warning(
            "Rejecting Mailgun webhook with stale timestamp: ts=%s now=%s delta=%s",
            ts_int, now, now - ts_int,
        )
        raise HTTPException(status_code=403, detail="Mailgun webhook timestamp out of window")

    msg = f"{timestamp}{token}".encode()
    key = settings.mailgun_signing_key.encode()

    expected = hmac.new(key, msg, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=403, detail="Invalid Mailgun signature")


# Mailgun's configured Route forwards to /api/webhooks/email/inbound, while the
# original handler path was /mailgun. Register BOTH so inbound delivery works
# regardless of which the Mailgun dashboard points at (same handler/signature
# check either way).
@router.post("/inbound")
@router.post("/mailgun")
async def mailgun_inbound(request: Request):
    # Read the multipart form tolerantly (Mailgun field presence/naming varies by
    # route config) instead of strict Form(...) params that 422 on any mismatch.
    form = await request.form()

    def g(*names: str) -> Optional[str]:
        for n in names:
            v = form.get(n)
            if v is not None:
                return str(v)
        return None

    timestamp = g("timestamp")
    token = g("token")
    signature = g("signature")
    recipient = g("recipient", "To", "to")
    sender = g("sender", "from", "From")
    subject = g("subject", "Subject") or ""
    body_plain = g("body-plain")
    stripped_text = g("stripped-text")
    stripped_html = g("stripped-html")
    message_id = g("Message-Id", "message-id")

    # The signature fields authenticate the webhook. If the request has no parseable
    # form body / is missing them, it isn't a real inbound email — reject with a
    # clear 406 (not a confusing 422) and log the content-type + keys so a route /
    # content-type misconfiguration is diagnosable.
    if not (timestamp and token and signature):
        # Unauthenticated probe / scanner hitting the public webhook (no Mailgun
        # signature). Rejected with 406; logged at DEBUG so it doesn't flood the log as
        # an ERROR. (Enable DEBUG logging if you're actually diagnosing a Mailgun route.)
        logger.debug(
            "Mailgun inbound rejected: missing signature fields. "
            "content_type=%s form_keys=%s — check the Mailgun Route URL/signing config.",
            request.headers.get("content-type"), sorted(form.keys()),
        )
        raise HTTPException(status_code=406, detail="Missing Mailgun signature fields")
    if not recipient or not sender:
        logger.error(
            "Mailgun inbound rejected: missing recipient/sender. form_keys=%s",
            sorted(form.keys()),
        )
        raise HTTPException(status_code=406, detail="Missing recipient/sender")

    verify_mailgun_signature(timestamp, token, signature)

    # Sanitize every field BEFORE handing off to Celery. Plain-text fields get
    # html-escaped; the HTML body has script/style/iframe blocks, on*= attrs,
    # and javascript: URLs stripped. The frontend MUST still render
    # stripped_html through DOMPurify — this is defense in depth, not the
    # authoritative pass.
    payload = {
        "event_type": "inbound",
        "message_id": escape_plaintext(message_id),
        "recipient": escape_plaintext(recipient),
        "sender": escape_plaintext(sender),
        "subject": escape_plaintext(subject),
        # 🔑 NORMALIZED KEYS
        "body_plain": escape_plaintext(body_plain),
        "stripped_text": escape_plaintext(stripped_text),
        "stripped_html": strip_dangerous_html(stripped_html),
    }

    process_webhook_task.delay(payload)

    return {"status": "ok"}

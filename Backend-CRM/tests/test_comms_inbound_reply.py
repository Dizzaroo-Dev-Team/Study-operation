"""Inbound email reply acceptance (regression guard).

Inbound replies broke when the sender allowlist was enforced even for an EMPTY
allowlist — but conversation recipients arrive via @mentions in message bodies,
not a stored participant list, so the allowlist was legitimately empty and every
real reply got rejected.

The fix (now permanent):
  * enforce the allowlist only when one EXISTS (empty → accept), and
  * build the allowlist from the conversation/thread's actual correspondents
    (the `mentioned_emails` recorded on its prior messages), so anti-forgery is
    still real where we have data.

These tests exercise the worker's allowlist construction + decision directly.
`asyncio_mode = auto`.
"""
from app.workers.tasks import inbound_sender_allowed, _collect_correspondent_emails


async def _messages(docs):
    return docs


# --------------------------------------------------------------------------- #
# The regression: a legitimate reply with no allowlist on file is ACCEPTED.
# --------------------------------------------------------------------------- #

def test_legitimate_reply_accepted_when_no_allowlist():
    # Conversation has empty participant_emails AND no recorded correspondents.
    # A real inbound reply must be accepted (it was wrongly rejected before).
    assert inbound_sender_allowed(set(), "replier@example.com") is True


# --------------------------------------------------------------------------- #
# The allowlist is built from actual correspondents (mentioned_emails).
# --------------------------------------------------------------------------- #

async def test_correspondents_collected_from_prior_message_mentions():
    docs = [
        {"mentioned_emails": ["Bob@X.com"]},
        {"mentioned_emails": ["carol@x.com", "bob@x.com"]},  # dup bob, new carol
        {"body": "no mentions here"},
        "not-a-dict",  # tolerated
    ]
    out = await _collect_correspondent_emails(_messages(docs))
    assert out == {"bob@x.com", "carol@x.com"}  # normalized + deduped


async def test_enriched_allowlist_accepts_correspondent_rejects_forger():
    # Conversation with empty participant_emails but a prior outbound message
    # that @mentioned bob — bob's reply is accepted, a forger is rejected.
    correspondents = await _collect_correspondent_emails(
        _messages([{"mentioned_emails": ["bob@x.com"]}])
    )
    allowlist = set() | correspondents  # participant_emails (empty) + correspondents
    assert inbound_sender_allowed(allowlist, "BOB@x.com") is True   # case-insensitive
    assert inbound_sender_allowed(allowlist, "forger@x.com") is False


async def test_collect_is_fail_open_on_error():
    # If loading messages fails, the collector returns an empty set (which then
    # means "no allowlist" → accept) — it never blocks a legitimate reply.
    async def _boom():
        raise RuntimeError("mongo down")
    assert await _collect_correspondent_emails(_boom()) == set()

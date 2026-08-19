"""Privacy gate + symmetric access recompute + inbound webhook sender allowlist.

These behaviors are now permanent (the COMMS_* flags were removed):
  * the access checker honors is_confidential/is_restricted
  * update_conversation_access recomputes access_level symmetrically
  * inbound_sender_allowed enforces the allowlist only when one exists

`asyncio_mode = auto`.
"""
import app.crud as crud
import app.integrations.iam.membership as membership_mod
from app.workers.tasks import inbound_sender_allowed

STUDY_A = "11111111-1111-1111-1111-111111111111"
SITE_A = "22222222-2222-2222-2222-222222222222"
CREATOR = "user-creator"
OUTSIDER = "user-outsider"


# --------------------------------------------------------------------------- #
# Privacy gate in the access checker
# --------------------------------------------------------------------------- #

def _conf_public_conv():
    # access_level left PUBLIC but explicitly confidential — the checker must
    # honor is_confidential and treat it as non-public.
    return {
        "id": "33333333-3333-3333-3333-333333333333",
        "conversation_type": "thread",
        "is_pinned": "false",
        "access_level": "PUBLIC",
        "is_confidential": "true",
        "created_by": CREATOR,
        "study_id": STUDY_A,
        "site_id": SITE_A,
        "participant_emails": [],
        "privileged_users": [],
    }


async def _access(user_id, conv):
    return await crud.check_user_can_access_conversation_by_role(
        None, user_id, conv, user_email=None, access_set=set()
    )


async def test_confidential_denied_to_outsider_allowed_to_creator():
    conv = _conf_public_conv()
    # is_confidential honored even though access_level is PUBLIC → not public →
    # membership branch skipped → falls through to participation rules.
    assert await _access(OUTSIDER, conv) is False
    assert await _access(CREATOR, conv) is True


async def test_plain_public_visible_to_a_study_member(monkeypatch):
    # A genuinely public conv (privacy did not flag it). Visibility now also
    # requires study membership, so simulate the caller being a member.
    async def _is_member(user_id, study_id):
        return True
    monkeypatch.setattr(membership_mod, "user_can_access_study", _is_member)
    conv = _conf_public_conv()
    conv["is_confidential"] = "false"
    assert await _access(OUTSIDER, conv) is True


# --------------------------------------------------------------------------- #
# update_conversation_access — symmetric recompute
# --------------------------------------------------------------------------- #

import pytest


@pytest.fixture
def capture_update(monkeypatch):
    """Patch get_conversation + ConversationRepository.update; capture the writes."""
    captured = {}

    def _install(existing):
        async def _get(db, cid):
            return existing
        async def _update(cid, updates):
            captured["updates"] = updates
            return {**existing, **updates}
        monkeypatch.setattr(crud, "get_conversation", _get)
        monkeypatch.setattr(crud.ConversationRepository, "update", staticmethod(_update))
    return _install, captured


async def test_update_returns_to_public(capture_update):
    install, captured = capture_update
    install({"is_confidential": "true", "is_restricted": "false", "access_level": "CONFIDENTIAL"})
    # Clearing confidential (restricted already false) → back to PUBLIC.
    await crud.update_conversation_access(None, "cid", is_confidential=False)
    assert captured["updates"]["access_level"] == "PUBLIC"


async def test_update_sets_confidential(capture_update):
    install, captured = capture_update
    install({"is_confidential": "false", "is_restricted": "false", "access_level": "PUBLIC"})
    await crud.update_conversation_access(None, "cid", is_confidential=True)
    assert captured["updates"]["access_level"] == "CONFIDENTIAL"


async def test_update_keeps_restricted_when_only_confidential_cleared(capture_update):
    install, captured = capture_update
    # restricted already true on the doc; clear confidential only → RESTRICTED stays.
    install({"is_confidential": "true", "is_restricted": "true", "access_level": "CONFIDENTIAL"})
    await crud.update_conversation_access(None, "cid", is_confidential=False)
    assert captured["updates"]["access_level"] == "RESTRICTED"


# --------------------------------------------------------------------------- #
# inbound_sender_allowed — enforce only when an allowlist exists
# --------------------------------------------------------------------------- #

def test_inbound_empty_allowlist_accepts():
    # No allowlist on file → no basis to reject a legitimate reply → accept.
    assert inbound_sender_allowed(set(), "anyone@x.com") is True
    assert inbound_sender_allowed(set(), None) is True


def test_inbound_nonempty_sender_in_list_allowed():
    assert inbound_sender_allowed({"a@x.com"}, "A@X.com") is True  # case-insensitive


def test_inbound_nonempty_sender_not_in_list_rejected():
    assert inbound_sender_allowed({"a@x.com"}, "b@x.com") is False
    assert inbound_sender_allowed({"a@x.com"}, None) is False

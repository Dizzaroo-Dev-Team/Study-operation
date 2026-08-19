"""Membership gate + LEAK-1 fix.

Covers the conversation/thread access checkers and the shared
`user_can_access_study` helper. Study-membership enforcement is now permanent.
`asyncio_mode = auto` (pytest.ini) runs the async tests without an explicit marker.

The checkers are exercised directly with hand-built dicts. We pass
`access_set=set()` (and `db=None`) so the explicit-grant rule resolves from the
in-memory set and never touches Postgres.
"""
import pytest

import app.crud as crud
import app.integrations.iam.membership as membership


STUDY_A = "11111111-1111-1111-1111-111111111111"  # local_resources._id
SITE_A = "22222222-2222-2222-2222-222222222222"
CREATOR = "user-creator"
MEMBER = "user-member"
OUTSIDER = "user-outsider"


def _public_conv(**over):
    base = {
        "id": "33333333-3333-3333-3333-333333333333",
        "conversation_type": "thread",
        "is_pinned": "false",
        "access_level": "PUBLIC",
        "created_by": CREATOR,
        "study_id": STUDY_A,
        "site_id": SITE_A,
        "participant_emails": [],
        "privileged_users": [],
    }
    base.update(over)
    return base


@pytest.fixture
def membership_stub(monkeypatch):
    """Patch user_can_access_study to allow only a given set of (user, study)."""
    def _install(allowed: set):
        async def _fake(user_id, study_resource_id):
            return (str(user_id), str(study_resource_id)) in allowed
        monkeypatch.setattr(membership, "user_can_access_study", _fake)
    return _install


async def _conv_access(user_id, conv, user_email=None):
    return await crud.check_user_can_access_conversation_by_role(
        None, user_id, conv, user_email=user_email, access_set=set()
    )


# --------------------------------------------------------------------------- #
# Conversation checker — the leak is closed (study membership required)
# --------------------------------------------------------------------------- #

async def test_study_member_allowed(membership_stub):
    membership_stub({(MEMBER, STUDY_A)})
    assert await _conv_access(MEMBER, _public_conv()) is True


async def test_non_member_denied(membership_stub):
    membership_stub(set())  # nobody is a member
    # OUTSIDER is not creator, not participant, not granted, not a member.
    assert await _conv_access(OUTSIDER, _public_conv()) is False


async def test_non_member_creator_still_allowed(membership_stub):
    membership_stub(set())  # creator is NOT a study member
    # Falls through the (failed) membership shortcut to the creator rule.
    assert await _conv_access(CREATOR, _public_conv()) is True


async def test_non_member_participant_still_allowed(membership_stub):
    membership_stub(set())
    conv = _public_conv(created_by="someone-else",
                        participant_emails=["p@x.com"])
    assert await _conv_access("p-user", conv, user_email="p@x.com") is True


async def test_null_study_only_participants(membership_stub):
    membership_stub({(MEMBER, STUDY_A)})  # membership is irrelevant w/o study id
    conv = _public_conv(study_id=None, created_by="someone-else")
    # No study id → no membership shortcut → outsider denied …
    assert await _conv_access(OUTSIDER, conv) is False
    # … but the creator still gets in.
    assert await _conv_access(CREATOR, _public_conv(study_id=None)) is True


async def test_notice_board_still_public(membership_stub):
    membership_stub(set())
    conv = _public_conv(conversation_type="notice_board")
    # Rule 1 (notice board) precedes the membership gate — stays public.
    assert await _conv_access(OUTSIDER, conv) is True


# --------------------------------------------------------------------------- #
# Thread checker
# --------------------------------------------------------------------------- #

async def _thread_access(user_id, thread, user_email=None):
    return await crud.check_user_can_access_thread(
        None, user_id, thread, user_email=user_email
    )


def _site_thread(**over):
    base = {
        "id": "44444444-4444-4444-4444-444444444444",
        "created_by": CREATOR,
        "visibility_scope": "site",
        "related_study_id": STUDY_A,
        "participants": [],
    }
    base.update(over)
    return base


async def test_thread_site_member_allowed(membership_stub):
    membership_stub({(MEMBER, STUDY_A)})
    assert await _thread_access(MEMBER, _site_thread()) is True


async def test_thread_private_not_broadened(membership_stub):
    membership_stub({(MEMBER, STUDY_A)})  # member, but thread is PRIVATE
    private = _site_thread(visibility_scope="private", created_by="someone-else")
    assert await _thread_access(MEMBER, private) is False


async def test_thread_creator_always_allowed(membership_stub):
    membership_stub(set())
    assert await _thread_access(CREATOR, _site_thread()) is True


# --------------------------------------------------------------------------- #
# Helper: user_can_access_study
# --------------------------------------------------------------------------- #

class _FakeColl:
    def __init__(self, doc):
        self._doc = doc

    async def find_one(self, query):
        uid = query.get("userId")
        if self._doc and self._doc.get("userId") == uid:
            return self._doc
        return None


class _FakeMongo:
    def __init__(self, doc):
        self._coll = _FakeColl(doc)

    def __getitem__(self, _name):
        return self._coll


async def test_helper_allows_matching_grant(monkeypatch):
    doc = {
        "userId": MEMBER,
        "attributeName": "resource_access",
        "value": [{"role": "cra", "resource_id": STUDY_A}],
    }

    async def _fake_get_mongo_db():
        return _FakeMongo(doc)

    monkeypatch.setattr("app.db.mongo.get_mongo_db", _fake_get_mongo_db)
    assert await membership.user_can_access_study(MEMBER, STUDY_A) is True


async def test_helper_denies_without_grant(monkeypatch):
    doc = {
        "userId": MEMBER,
        "attributeName": "resource_access",
        "value": [{"role": "cra", "resource_id": "some-other-study"}],
    }

    async def _fake_get_mongo_db():
        return _FakeMongo(doc)

    monkeypatch.setattr("app.db.mongo.get_mongo_db", _fake_get_mongo_db)
    assert await membership.user_can_access_study(MEMBER, STUDY_A) is False
    # Empty inputs fail closed.
    assert await membership.user_can_access_study("", STUDY_A) is False
    assert await membership.user_can_access_study(MEMBER, "") is False


def test_parse_resource_access_value_dedups_and_normalizes():
    value = [
        {"role": "cra", "resource_id": STUDY_A},
        {"role": "x", "resourceId": STUDY_A},   # dup by resource_id → dropped
        {"role": None, "id": "study-b"},        # alt key `id`
        "garbage",                               # non-dict → skipped
        {"role": "y"},                           # no id → skipped
    ]
    out = membership.parse_resource_access_value(value)
    assert out == [
        {"resource_id": STUDY_A, "role": "cra"},
        {"resource_id": "study-b", "role": None},
    ]
    assert membership.parse_resource_access_value(None) == []

"""Shared write-guard dependencies.

Exercises the three guards directly (they return None on allow, raise
HTTPException on deny). `crud` lookups are monkeypatched so no DB is needed.
`asyncio_mode = auto` runs the async tests without a marker.
"""
import pytest
from fastapi import HTTPException

from app import crud
import app.modules.communications.guards as guards

CREATOR = "user-creator"
OTHER = "user-other"


@pytest.fixture
def patch_crud(monkeypatch):
    """Install fake conversation/thread loaders + access checkers."""
    def _install(*, conv=None, thread=None, conv_ok=True, thread_ok=True):
        async def _get_conv(db, cid):
            return conv
        async def _get_thread(db, tid):
            return thread
        async def _conv_check(db, user_id, c, **kw):
            return conv_ok
        async def _thread_check(db, user_id, t, **kw):
            return thread_ok
        monkeypatch.setattr(crud, "get_conversation", _get_conv)
        monkeypatch.setattr(crud, "get_thread", _get_thread)
        monkeypatch.setattr(crud, "check_user_can_access_conversation_by_role", _conv_check)
        monkeypatch.setattr(crud, "check_user_can_access_thread", _thread_check)
    return _install


def _status(excinfo):
    return excinfo.value.status_code


# --------------------------------------------------------------------------- #
# Conversation member guard
# --------------------------------------------------------------------------- #

async def test_member_anonymous_denied(patch_crud):
    patch_crud(conv={"created_by": CREATOR}, conv_ok=True)
    with pytest.raises(HTTPException) as e:
        await guards.require_conversation_member(None, current_user=None, db=None)
    assert _status(e) == 403


async def test_member_nonmember_denied(patch_crud):
    patch_crud(conv={"created_by": CREATOR}, conv_ok=False)
    with pytest.raises(HTTPException) as e:
        await guards.require_conversation_member(None, current_user={"user_id": OTHER}, db=None)
    assert _status(e) == 403


async def test_member_member_allowed(patch_crud):
    patch_crud(conv={"created_by": CREATOR}, conv_ok=True)
    assert await guards.require_conversation_member(None, current_user={"user_id": OTHER}, db=None) is None


async def test_member_missing_conv_404(patch_crud):
    patch_crud(conv=None)
    with pytest.raises(HTTPException) as e:
        await guards.require_conversation_member(None, current_user={"user_id": OTHER}, db=None)
    assert _status(e) == 404


# --------------------------------------------------------------------------- #
# Conversation admin guard (creator OR privileged)
# --------------------------------------------------------------------------- #

async def test_admin_creator_allowed(patch_crud):
    patch_crud(conv={"created_by": CREATOR})
    assert await guards.require_conversation_admin(None, current_user={"user_id": CREATOR}, db=None) is None


async def test_admin_privileged_allowed(patch_crud):
    patch_crud(conv={"created_by": CREATOR})
    cu = {"user_id": OTHER, "is_privileged": True}
    assert await guards.require_conversation_admin(None, current_user=cu, db=None) is None


async def test_admin_other_denied(patch_crud):
    patch_crud(conv={"created_by": CREATOR})
    cu = {"user_id": OTHER, "is_privileged": False}
    with pytest.raises(HTTPException) as e:
        await guards.require_conversation_admin(None, current_user=cu, db=None)
    assert _status(e) == 403


async def test_admin_anonymous_denied(patch_crud):
    patch_crud(conv={"created_by": CREATOR})
    with pytest.raises(HTTPException) as e:
        await guards.require_conversation_admin(None, current_user=None, db=None)
    assert _status(e) == 403


# --------------------------------------------------------------------------- #
# Thread member guard
# --------------------------------------------------------------------------- #

async def test_thread_anonymous_denied(patch_crud):
    patch_crud(thread={"created_by": CREATOR}, thread_ok=True)
    with pytest.raises(HTTPException) as e:
        await guards.require_thread_member(None, current_user=None, db=None)
    assert _status(e) == 403


async def test_thread_nonmember_denied(patch_crud):
    patch_crud(thread={"created_by": CREATOR}, thread_ok=False)
    with pytest.raises(HTTPException) as e:
        await guards.require_thread_member(None, current_user={"user_id": OTHER}, db=None)
    assert _status(e) == 403


async def test_thread_member_allowed(patch_crud):
    patch_crud(thread={"created_by": CREATOR}, thread_ok=True)
    assert await guards.require_thread_member(None, current_user={"user_id": OTHER}, db=None) is None


async def test_thread_missing_404(patch_crud):
    patch_crud(thread=None)
    with pytest.raises(HTTPException) as e:
        await guards.require_thread_member(None, current_user={"user_id": OTHER}, db=None)
    assert _status(e) == 404

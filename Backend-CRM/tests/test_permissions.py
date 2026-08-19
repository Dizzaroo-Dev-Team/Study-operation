"""Smoke tests for the permissions foundation (app/permissions.py)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.errors import AuthorizationError
from app.models import UserRole
from app.permissions import (
    AuthContext,
    authenticated,
    has_any_role,
    has_role,
    is_privileged,
    require,
)


def _ctx(*, role: UserRole = UserRole.PARTICIPANT, is_priv: str = "false") -> AuthContext:
    """Build an AuthContext with a stub user. db is unused for these checks."""
    user = SimpleNamespace(role=role, is_privileged=is_priv)
    return AuthContext(user=user, db=None)  # type: ignore[arg-type]


def test_authenticated_passes_when_user_present():
    assert authenticated(_ctx()) is True


def test_authenticated_fails_when_user_missing():
    ctx = AuthContext(user=None, db=None)  # type: ignore[arg-type]
    assert authenticated(ctx) is False


def test_has_role_matches_exact_role():
    perm = has_role(UserRole.CRA)
    assert perm(_ctx(role=UserRole.CRA)) is True
    assert perm(_ctx(role=UserRole.PARTICIPANT)) is False


def test_has_role_name_is_descriptive():
    perm = has_role(UserRole.STUDY_MANAGER)
    assert perm._permission_name == "has_role:study_manager"  # type: ignore[attr-defined]


def test_has_any_role_matches_one_of_set():
    perm = has_any_role(UserRole.CRA, UserRole.STUDY_MANAGER)
    assert perm(_ctx(role=UserRole.CRA)) is True
    assert perm(_ctx(role=UserRole.STUDY_MANAGER)) is True
    assert perm(_ctx(role=UserRole.PARTICIPANT)) is False


def test_is_privileged_truthy_for_flag_string():
    assert is_privileged(_ctx(is_priv="true")) is True
    assert is_privileged(_ctx(is_priv="false")) is False


@pytest.mark.asyncio
async def test_require_allows_when_all_permissions_pass():
    dep = require(authenticated, has_any_role(UserRole.CRA, UserRole.STUDY_MANAGER))
    user = SimpleNamespace(role=UserRole.CRA, is_privileged="false")
    ctx = await dep(current_user=user, db=None)  # type: ignore[arg-type]
    assert ctx.user is user


@pytest.mark.asyncio
async def test_require_raises_authorization_error_with_named_permission():
    dep = require(has_role(UserRole.STUDY_MANAGER))
    user = SimpleNamespace(role=UserRole.PARTICIPANT, is_privileged="false")
    with pytest.raises(AuthorizationError) as exc_info:
        await dep(current_user=user, db=None)  # type: ignore[arg-type]
    # The denial message names which permission failed so the client can react.
    assert "has_role:study_manager" in str(exc_info.value)
    assert exc_info.value.details["permission"] == "has_role:study_manager"
    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "forbidden"

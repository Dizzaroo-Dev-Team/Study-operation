"""
Composable authorization helpers and the `require()` FastAPI dependency.

Design
------
- Authentication is owned by `app.auth.get_current_user` and is upstream of
  this module. By the time a permission function runs, the user is known.
- A `Permission` is a callable `(ctx: AuthContext) -> bool`. It is sync or
  async. It returns True if the caller is allowed, False otherwise.
- `require(*permissions)` returns a FastAPI dependency that resolves
  `AuthContext` and evaluates every permission. The FIRST failure raises
  `AuthorizationError` naming the offending permission, so the response body
  carries enough context for the client to render a useful message.
- This module deliberately ships ONLY infrastructure plus a handful of
  generic permissions (authenticated, has_role, ...). Domain-specific
  permissions (e.g. agreement-related) live with their feature module and
  are composed via `require(...)` at the route layer.

Usage
-----
    from app.permissions import require, has_any_role
    from app.models import UserRole

    @router.post(
        "/agreements",
        dependencies=[
            Depends(require(has_any_role(UserRole.CRA, UserRole.STUDY_MANAGER)))
        ],
    )
    async def create_agreement(...): ...

Migration plan
--------------
- New routes added during Phase 2 conversions adopt `require(...)` directly.
- Existing routes keep their inline checks until their Phase 2 conversion
  rewrites them. Do not migrate routes that aren't otherwise being touched.
"""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, Union

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.db import get_db
from app.errors import AuthorizationError
from app.models import User, UserRole


@dataclass
class AuthContext:
    """Resolved authorization context handed to permission functions.

    Holds the authenticated user and the DB session so permissions can
    do role/membership lookups without re-resolving them per check.
    """
    user: User
    db: AsyncSession


# A Permission is a callable AuthContext -> bool, sync or async.
Permission = Callable[[AuthContext], Union[bool, Awaitable[bool]]]


def _named(fn: Permission, name: Optional[str] = None) -> Permission:
    """Attach a human-readable name to a permission for error reporting."""
    setattr(fn, "_permission_name", name or fn.__name__)
    return fn


def _permission_name(fn: Permission) -> str:
    return getattr(fn, "_permission_name", getattr(fn, "__name__", "permission"))


def require(*permissions: Permission):
    """Return a FastAPI dependency that enforces every supplied permission.

    The dependency resolves `AuthContext` (user + db), evaluates permissions
    in declaration order, and raises `AuthorizationError` on the first one
    that fails. On success it returns the `AuthContext` so the route can
    reuse it as a function argument.
    """

    async def dep(
        current_user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> AuthContext:
        ctx = AuthContext(user=current_user, db=db)
        for perm in permissions:
            result = perm(ctx)
            if inspect.isawaitable(result):
                result = await result
            if not result:
                raise AuthorizationError(
                    f"permission denied: {_permission_name(perm)}",
                    details={"permission": _permission_name(perm)},
                )
        return ctx

    return dep


# ---------------------------------------------------------------------------
# Generic permissions
#
# Domain-specific permissions (e.g. "can_edit_agreement(agreement_id)") belong
# with their feature module, not here. The helpers below are intentionally
# small and broad-purpose.
# ---------------------------------------------------------------------------

def authenticated(ctx: AuthContext) -> bool:
    """Allow any authenticated user. Useful as a baseline guard."""
    return ctx.user is not None


def has_role(role: UserRole) -> Permission:
    """Allow only callers whose User.role exactly matches `role`."""

    def _check(ctx: AuthContext) -> bool:
        return ctx.user is not None and ctx.user.role == role

    return _named(_check, f"has_role:{role.value}")


def has_any_role(*roles: UserRole) -> Permission:
    """Allow callers whose User.role is in `roles`."""

    role_set = set(roles)

    def _check(ctx: AuthContext) -> bool:
        return ctx.user is not None and ctx.user.role in role_set

    return _named(_check, f"has_any_role:{','.join(r.value for r in roles)}")


def is_privileged(ctx: AuthContext) -> bool:
    """Allow callers flagged as privileged (can manage confidential conversations).

    Matches the existing string-typed `User.is_privileged` column.
    """
    flag = getattr(ctx.user, "is_privileged", "false")
    return flag in ("true", True)

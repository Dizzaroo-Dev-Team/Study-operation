"""
Audit logging helpers.

Two ways to record an audit entry:

1. Explicit call inside a service function (preferred when context is rich):

       async with transactional(db):
           agreement = await _do_status_change(db, agreement_id, new_status)
           await record_audit(
               db,
               action="agreement.status_change",
               target_type="agreement",
               target_id=str(agreement.id),
               user=actor.user_id,
               details={"to": new_status.value},
           )

2. `@audit(...)` decorator for the common case where the audit shape can be
   derived mechanically from the function's args / return value:

       @audit("agreement.create", target_type="agreement")
       async def create_agreement(db, payload, *, actor):
           agreement = Agreement(...)
           db.add(agreement)
           await db.flush()
           return agreement   # target_id comes from agreement.id

Both helpers add the AuditLog row to the SQLAlchemy session WITHOUT
committing. The route handler's `transactional()` block owns the commit, so
the audit entry and the mutation land in the same transaction by
construction.

This is the replacement for the legacy `app.crud.create_audit_log` function,
which committed mid-operation - we keep that one for backward compat but new
code should use these helpers.
"""
from __future__ import annotations

import functools
import inspect
from typing import Any, Awaitable, Callable, Optional, TypeVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog

T = TypeVar("T")


async def record_audit(
    db: AsyncSession,
    *,
    action: str,
    target_type: str,
    target_id: str,
    user: Optional[str] = None,
    details: Optional[dict] = None,
) -> AuditLog:
    """Add an AuditLog row to the session. Does NOT commit.

    Caller owns the transaction (use `transactional()` from `app.db`).
    """
    from app.audit_context import apply_provenance

    log = AuditLog(
        user=user,
        action=action,
        target_type=target_type,
        target_id=target_id,
        details=apply_provenance(details) or {},
    )
    db.add(log)
    return log


def _extract_db(args: tuple, kwargs: dict) -> Optional[AsyncSession]:
    """Pull the AsyncSession out of args/kwargs. By convention `db` is first
    positional arg, but routes/services occasionally pass it as a kwarg."""
    db = kwargs.get("db")
    if isinstance(db, AsyncSession):
        return db
    for value in args:
        if isinstance(value, AsyncSession):
            return value
    return None


def _extract_actor(args: tuple, kwargs: dict) -> Optional[str]:
    """Pick the audit `user` field from common kwarg names."""
    for name in ("actor_user_id", "actor", "user_id", "user"):
        value = kwargs.get(name)
        if value is None:
            continue
        # Prefer a string user_id when actor is a User-like object.
        user_id = getattr(value, "user_id", None)
        if user_id is not None:
            return str(user_id)
        if isinstance(value, str):
            return value
    return None


def _extract_target_id(
    args: tuple,
    kwargs: dict,
    result: Any,
    target_id_kwarg: Optional[str],
) -> str:
    """Determine the audit `target_id`. Precedence:
    1. Explicit kwarg name (if `target_id_kwarg` set).
    2. `result.id` attribute (typical for create_*).
    3. String representation of the result (fallback).
    """
    if target_id_kwarg:
        if target_id_kwarg in kwargs:
            return str(kwargs[target_id_kwarg])
        # Try positional - look up signature
        # (caller can always pass as kwarg; we don't reflect deeply here.)
    target_id = getattr(result, "id", None)
    if target_id is not None:
        return str(target_id)
    return str(result) if result is not None else "unknown"


def audit(
    action: str,
    *,
    target_type: str,
    target_id_kwarg: Optional[str] = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator that records an `AuditLog` after a successful service call.

    Args:
        action: dot-namespaced action string (e.g. "agreement.status_change").
        target_type: short type name for the audited entity ("agreement").
        target_id_kwarg: name of the kwarg holding the target id. If unset,
            the decorator inspects `result.id` instead.

    Conventions enforced by this decorator:
      - The wrapped function must be async.
      - It must take `db: AsyncSession` either as first positional arg or as
        the `db` kwarg.
      - On exception the audit is NOT written (the caller's transactional
        block rolls back; partial audits would be lies).
    """

    def deco(fn: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        if not inspect.iscoroutinefunction(fn):
            raise TypeError(
                f"@audit can only wrap async functions; {fn.__name__} is sync"
            )

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            db = _extract_db(args, kwargs)
            if db is None:
                # Fail loudly BEFORE running the wrapped function: a mutation
                # without its audit row is a compliance violation (GxP / 21 CFR
                # Part 11). The decorator contract requires `db` as the first
                # positional arg or the `db` kwarg; if it's missing the caller
                # is misusing @audit and we refuse to proceed.
                raise RuntimeError(
                    f"@audit({action}) on {fn.__name__}: AsyncSession not found "
                    "in args/kwargs. Pass `db` as first positional arg or `db=` "
                    "kwarg; refusing to run the wrapped function to prevent an "
                    "un-audited mutation."
                )
            result = await fn(*args, **kwargs)
            actor = _extract_actor(args, kwargs)
            target_id = _extract_target_id(args, kwargs, result, target_id_kwarg)
            await record_audit(
                db,
                action=action,
                target_type=target_type,
                target_id=target_id,
                user=actor,
            )
            return result

        return wrapper

    return deco

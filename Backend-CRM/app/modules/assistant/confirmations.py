"""Pending-action store for the write/regulated confirmation gate.

A write command doesn't execute until the user approves it. The agent loop
creates a pending action, emits a ``confirmation`` block over SSE, and awaits
the decision. ``/assistant/approve`` and ``/assistant/cancel`` resolve it.
``owner_key`` (``"{user_id}:{session_id}"``) is checked on resolve so a user
can never approve/cancel another user's pending action, even with the token.
Tokens are strictly single-use (replay-resolve returns False).

Two interchangeable engines behind one API (selection mirrors session.py —
Redis whenever a URL is configured):

  * ``RedisConfirmationStore`` — the pending record lives in Redis
    (``orbit:pend:{token}``, TTL slightly above the approval window) and the
    decision is delivered via BLPOP on ``orbit:dec:{token}``, so the approving
    request may land on a DIFFERENT worker/replica than the turn awaiting it.
    Single-use is enforced by ``DEL`` returning 1 exactly once.
  * ``LocalConfirmationStore`` — in-process asyncio Futures (bare local dev).

Unified API:
    create(owner_key=…, command_name=…, args=…, risk=…, description=…) -> PendingAction
    await wait(pending, timeout) -> True (approved) | False (cancelled) | None (timeout)
    await resolve(token, owner_key=…, approved=…) -> bool
    await discard(token)
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from app.modules.assistant.session import _resolve_redis_url

logger = logging.getLogger(__name__)

_PEND_PREFIX = "orbit:pend:"
_DEC_PREFIX = "orbit:dec:"


@dataclass
class PendingAction:
    token: str
    owner_key: str
    command_name: str
    args: Dict[str, Any]
    risk: str
    description: str
    future: Optional["asyncio.Future[bool]"] = field(default=None, repr=False)


class LocalConfirmationStore:
    def __init__(self) -> None:
        self._pending: Dict[str, PendingAction] = {}

    def create(self, *, owner_key: str, command_name: str, args: Dict[str, Any],
               risk: str, description: str) -> PendingAction:
        pending = PendingAction(
            token=uuid.uuid4().hex, owner_key=owner_key, command_name=command_name,
            args=args, risk=risk, description=description,
            future=asyncio.get_event_loop().create_future(),
        )
        self._pending[pending.token] = pending
        return pending

    async def wait(self, pending: PendingAction, timeout: float) -> Optional[bool]:
        try:
            assert pending.future is not None
            return await asyncio.wait_for(pending.future, timeout=timeout)
        except asyncio.TimeoutError:
            self._pending.pop(pending.token, None)
            return None

    async def resolve(self, token: str, *, owner_key: str, approved: bool) -> bool:
        pending = self._pending.get(token)
        if pending is None or pending.owner_key != owner_key:
            return False
        if pending.future is not None and not pending.future.done():
            pending.future.set_result(approved)
        self._pending.pop(token, None)
        return True

    async def discard(self, token: str) -> None:
        self._pending.pop(token, None)


class RedisConfirmationStore:
    """Cross-process gate. The awaiting turn BLPOPs the per-token decision list;
    the approving request (any worker) validates ownership against the pending
    record, deletes it (single-use), and pushes the decision."""

    def __init__(self, url: str, ttl_seconds: int = 330) -> None:
        self._url = url
        self._ttl = ttl_seconds  # slightly above the 300s approval window
        self._client = None

    def _redis(self):
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._url, decode_responses=True)
        return self._client

    def create(self, *, owner_key: str, command_name: str, args: Dict[str, Any],
               risk: str, description: str) -> PendingAction:
        pending = PendingAction(
            token=uuid.uuid4().hex, owner_key=owner_key, command_name=command_name,
            args=args, risk=risk, description=description,
        )

        async def _persist() -> None:
            try:
                await self._redis().set(
                    _PEND_PREFIX + pending.token,
                    json.dumps({"owner_key": owner_key, "command": command_name}),
                    ex=self._ttl,
                )
            except Exception:  # noqa: BLE001
                logger.exception("assistant confirmations: redis persist failed")

        # Fire-and-forget; wait() below tolerates a not-yet-persisted record
        # only in the pathological case, and approval requires the record.
        asyncio.get_event_loop().create_task(_persist())
        return pending

    async def wait(self, pending: PendingAction, timeout: float) -> Optional[bool]:
        try:
            res = await self._redis().blpop(
                _DEC_PREFIX + pending.token, timeout=max(1, int(timeout))
            )
        except Exception:  # noqa: BLE001
            logger.exception("assistant confirmations: redis wait failed")
            return None
        if not res:
            await self.discard(pending.token)  # timeout — invalidate the card
            return None
        return res[1] == "1"

    async def resolve(self, token: str, *, owner_key: str, approved: bool) -> bool:
        try:
            r = self._redis()
            raw = await r.get(_PEND_PREFIX + token)
            if not raw:
                return False
            if json.loads(raw).get("owner_key") != owner_key:
                return False
            # Single-use: exactly one caller wins the DEL; replays return False.
            if await r.delete(_PEND_PREFIX + token) != 1:
                return False
            pipe = r.pipeline()
            pipe.rpush(_DEC_PREFIX + token, "1" if approved else "0")
            pipe.expire(_DEC_PREFIX + token, 60)
            await pipe.execute()
            return True
        except Exception:  # noqa: BLE001
            logger.exception("assistant confirmations: redis resolve failed")
            return False

    async def discard(self, token: str) -> None:
        try:
            await self._redis().delete(_PEND_PREFIX + token)
        except Exception:  # noqa: BLE001
            pass


def _build_store():
    url = _resolve_redis_url()
    if url:
        return RedisConfirmationStore(url)
    return LocalConfirmationStore()


confirmations = _build_store()

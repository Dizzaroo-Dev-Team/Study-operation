"""Per-session event plumbing for the assistant.

Transport shape: the client holds ONE long-lived SSE connection per chat session
and POSTs messages / approvals on separate requests. Emitters push events for a
session key; the SSE generator consumes them. Both sides derive the key from
their own authenticated token (``"{user_id}:{session_id}"``) so a session can
never be read or written across users.

Two interchangeable engines behind one API:

  * ``RedisSessionHub`` — the default whenever a Redis URL is configured
    (``ASSISTANT_REDIS_URL`` env → ``settings.redis_url`` →
    ``settings.celery_broker_url``). Events live in a Redis LIST per session
    (RPUSH by the emitting process, BLPOP by whichever process holds the SSE
    connection), so **multiple uvicorn workers / container replicas are safe**:
    the message POST and the SSE stream may land on different processes and
    events still arrive. Lists expire after 1h idle; an open stream refreshes
    the TTL every loop.
  * ``LocalSessionHub`` — in-process asyncio queues, used only when no Redis is
    configured (bare local dev). Single-process semantics.

Unified API (both engines):
    emit(key, event)                    # sync, fire-and-forget, ordered
    await get(key, timeout) -> event | None   # None on timeout (keep-alive tick)
    requeue(key, event)                 # put an UNDELIVERED popped event back at the FRONT
    touch(key)                          # mark session live (TTL refresh)
    await drain(key) -> list[event]     # test harnesses: pop everything queued
    drop(key)                           # discard a session's queue
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Sessions with no live consumer for this long are discarded (Redis: key TTL;
# local: sweep). The SSE loop touches its key every iteration, so an OPEN
# stream never expires — only abandoned sessions do.
_IDLE_TTL_SECONDS = 3600

_KEY_PREFIX = "orbit:evq:"

# ---------------------------------------------------------------------------
# Per-turn event TAP (live-eval recorder). The SSE stream consumes hub events
# DESTRUCTIVELY (the browser pops them), so anything that wants the turn's
# events AFTER the answer — live scoring — must record them as they are
# emitted. A tap is a plain list registered per session key; both hub engines
# append to it synchronously inside emit() (emit always runs in the turn's own
# process, before any Redis hop). Taps are started/stopped by the live-eval
# integration around run_turn; when no tap is registered this is a dict miss.
# ---------------------------------------------------------------------------

_TAPS: Dict[str, List[Dict[str, Any]]] = {}


def start_tap(key: str) -> None:
    _TAPS[key] = []


def stop_tap(key: str) -> List[Dict[str, Any]]:
    return _TAPS.pop(key, [])


def _tap(key: str, event: Dict[str, Any]) -> None:
    events = _TAPS.get(key)
    if events is not None:
        events.append(event)


def _resolve_redis_url() -> Optional[str]:
    url = os.environ.get("ASSISTANT_REDIS_URL")
    if url:
        return url
    try:
        from app.config import settings

        return settings.redis_url or settings.celery_broker_url or None
    except Exception:  # noqa: BLE001 — config unavailable (early import) → local
        return None


class LocalSessionHub:
    """In-process queues. Correct only for a single-process deployment."""

    def __init__(self) -> None:
        self._queues: Dict[str, asyncio.Queue] = {}
        self._touched: Dict[str, float] = {}
        # Events popped by get() but never delivered (SSE cancelled mid-yield) —
        # redelivered FIRST on the next get() so a dropped connection can't eat
        # a terminal `done`/`error` event.
        self._redelivery: Dict[str, List[Dict[str, Any]]] = {}

    def _queue(self, key: str) -> asyncio.Queue:
        self._sweep()
        q = self._queues.get(key)
        if q is None:
            q = asyncio.Queue()
            self._queues[key] = q
        self._touched[key] = time.monotonic()
        return q

    def emit(self, key: str, event: Dict[str, Any]) -> None:
        _tap(key, event)
        self._queue(key).put_nowait(event)

    async def get(self, key: str, timeout: float) -> Optional[Dict[str, Any]]:
        pending = self._redelivery.get(key)
        if pending:
            return pending.pop(0)
        # Looked up by key on every call, so a swept-and-recreated queue is
        # always the one being consumed — no orphaning.
        try:
            return await asyncio.wait_for(self._queue(key).get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def requeue(self, key: str, event: Dict[str, Any]) -> None:
        self._redelivery.setdefault(key, []).append(event)

    def touch(self, key: str) -> None:
        self._queue(key)

    async def drain(self, key: str) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = list(self._redelivery.pop(key, []))
        q = self._queue(key)
        while not q.empty():
            out.append(q.get_nowait())
        return out

    def drop(self, key: str) -> None:
        self._queues.pop(key, None)
        self._touched.pop(key, None)
        self._redelivery.pop(key, None)

    def _sweep(self) -> None:
        now = time.monotonic()
        stale = [k for k, t in self._touched.items() if now - t > _IDLE_TTL_SECONDS]
        for k in stale:
            self._queues.pop(k, None)
            self._touched.pop(k, None)
            self._redelivery.pop(k, None)


class RedisSessionHub:
    """Redis-LIST-backed queues: safe across workers and replicas.

    ``emit`` stays synchronous (callers are mid-turn) by enqueueing to a local
    outbound buffer drained by ONE pump task per process — strict FIFO ordering
    onto Redis, and a Redis hiccup can never break a turn (errors are logged,
    the pump keeps going).
    """

    def __init__(self, url: str) -> None:
        self._url = url
        self._client = None
        self._out: "asyncio.Queue[tuple]" = asyncio.Queue()
        self._pump_task: Optional[asyncio.Task] = None

    def _redis(self):
        if self._client is None:
            import redis.asyncio as aioredis

            self._client = aioredis.from_url(self._url, decode_responses=True)
        return self._client

    def _ensure_pump(self) -> None:
        if self._pump_task is None or self._pump_task.done():
            self._pump_task = asyncio.get_event_loop().create_task(self._pump())

    async def _pump(self) -> None:
        while True:
            key, event = await self._out.get()
            try:
                r = self._redis()
                await r.rpush(_KEY_PREFIX + key, json.dumps(event))
                await r.expire(_KEY_PREFIX + key, _IDLE_TTL_SECONDS)
            except Exception:  # noqa: BLE001 — never let transport break a turn
                logger.exception("assistant hub: redis emit failed (event dropped)")

    def emit(self, key: str, event: Dict[str, Any]) -> None:
        _tap(key, event)
        self._out.put_nowait((key, event))
        self._ensure_pump()

    async def get(self, key: str, timeout: float) -> Optional[Dict[str, Any]]:
        try:
            res = await self._redis().blpop(_KEY_PREFIX + key, timeout=max(1, int(timeout)))
        except Exception:  # noqa: BLE001
            logger.exception("assistant hub: redis get failed")
            await asyncio.sleep(1)  # don't hot-loop the SSE generator on outage
            return None
        if not res:
            return None
        try:
            return json.loads(res[1])
        except Exception:  # noqa: BLE001
            return None

    def requeue(self, key: str, event: Dict[str, Any]) -> None:
        """Push an undelivered in-flight event back to the FRONT of the list
        (LPUSH — the mirror of the pump's RPUSH), fire-and-forget."""

        async def _re() -> None:
            try:
                r = self._redis()
                await r.lpush(_KEY_PREFIX + key, json.dumps(event))
                await r.expire(_KEY_PREFIX + key, _IDLE_TTL_SECONDS)
            except Exception:  # noqa: BLE001
                logger.exception("assistant hub: redis requeue failed (event dropped)")

        try:
            asyncio.get_event_loop().create_task(_re())
        except RuntimeError:
            pass

    def touch(self, key: str) -> None:
        # TTL refresh, fire-and-forget through the pump path.
        async def _touch() -> None:
            try:
                await self._redis().expire(_KEY_PREFIX + key, _IDLE_TTL_SECONDS)
            except Exception:  # noqa: BLE001
                pass

        try:
            asyncio.get_event_loop().create_task(_touch())
        except RuntimeError:
            pass

    async def drain(self, key: str) -> List[Dict[str, Any]]:
        try:
            r = self._redis()
            pipe = r.pipeline()
            pipe.lrange(_KEY_PREFIX + key, 0, -1)
            pipe.delete(_KEY_PREFIX + key)
            raw, _ = await pipe.execute()
            return [json.loads(x) for x in raw]
        except Exception:  # noqa: BLE001
            logger.exception("assistant hub: redis drain failed")
            return []

    def drop(self, key: str) -> None:
        async def _drop() -> None:
            try:
                await self._redis().delete(_KEY_PREFIX + key)
            except Exception:  # noqa: BLE001
                pass

        try:
            asyncio.get_event_loop().create_task(_drop())
        except RuntimeError:
            pass


def _build_hub():
    url = _resolve_redis_url()
    if url:
        logger.info("assistant hub: Redis-backed (multi-worker safe)")
        return RedisSessionHub(url)
    logger.warning(
        "assistant hub: process-local (no Redis URL configured) — "
        "NOT safe for multiple workers/replicas"
    )
    return LocalSessionHub()


# Process-wide singleton.
hub = _build_hub()

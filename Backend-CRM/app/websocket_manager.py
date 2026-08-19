"""WebSocket connection manager with Redis pub/sub for multi-worker broadcast.

History
-------
The original manager kept connections in an in-process dict and broadcast
directly to it. That works for a single uvicorn worker but silently drops
events for users connected to *other* workers once the app is scaled
horizontally. Redis pub/sub was bolted on, but with three latent bugs the
May 2026 audit flagged:

  1. The Redis listener `psubscribe("conversation.*")` — so thread updates
     published to `thread.<id>` were sent to Redis and never received by any
     worker. Inter-worker thread broadcast was broken.

  2. `publish_thread_update` had no local-broadcast fallback. When Redis went
     down (or was disabled) thread events disappeared entirely; conversation
     events still worked because `publish_event` had a fallback.

  3. `start_listening()` was invoked from a route handler, not from app
     startup. If no client ever connected, the listener never started. The
     first connecting user also paid the Redis-init cost on their first WS
     handshake.

Fixes in this module
--------------------
  * Listener psubscribes to `conversation.*` AND `thread.*`. Channel prefix
    routes to the correct broadcast helper.
  * Symmetric `publish_thread_update`: Redis if available, local-broadcast
    fallback otherwise.
  * `startup_init()` is meant to be awaited from FastAPI lifespan so the
    first WS connection no longer pays Redis-init latency.
  * `WEBSOCKET_REQUIRE_REDIS=true` env var makes Redis init re-raise rather
    than silently degrade. Use this in prod to surface misconfig loudly.
"""
from typing import Dict, Set, Optional
from fastapi import WebSocket
import json
import os
import logging
from uuid import UUID
import redis.asyncio as aioredis
from app.config import settings
import asyncio

logger = logging.getLogger(__name__)


# When True, a failed Redis init RAISES — no silent fallback to in-memory
# broadcast. Use in prod to fail fast on broker outage / misconfig. Local
# dev / unit tests should keep this False so the app boots without Redis.
WEBSOCKET_REQUIRE_REDIS = os.getenv("WEBSOCKET_REQUIRE_REDIS", "false").lower() == "true"


class WebSocketManager:
    def __init__(self):
        # Conversations and threads share this dict; their UUIDs don't
        # collide. Keeping a single dict simplifies the broadcast helpers
        # below.
        self.active_connections: Dict[UUID, Set[WebSocket]] = {}
        self.redis_client: Optional[aioredis.Redis] = None
        self.pubsub = None
        self._listening = False
        self.redis_disabled = False
        # Strong references to fire-and-forget tasks (heartbeats, listener) so
        # the event loop can't GC them mid-flight; they discard themselves.
        self._background_tasks: Set[asyncio.Task] = set()
        self._listener_task: Optional[asyncio.Task] = None

    # -------------------------------------------------
    # WebSocket connection handling
    # -------------------------------------------------

    async def connect(self, websocket: WebSocket, conversation_id: UUID):
        if conversation_id not in self.active_connections:
            self.active_connections[conversation_id] = set()

        self.active_connections[conversation_id].add(websocket)

        # 🔥 IMPORTANT: Start heartbeat to prevent Azure idle disconnects
        task = asyncio.create_task(self._heartbeat(websocket))
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    async def disconnect(self, websocket: WebSocket, conversation_id: UUID):
        if conversation_id in self.active_connections:
            self.active_connections[conversation_id].discard(websocket)
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]

    async def send_personal_message(self, message: dict, websocket: WebSocket):
        try:
            await websocket.send_json(message)
        except Exception as e:
            logger.warning("Error sending WebSocket message: %s", e)

    async def _broadcast_local(self, key: UUID, message: dict):
        """Deliver `message` to every WebSocket subscribed to `key` on THIS
        worker. Pruning dead sockets is opportunistic — they get reaped on the
        next send failure rather than via a separate health-check loop.
        """
        if key not in self.active_connections:
            return
        disconnected = set()
        for connection in self.active_connections[key]:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)
        for conn in disconnected:
            self.active_connections[key].discard(conn)
        if not self.active_connections.get(key):
            self.active_connections.pop(key, None)

    async def broadcast_to_conversation(self, conversation_id: UUID, message: dict):
        await self._broadcast_local(conversation_id, message)

    async def broadcast_to_thread(self, thread_id: UUID, message: dict):
        await self._broadcast_local(thread_id, message)

    # -------------------------------------------------
    # HEARTBEAT (CRITICAL FOR AZURE)
    # -------------------------------------------------

    async def _heartbeat(self, websocket: WebSocket):
        """
        Keeps WebSocket alive to avoid Azure 1006 idle disconnects.
        """
        try:
            while True:
                await asyncio.sleep(20)  # Azure-safe interval
                await websocket.send_json({"type": "ping"})
        except Exception:
            # Socket closed or client gone
            pass

    # -------------------------------------------------
    # Redis initialization
    # -------------------------------------------------

    async def init_redis(self):
        if self.redis_disabled:
            return

        if self.redis_client is not None:
            return

        try:
            redis_url = settings.redis_url

            if not redis_url:
                raise RuntimeError("redis_url not configured")

            self.redis_client = await asyncio.wait_for(
                aioredis.from_url(
                    redis_url,
                    decode_responses=False,
                    socket_connect_timeout=5,
                ),
                timeout=6.0,
            )

            await asyncio.wait_for(self.redis_client.ping(), timeout=3.0)

            self.pubsub = self.redis_client.pubsub()
            logger.info("Redis connected successfully for WebSocket pub/sub")

        except Exception as e:
            self.redis_client = None
            self.pubsub = None
            if WEBSOCKET_REQUIRE_REDIS:
                # In prod, Redis is load-bearing for horizontal broadcast.
                # Silently disabling it means messages stop reaching half the
                # users. Fail loudly so the deploy / oncall notices.
                raise RuntimeError(
                    "WEBSOCKET_REQUIRE_REDIS=true but Redis connection failed: "
                    f"{e}"
                )
            logger.exception("Redis permanently disabled for this worker: %s", e)
            self.redis_disabled = True

    # -------------------------------------------------
    # Redis listener
    # -------------------------------------------------

    async def startup_init(self):
        """Connect to Redis and start the listener from app startup.

        Lifespan calls this so the first WS connection no longer pays the
        ~6s Redis-init timeout. Safe to call multiple times.
        """
        await self.init_redis()
        await self.start_listening()

    async def start_listening(self):
        if self._listening or self.redis_disabled:
            return

        await self.init_redis()

        if self.redis_client is None or self.pubsub is None:
            logger.warning("Cannot start Redis listener - Redis not available")
            return

        self._listening = True
        self._listener_task = asyncio.create_task(self._redis_listener())

    async def _consume_pmessages(self):
        """Subscribe to both channel families and process pmessages until the
        listen() iterator ends or an error propagates."""
        # Subscribe to BOTH conversation and thread channels. The earlier code
        # only psubscribed to conversation.* — thread updates were published to
        # thread.* and never received.
        await self.pubsub.psubscribe("conversation.*", "thread.*")
        async for message in self.pubsub.listen():
            if message.get("type") != "pmessage":
                continue
            try:
                channel = message["channel"].decode()
                kind, _, id_str = channel.partition(".")
                target_id = UUID(id_str)
                data = json.loads(message["data"].decode())
                if kind == "conversation":
                    await self.broadcast_to_conversation(target_id, data)
                elif kind == "thread":
                    await self.broadcast_to_thread(target_id, data)
                # Unknown prefix: ignore.
            except Exception as e:
                logger.warning("Error processing Redis message: %s", e)

    async def _redis_listener(self):
        if self.pubsub is None:
            return

        # Bounded reconnect with capped backoff instead
        # of permanently disabling cross-worker realtime on the first error.
        backoff = 1.0
        max_backoff = 30.0
        max_attempts = 10
        attempt = 0
        while attempt < max_attempts:
            try:
                if self.pubsub is None:
                    await self.init_redis()
                if self.pubsub is None:
                    raise RuntimeError("Redis pubsub unavailable")
                await self._consume_pmessages()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                attempt += 1
                logger.warning(
                    "Redis listener error (attempt %s/%s): %s; reconnecting in %.1fs",
                    attempt, max_attempts, e, backoff,
                )
                self.redis_client = None
                self.pubsub = None
                self.redis_disabled = False  # allow init_redis to rebuild
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    raise
                backoff = min(backoff * 2, max_backoff)
                continue
            else:
                # Clean end of the listen() stream — reset counters, reconnect.
                logger.warning("Redis listener stream ended cleanly; reconnecting.")
                attempt = 0
                backoff = 1.0
                self.redis_client = None
                self.pubsub = None
                self.redis_disabled = False
                continue

        logger.error(
            "Redis listener giving up after %s reconnect attempts; disabling for this worker.",
            max_attempts,
        )
        self.redis_disabled = True
        self._listening = False

    # -------------------------------------------------
    # Publishing events
    # -------------------------------------------------

    async def publish_event(self, conversation_id: UUID, event_data: dict):
        # Fallback to in-memory broadcast when Redis is unavailable.
        if self.redis_disabled:
            await self.broadcast_to_conversation(conversation_id, event_data)
            return

        if self.redis_client is None:
            await self.init_redis()

        if self.redis_client is None:
            self.redis_disabled = True
            await self.broadcast_to_conversation(conversation_id, event_data)
            return

        try:
            channel = f"conversation.{conversation_id}"
            await self.redis_client.publish(channel, json.dumps(event_data))
        except Exception as e:
            logger.exception("Redis publish failed, disabling Redis: %s", e)
            self.redis_disabled = True
            await self.broadcast_to_conversation(conversation_id, event_data)

    async def publish_thread_update(self, thread_id: UUID, event_data: dict):
        # Symmetric with publish_event: fall back to in-memory local broadcast
        # when Redis is disabled instead of dropping the event. Previously
        # this method silently returned, which lost thread updates entirely
        # on workers where Redis had been disabled.
        if self.redis_disabled:
            await self.broadcast_to_thread(thread_id, event_data)
            return

        if self.redis_client is None:
            await self.init_redis()

        if self.redis_client is None:
            self.redis_disabled = True
            await self.broadcast_to_thread(thread_id, event_data)
            return

        try:
            channel = f"thread.{thread_id}"
            await self.redis_client.publish(channel, json.dumps(event_data))
        except Exception as e:
            logger.exception("Redis thread publish failed, disabling Redis: %s", e)
            self.redis_disabled = True
            await self.broadcast_to_thread(thread_id, event_data)


# Singleton
manager = WebSocketManager()

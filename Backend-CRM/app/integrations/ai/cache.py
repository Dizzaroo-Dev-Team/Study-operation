"""Content-addressed cache for AI responses.

Why
---
Most AI calls in this app are **deterministic on the input**: summarize a
conversation that hasn't changed, classify the same document twice, ask the
same compose-assist question. Each call costs:

  * 1-30 seconds of latency, often dominating the request timeline
  * non-trivial Gemini quota
  * an outbound HTTPS round trip from inside the container

By keying a small Redis cache on `sha256(prompt)`, repeats become ~5 ms
local-Redis lookups. Re-summarizing the same conversation N times costs
exactly one Gemini call instead of N.

What goes in here
-----------------
Only **side-effect-free, content-only** AI calls. NOT included:
  * anything that uses a stateful chat session (chat_with_document)
  * anything that depends on real-time context (user mood, time of day, …)
  * anything where the same prompt SHOULD produce variation (idea brainstorm)

Public API
----------
    from app.integrations.ai.cache import cached_text_generate

    text = await cached_text_generate(
        client,
        prompt,
        cache_namespace="summarize_conversation",
        ttl_seconds=3600,
    )

`cache_namespace` keeps different code paths from sharing a cache slot when
they happen to produce identical prompts (defensive — sha256 collisions are
not a concern, but separating namespaces makes invalidation per-feature
easy).

The cache is best-effort: if Redis is unavailable, the call falls through
to the underlying Gemini API and the function still returns the right
answer. The cost in that case is exactly the pre-cache cost — no degradation.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Optional

import redis.asyncio as aioredis

from app.config import settings
from app.integrations.ai.client import AIClient

logger = logging.getLogger("app.ai_cache")


# Singleton Redis client. We deliberately do NOT reuse the WebSocket
# manager's client because (a) it's been disabled in some failure paths, and
# (b) decode_responses=True simplifies the string-only API used here.
_redis: Optional[aioredis.Redis] = None
_redis_disabled = False


async def _get_redis() -> Optional[aioredis.Redis]:
    """Return a connected Redis client or None if Redis is unavailable.

    First call connects + pings. Subsequent calls reuse the client. Once
    Redis has failed, we don't retry within the process lifetime — let the
    process restart re-attempt.
    """
    global _redis, _redis_disabled
    if _redis_disabled:
        return None
    if _redis is not None:
        return _redis

    redis_url = getattr(settings, "redis_url", None)
    if not redis_url:
        _redis_disabled = True
        return None

    try:
        client = await asyncio.wait_for(
            aioredis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
            ),
            timeout=3.0,
        )
        await asyncio.wait_for(client.ping(), timeout=2.0)
        _redis = client
        logger.info("[ai-cache] Redis connected")
        return _redis
    except Exception as exc:
        logger.warning(f"[ai-cache] Redis unavailable, cache disabled: {exc}")
        _redis_disabled = True
        return None


def _cache_key(namespace: str, prompt: str) -> str:
    # Length-prefixed namespace + sha256 of prompt. Keeps the key human-
    # debuggable (you can grep for `ai:cache:summarize_conversation:*` in
    # Redis) without leaking the prompt content into the key.
    digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return f"ai:cache:{namespace}:{digest}"


async def cached_text_generate(
    client: AIClient,
    prompt: str,
    *,
    cache_namespace: str,
    ttl_seconds: int = 3600,
) -> Optional[str]:
    """Run a Gemini text generation with a Redis read-through cache.

    Cache hits return in ~5 ms. Cache misses behave identically to the raw
    `client.model.generate_content(prompt)` path, then populate the cache
    for next time.
    """
    if not client.is_available() or not client.model:
        return None

    redis = await _get_redis()
    key = _cache_key(cache_namespace, prompt) if redis is not None else None

    if redis is not None and key is not None:
        try:
            cached = await redis.get(key)
            if cached:
                # Empty strings are stored as the literal one-char value so
                # we can distinguish "cached: known to be empty" from
                # "no entry" — both `cached` and `cached == ''` would
                # otherwise look the same.
                if cached == "\0":
                    return ""
                return cached
        except Exception as exc:
            logger.warning(f"[ai-cache] read failed: {exc}")
            # fall through to live call

    # Live call.
    loop = asyncio.get_event_loop()
    try:
        response = await loop.run_in_executor(
            None, lambda: client.model.generate_content(prompt)
        )
    except Exception as exc:
        logger.exception(f"[ai-cache] generate_content raised: {exc}")
        return None

    text: Optional[str] = None
    if hasattr(response, "text"):
        text = response.text
    elif isinstance(response, str):
        text = response
    else:
        text = str(response) if response is not None else None
    if text is not None:
        text = text.strip()

    # Populate cache on success. Don't cache None — that would mask
    # transient Gemini errors as if they were a real "no answer" outcome.
    if redis is not None and key is not None and text is not None:
        try:
            stored = text if text else "\0"
            await redis.set(key, stored, ex=ttl_seconds)
        except Exception as exc:
            logger.warning(f"[ai-cache] write failed: {exc}")

    return text

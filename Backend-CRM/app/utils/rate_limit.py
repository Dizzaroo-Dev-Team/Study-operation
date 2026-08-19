"""Tiny in-memory sliding-window rate limiter.

Per-process. Behind N workers the effective cap is N * limit. Good enough as a
flood-stop on user-facing write endpoints; if you need a hard global cap, swap
for a Redis-backed limiter.
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock
from typing import Deque, Dict, Tuple

_buckets: Dict[Tuple[str, ...], Deque[float]] = {}
_lock = Lock()


def hit(key: Tuple[str, ...], limit: int, window_seconds: float) -> bool:
    """Record a hit for `key` and return True if it is within the limit.

    Returns False if the call would exceed `limit` hits in `window_seconds`.
    """
    now = time.monotonic()
    cutoff = now - window_seconds
    with _lock:
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = deque()
            _buckets[key] = bucket
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

"""
Port of ``events/helpers.js``.

Shared helpers for the Data-platform Kafka consumers. The consumers mirror the
IAM producer, which emits exactly three event types — created / updated /
deleted — with a flat, documented payload. There is no field-alias hunting or
envelope merging: each consumer reads the IAM payload fields directly.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional

from app.config import settings

from ..utils.iam_config import resolve_default_app_id


async def sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def parse_brokers(raw: Optional[str]) -> list[str]:
    if not raw or not isinstance(raw, str):
        return ["localhost:9092"]
    return [s.strip() for s in raw.split(",") if s.strip()]


def env_bool(name: str, default_value: bool = False) -> bool:
    import os

    v = os.environ.get(name)
    if v is None or v == "":
        return default_value
    return str(v).lower() == "true" or v == "1"


def canonical_action(envelope: dict) -> str:
    """
    The action carried by an IAM envelope: 'created' | 'updated' | 'deleted' | ''.

    Accepts both the short form ('created') and the fully-qualified form the
    data-platform producer emits ('user.created', 'hub_user_attribute.created', …)
    by taking the segment after the last dot.
    """
    t = (envelope or {}).get("event_type")
    if t is None:
        t = (envelope or {}).get("action")
    if t is None:
        return ""
    et = str(t).strip().lower()
    dot = et.rfind(".")
    if dot != -1:
        et = et[dot + 1:]  # 'user.created' → 'created'
    if et in ("created", "updated", "deleted"):
        return et
    return ""


def normalize_routing_tag(raw: Any) -> str:
    """Normalize a source/target tag: trim, lowercase, dashes → underscores."""
    if raw is None:
        return ""
    return str(raw).strip().lower().replace("-", "_")


def parse_routing_tag_list(raw: Any) -> set[str]:
    """Split a comma-separated env value into a Set of normalized tags."""
    if raw is None:
        return set()
    return {t for t in (normalize_routing_tag(s) for s in str(raw).split(",")) if t}


def resolve_required_targets() -> set[str]:
    """
    Accepted routing targets for this service: the application id
    (DATA_PLATFORM_APP_ID) plus the broadcast tag "all" (always included in code).
    Returns a Set of normalized tags; contains only "all" when the app id is unset.
    """
    targets: set[str] = set()
    app_id = normalize_routing_tag(resolve_default_app_id())
    if app_id:
        targets.add(app_id)
    targets.add("all")  # broadcast events addressed to "all" are always accepted
    return targets


def is_addressed_to_this_service(envelope: dict) -> dict:
    """
    Routing guard: a message is accepted only when
      source === KAFKA_REQUIRED_SOURCE  AND  target ∈ { DATA_PLATFORM_APP_ID, "all" }.

    KAFKA_REQUIRED_SOURCE comes from the environment with NO hardcoded fallback —
    if it is unset/blank the guard is FAIL-CLOSED and rejects every message.

    Returns ``{"accepted": bool, "source": str, "target": str}``.
    """
    e = envelope if isinstance(envelope, dict) else {}
    source = normalize_routing_tag(e.get("source"))
    target = normalize_routing_tag(e.get("target"))

    required_source = normalize_routing_tag(settings.kafka_required_source)
    required_targets = resolve_required_targets()

    # Fail-closed: with no configured source, accept nothing.
    if not required_source or len(required_targets) == 0:
        return {"accepted": False, "source": source, "target": target}

    source_ok = source == required_source
    target_ok = target in required_targets
    return {"accepted": source_ok and target_ok, "source": source, "target": target}


async def dispatch_by_action(
    envelope: dict,
    *,
    on_created: Optional[Callable[[dict], Awaitable[None]]] = None,
    on_updated: Optional[Callable[[dict], Awaitable[None]]] = None,
    on_deleted: Optional[Callable[[dict], Awaitable[None]]] = None,
) -> None:
    """
    Dispatch a parsed IAM envelope to one of three action handlers based on its
    event_type. Unknown/missing types are ignored.
    """
    action = canonical_action(envelope)
    if action == "created":
        if on_created:
            await on_created(envelope)
        return
    if action == "updated":
        if on_updated:
            await on_updated(envelope)
        return
    if action == "deleted":
        if on_deleted:
            await on_deleted(envelope)
        return
    return

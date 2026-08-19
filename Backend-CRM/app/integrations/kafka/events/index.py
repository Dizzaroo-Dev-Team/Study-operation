"""
Port of ``events/index.js`` — Data-platform topic registry & routing.

Single source of truth mapping every consumed topic to the handler that
processes it. The consumer (``data_platform_consumer``) holds only
connection/lifecycle code and delegates all event handling here.

NOTE: the reference also registered ``milestone`` and ``document notification``
handlers. This app PRODUCES those topics (see ``app.integrations.milestones_kafka``),
so they are intentionally not consumed here — only the six IAM sync topics are.
"""
from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from app.config import settings

from .app_attribute_definition_event import handle_app_attribute_definition_message
from .app_user_attribute_event import handle_app_attribute_message
from .helpers import is_addressed_to_this_service, resolve_required_targets
from .hub_user_attribute_event import handle_hub_attribute_message
from .policy_event import handle_policy_message
from .resource_event import handle_resource_message
from .user_event import handle_user_message

log = logging.getLogger("kafka.DataPlatformRouter")

# Async handler that receives a raw Kafka message value (bytes) and processes it.
RawHandler = Callable[[bytes], Awaitable[None]]


def parse_json(value: bytes | None) -> dict:
    """Parse a raw Kafka message value into a JSON object."""
    try:
        return json.loads((value or b"").decode("utf-8") or "{}")
    except Exception:
        return {}


def routed(topic: str, handle: Callable[[dict], Awaitable[None]]) -> RawHandler:
    """
    Wrap a topic handler with the routing guard: only envelopes whose
    source === KAFKA_REQUIRED_SOURCE and whose target ∈ {DATA_PLATFORM_APP_ID, all}
    reach the handler. Everything else is dropped (logged) before any DB work.
    """

    async def _run(value: bytes) -> None:
        envelope = parse_json(value)
        guard = is_addressed_to_this_service(envelope)
        event_id = envelope.get("event_id") or envelope.get("eventId")
        event_type = envelope.get("event_type") or envelope.get("eventType") or envelope.get("type")
        if not guard["accepted"]:
            # info (not debug) so routing rejections are visible at default level —
            # these are the usual reason "nothing happens".
            log.info(
                "Skip message: not addressed to this service "
                "(topic=%s eventId=%s eventType=%s source=%s target=%s "
                "requiredSource=%s requiredTargets=%s)",
                topic, event_id, event_type, guard["source"] or None, guard["target"] or None,
                settings.kafka_required_source or None, sorted(resolve_required_targets()),
            )
            return
        log.info(
            "Accepted message; dispatching to handler (topic=%s eventId=%s eventType=%s source=%s target=%s)",
            topic, event_id, event_type, guard["source"], guard["target"],
        )
        await handle(envelope)

    return _run


def resolve_data_platform_topics() -> list[dict]:
    """
    Resolve the list of {topic, handle} entries consumed over the Data-platform
    connection. Topic names come from settings (the Data Platform contract env
    vars); any topic left blank is skipped in build_topic_handler_map.
    """
    users_topic = settings.users_kafka_topic
    hub_attrs_topic = settings.hub_user_attributes_kafka_topic
    app_attrs_topic = settings.app_user_attributes_kafka_topic
    app_attr_defs_topic = settings.app_attribute_definitions_kafka_topic
    policies_topic = settings.policies_kafka_topic
    resources_topic = settings.resources_kafka_topic

    return [
        {"topic": users_topic, "handle": routed(users_topic, handle_user_message)},
        {"topic": hub_attrs_topic, "handle": routed(hub_attrs_topic, handle_hub_attribute_message)},
        {"topic": app_attrs_topic, "handle": routed(app_attrs_topic, handle_app_attribute_message)},
        {"topic": app_attr_defs_topic, "handle": routed(app_attr_defs_topic, handle_app_attribute_definition_message)},
        {"topic": policies_topic, "handle": routed(policies_topic, handle_policy_message)},
        {"topic": resources_topic, "handle": routed(resources_topic, handle_resource_message)},
    ]


def build_topic_handler_map() -> dict[str, RawHandler]:
    """Build a dict[topic, handle] from the registry, resolving topic names once."""
    mapping: dict[str, RawHandler] = {}
    for entry in resolve_data_platform_topics():
        topic = entry["topic"]
        if topic:
            mapping[topic] = entry["handle"]
    return mapping

"""
Port of ``dataPlatformConsumer.js``.

The SINGLE inbound Data-platform Kafka connection for this service
(KAFKA_BROKERS, consumer group DATAPLATFORM_KAFKA_GROUP_ID) — the same
connection the milestone PRODUCER uses. Connects directly to the self-hosted
broker with PLAINTEXT (no SASL/SSL).

This file holds ONLY connection/lifecycle code; the topic registry and all event
handling live in ``events/index.py``. Startup is non-blocking: if the broker
is unreachable after the retry budget, the FastAPI app keeps running and the
failure is logged (matches Node behaviour).
"""
from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiokafka import AIOKafkaConsumer

from app.config import settings
from app.db.mongo import get_mongo_db

from .events.index import build_topic_handler_map
from .models.sync_models import ensure_indexes

log = logging.getLogger("kafka.DataPlatformConsumer")

RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2.0

# Module-level singletons — mirror the Node singletons.
_consumer: Optional[AIOKafkaConsumer] = None
_run_task: Optional[asyncio.Task] = None
_shutting_down: bool = False


def _derive_brokers() -> list[str]:
    """Resolve the Data-platform broker address from ``KAFKA_BROKERS`` (CSV
    host:port) — same source as the milestone producer so both share one
    connection target."""
    raw = settings.kafka_brokers
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    return []


def _build_consumer(topics: list[str]) -> AIOKafkaConsumer:
    """aiokafka consumer wired for the self-hosted broker (PLAINTEXT)."""
    return AIOKafkaConsumer(
        *topics,
        bootstrap_servers=_derive_brokers(),
        client_id=settings.kafka_consumer_client_id,
        group_id=settings.dataplatform_kafka_group_id,
        enable_auto_commit=True,
        auto_offset_reset=("earliest" if settings.kafka_start_from_beginning else "latest"),
    )


async def _connect_with_retry(topics: list[str]) -> Optional[AIOKafkaConsumer]:
    group_id = settings.dataplatform_kafka_group_id
    client_id = settings.kafka_consumer_client_id

    # Group id / client id come from config (defaults provided); brokers are required.
    if not _derive_brokers():
        log.warning(
            "KAFKA_BROKERS not set; Data-platform consumer will not start"
        )
        return None
    if not group_id:
        log.warning("DATAPLATFORM_KAFKA_GROUP_ID not set; Data-platform consumer will not start")
        return None
    if not client_id:
        log.warning("KAFKA_CONSUMER_CLIENT_ID not set; Data-platform consumer will not start")
        return None

    last_err: Optional[BaseException] = None
    for attempt in range(1, RETRY_ATTEMPTS + 1):
        try:
            consumer = _build_consumer(topics)
            await consumer.start()
            log.info(
                "DataPlatformConsumer: connected to Kafka broker=%s group=%s topics=%d",
                _derive_brokers(), group_id, len(topics),
            )
            return consumer
        except Exception as err:  # noqa: BLE001
            last_err = err
            log.error(
                "DataPlatformConsumer: connect failed attempt %d/%d; retrying: %s",
                attempt, RETRY_ATTEMPTS, err,
            )
            if attempt < RETRY_ATTEMPTS:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
    log.error(
        "DataPlatformConsumer: not started after %d attempts; HTTP server continues. last_err=%s",
        RETRY_ATTEMPTS, last_err,
    )
    return None


async def _run_loop(consumer: AIOKafkaConsumer, topic_handlers: dict) -> None:
    """One message at a time, with per-message try/except so a poison pill never
    kills the whole consumer."""
    try:
        async for message in consumer:
            if _shutting_down:
                break
            handle = topic_handlers.get(message.topic)
            if handle is None:
                log.debug("DataPlatformConsumer: no handler for topic=%s; ignoring", message.topic)
                continue
            try:
                await handle(message.value)
            except Exception as err:  # noqa: BLE001
                log.error(
                    "DataPlatformConsumer: unhandled error in message handler "
                    "topic=%s offset=%s err=%s",
                    message.topic, message.offset, err, exc_info=True,
                )
    except asyncio.CancelledError:
        raise
    except Exception as err:  # noqa: BLE001
        if not _shutting_down:
            log.error("DataPlatformConsumer: run loop ended unexpectedly: %s", err, exc_info=True)


async def initialize_data_platform_consumer() -> None:
    """
    Start the Data-platform consumer (non-blocking — HTTP server is unaffected by
    failures). Port of ``initializeDataPlatformConsumer``.
    """
    global _consumer, _run_task, _shutting_down

    if _shutting_down:
        return
    if _consumer is not None:
        log.warning("DataPlatformConsumer: already initialised; skip")
        return

    topic_handlers = build_topic_handler_map()
    topics = list(topic_handlers.keys())
    if not topics:
        log.warning("DataPlatformConsumer: no topics configured; not starting")
        return

    # Best-effort index creation (mongoose built these on model load).
    try:
        mongo_db = await get_mongo_db()
        await ensure_indexes(mongo_db)
    except Exception as err:  # noqa: BLE001
        log.warning("DataPlatformConsumer: could not ensure Mongo indexes at startup: %s", err)

    consumer = await _connect_with_retry(topics)
    if consumer is None:
        return

    _consumer = consumer
    _run_task = asyncio.create_task(
        _run_loop(consumer, topic_handlers), name="data-platform-consumer-run-loop"
    )
    log.info("DataPlatformConsumer: run loop started (background)")


async def shutdown_data_platform_consumer() -> None:
    """Stop the consumer cleanly. Safe to call multiple times. Port of
    ``shutdownDataPlatformConsumer``."""
    global _consumer, _run_task, _shutting_down

    _shutting_down = True
    if _consumer is None:
        return
    try:
        log.info("DataPlatformConsumer: disconnecting")
        await _consumer.stop()
        log.info("DataPlatformConsumer: disconnected")
    except Exception as err:  # noqa: BLE001
        log.exception("DataPlatformConsumer: error during disconnect: %s", err)
    finally:
        if _run_task is not None and not _run_task.done():
            _run_task.cancel()
            try:
                await _run_task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        _consumer = None
        _run_task = None


# Backward-compatible aliases (mirror the Node module's exported names).
initialize_milestone_consumer = initialize_data_platform_consumer
shutdown_milestone_consumer = shutdown_data_platform_consumer

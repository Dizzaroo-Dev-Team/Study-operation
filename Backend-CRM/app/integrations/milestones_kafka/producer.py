"""
aiokafka producer wired for the self-hosted Data Platform Kafka broker.

Connects directly (PLAINTEXT — no SASL/SSL) to the broker(s) listed in the
``KAFKA_BROKERS`` env var (comma-separated ``host:port`` list).

The producer is kept in a module-level singleton so a single FastAPI process
holds at most one connection. Startup is non-blocking: if the broker is
unreachable after the retry budget we log and leave ``_producer`` as ``None`` —
``publish_envelope`` then degrades to a logged no-op so a milestone publish can
never break a domain request.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from aiokafka import AIOKafkaProducer

from app.config import settings

logger = logging.getLogger(__name__)

RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 1.0

# Module-level singleton so one FastAPI process holds at most one connection.
_producer: Optional[AIOKafkaProducer] = None
_start_lock: Optional[asyncio.Lock] = None


def _get_start_lock() -> asyncio.Lock:
    # Lazily created so we bind to the running loop, not import-time.
    global _start_lock
    if _start_lock is None:
        _start_lock = asyncio.Lock()
    return _start_lock


def _derive_brokers() -> list[str]:
    """Resolve bootstrap brokers from ``KAFKA_BROKERS`` (CSV host:port)."""
    raw = settings.kafka_brokers
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    raise RuntimeError(
        "milestone producer: cannot resolve brokers — set KAFKA_BROKERS"
    )


def _build_producer() -> AIOKafkaProducer:
    return AIOKafkaProducer(
        bootstrap_servers=_derive_brokers(),
        client_id=settings.milestones_kafka_client_id,
        acks="all",
        enable_idempotence=False,
        # We serialize the envelope ourselves to UTF-8 JSON before send().
    )


async def start_milestones_producer() -> None:
    """
    Connect the producer with a small retry budget. Non-blocking on failure:
    logs and leaves the singleton unset so publishes degrade to no-ops.
    Safe to call multiple times (idempotent).
    """
    global _producer

    async with _get_start_lock():
        if _producer is not None:
            logger.debug("[milestones-kafka] producer already started; skip")
            return

        last_err: Optional[BaseException] = None
        for attempt in range(1, RETRY_ATTEMPTS + 1):
            try:
                producer = _build_producer()
                await producer.start()
                _producer = producer
                logger.info(
                    "[milestones-kafka] producer connected brokers=%s topic=%s",
                    _derive_brokers(), settings.milestones_kafka_topic,
                )
                return
            except Exception as err:  # noqa: BLE001
                last_err = err
                logger.warning(
                    "[milestones-kafka] connect attempt %d/%d failed: %s",
                    attempt, RETRY_ATTEMPTS, err,
                )
                if attempt < RETRY_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
        logger.error(
            "[milestones-kafka] producer not started after %d attempts; publishes "
            "will be no-ops. last_err=%s",
            RETRY_ATTEMPTS, last_err,
        )


async def stop_milestones_producer() -> None:
    """Flush and close the producer. Safe to call multiple times."""
    global _producer
    if _producer is None:
        return
    try:
        logger.info("[milestones-kafka] stopping producer…")
        await _producer.stop()
        logger.info("[milestones-kafka] producer stopped")
    except Exception as exc:  # noqa: BLE001
        logger.exception("[milestones-kafka] error stopping producer: %s", exc)
    finally:
        _producer = None


async def publish_envelope(
    envelope: dict, *, topic: Optional[str] = None, key: Optional[str] = None
) -> bool:
    """
    Serialize and send one envelope to ``topic`` (defaults to the milestone
    topic). Returns True on success, False if the producer is unavailable or the
    send fails. NEVER raises — Data Platform delivery is best-effort and must not
    break the calling request.
    """
    target_topic = topic or settings.milestones_kafka_topic
    if _producer is None:
        logger.warning(
            "[milestones-kafka] producer unavailable; dropping event %s (event_type=%s)",
            envelope.get("event_id"), envelope.get("event_type"),
        )
        return False
    try:
        value = json.dumps(envelope, separators=(",", ":")).encode("utf-8")
        key_bytes = key.encode("utf-8") if key else None
        await _producer.send_and_wait(target_topic, value=value, key=key_bytes)
        logger.info(
            "[milestones-kafka] published event_id=%s event_type=%s topic=%s key=%s",
            envelope.get("event_id"), envelope.get("event_type"), target_topic, key,
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[milestones-kafka] publish failed event_id=%s err=%s",
            envelope.get("event_id"), exc, exc_info=True,
        )
        return False

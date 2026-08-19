"""
Port of ``events/policyEvent.js`` — iam.policies.events.

IAM emits three actions with this flat payload:
  created / updated / deleted →
    { id, policy_type, application_id, name, description, status, priority,
      effect, conditions }
  (application_key is carried on the envelope, not the payload)

No field aliases, no envelope merging, no app-allowlist filtering — read the
documented fields and write them straight to local_policies.

NOTE (matches the reference): an archived policy arrives as an `updated` event
with status='archived' and is KEPT as a row; the policy engine filters on status
at read time. Only an explicit `deleted` event removes the row.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db.mongo import get_mongo_db

from ..models.sync_models import COLL_LOCAL_POLICIES
from ..utils.logger import create_module_logger
from ..utils.policy_evaluation_cache import invalidate_policy_evaluation_caches
from .helpers import dispatch_by_action

log = create_module_logger("KafkaConsumer")


def _get_payload(envelope: dict) -> dict:
    p = (envelope or {}).get("payload")
    return p if isinstance(p, dict) else {}


def _map_effect(effect) -> str:
    """local_policies.effect enum only allows PERMIT | DENY; IAM may send ALLOW."""
    return "DENY" if str(effect if effect is not None else "PERMIT").strip().upper() == "DENY" else "PERMIT"


async def upsert_policy(envelope: dict) -> None:
    """created / updated → upsert the policy row."""
    p = _get_payload(envelope)
    if not p.get("id"):
        log.warning("Policy event missing id; skip")
        return

    mongo_db = await get_mongo_db()
    await mongo_db[COLL_LOCAL_POLICIES].update_one(
        {"_id": p["id"]},
        {
            "$set": {
                "name": p.get("name"),
                "description": p.get("description"),
                "status": p.get("status") if p.get("status") is not None else "draft",
                "priority": int(p.get("priority") or 0),
                "effect": _map_effect(p.get("effect")),
                "conditions": p.get("conditions"),
                "policy_type": p.get("policy_type"),
                "app_id": p.get("application_id"),
                "syncedAt": datetime.now(timezone.utc),
            }
        },
        upsert=True,
    )
    invalidate_policy_evaluation_caches()
    log.info("Upserted local_policies from Kafka policyId=%s", p["id"])


async def delete_policy(envelope: dict) -> None:
    """deleted → remove the policy row."""
    p = _get_payload(envelope)
    policy_id = p.get("id")
    if not policy_id:
        log.warning("Policy delete event missing id; skip")
        return

    mongo_db = await get_mongo_db()
    await mongo_db[COLL_LOCAL_POLICIES].delete_one({"_id": policy_id})
    invalidate_policy_evaluation_caches()
    log.info("Removed local_policies from Kafka policyId=%s", policy_id)


async def handle_policy_message(envelope: dict) -> None:
    """iam.policies.events — dispatch to created/updated/deleted."""
    await dispatch_by_action(
        envelope,
        on_created=upsert_policy,
        on_updated=upsert_policy,
        on_deleted=delete_policy,
    )

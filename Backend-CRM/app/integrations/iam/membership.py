"""Study-level membership resolution against IAM ``resource_access``.

Single source of truth for "does user X have access to study Y", where Y is a
``local_resources._id`` — the same identifier that is stored on conversations as
``study_id`` and on threads as ``related_study_id``, and the same identifier IAM
publishes inside ``local_app_user_attributes`` ``resource_access`` entries
(confirmed by the Stage-1.5 id-mapping spike: MATCH, no translation needed).

The resource_access → resource_id resolution lives here ONLY. ``GET /study-team``
(``app/modules/sites/routes/sites.py``) imports :func:`parse_resource_access_value`
so there is one implementation, not two copies.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional, Set

from app.integrations.kafka.models.sync_models import COLL_LOCAL_APP_USER_ATTRIBUTES

logger = logging.getLogger(__name__)

# IAM publishes per-user, per-resource grants as documents with this
# ``attributeName`` whose ``value`` is the ``[{role, resource_id}, ...]`` array.
RESOURCE_ACCESS_ATTRIBUTE = "resource_access"


def parse_resource_access_value(value: Any) -> List[dict]:
    """Normalise a ``resource_access`` ``value`` list.

    Returns ``[{"resource_id": str, "role": Optional[str]}, ...]`` deduped by
    ``resource_id`` and preserving first-seen order. Lifted verbatim from the
    loop that used to live inline in ``GET /study-team`` so both callers share
    one resolution. A non-list / malformed value yields ``[]``.
    """
    out: List[dict] = []
    if not isinstance(value, list):
        return out
    seen: Set[str] = set()
    for entry in value:
        if not isinstance(entry, dict):
            continue
        rid = str(
            entry.get("resource_id")
            or entry.get("resourceId")
            or entry.get("id")
            or ""
        )
        if not rid or rid in seen:
            continue
        seen.add(rid)
        out.append({"resource_id": rid, "role": entry.get("role") or None})
    return out


async def get_user_study_resource_ids(mongo_db, user_id: str) -> Set[str]:
    """Return every ``resource_id`` granted to ``user_id`` via IAM resource_access.

    One indexed lookup on ``(userId, attributeName)``.
    """
    uid = str(user_id or "").strip()
    if not uid:
        return set()
    doc = await mongo_db[COLL_LOCAL_APP_USER_ATTRIBUTES].find_one(
        {"attributeName": RESOURCE_ACCESS_ATTRIBUTE, "userId": uid}
    )
    if not doc:
        return set()
    return {e["resource_id"] for e in parse_resource_access_value(doc.get("value"))}


async def user_can_access_study(user_id: str, study_resource_id: str) -> bool:
    """True iff ``user_id`` holds an IAM resource_access grant for the study.

    ``study_resource_id`` is a ``local_resources._id`` string (== the value
    stored on a conversation's ``study_id`` / a thread's ``related_study_id``).

    Fail-closed: empty inputs, a missing grant, or any Mongo/IAM error all
    resolve to ``False`` — the gate never opens on uncertainty.
    """
    uid = str(user_id or "").strip()
    sid = str(study_resource_id or "").strip()
    if not uid or not sid:
        return False
    try:
        from app.db.mongo import get_mongo_db

        mongo_db = await get_mongo_db()
        resource_ids = await get_user_study_resource_ids(mongo_db, uid)
        return sid in resource_ids
    except Exception:
        logger.exception(
            "user_can_access_study: membership lookup failed (user=%s study=%s); "
            "failing closed",
            uid,
            sid,
        )
        return False


# Owner hub-roles that bypass the per-study grant filter (mirrors the owner
# override in ``GET /studies`` — see sites.routes.sites._user_is_hub_owner). Kept
# here so the WRITE-route entitlement gate below has the SAME semantics as the
# read path: an app owner sees, and may act in, every study.
_OWNER_HUB_ROLES = {"APP_OWNER", "HUB_OWNER"}


async def user_is_app_owner(mongo_db, user_id: str) -> bool:
    """True when the user's ``hub_roles`` attribute contains an owner role."""
    uid = str(user_id or "").strip()
    if not uid:
        return False
    doc = await mongo_db["local_hub_user_attributes"].find_one(
        {"userId": uid, "attributeKey": "hub_roles"}
    )
    if not doc:
        return False
    raw = doc.get("value")
    roles = raw if isinstance(raw, list) else [raw]
    return any(str(r).strip().upper() in _OWNER_HUB_ROLES for r in roles if r)


async def user_can_act_in_study(user_id: str, study_resource_id: str) -> bool:
    """Study-entitlement gate for WRITE/mutation routes.

    The caller may act in the study iff they are an **app owner** OR hold an IAM
    ``resource_access`` grant for it — the SAME owner-or-grant rule ``GET /studies``
    uses to decide which studies a user sees, so "can see it" and "can act in it"
    stay consistent (no roles logic; a later roles decision governs *which* actions
    a member may take within a study).

    ``study_resource_id`` is a ``local_resources._id`` (== a conversation's
    ``study_id`` and, per the id-mapping spike, == an agreement's postgres
    ``study_id``). Fail-closed on empty inputs / missing grant / any error.
    """
    uid = str(user_id or "").strip()
    sid = str(study_resource_id or "").strip()
    if not uid or not sid:
        return False
    try:
        from app.db.mongo import get_mongo_db

        mongo_db = await get_mongo_db()
        if await user_is_app_owner(mongo_db, uid):
            return True
        resource_ids = await get_user_study_resource_ids(mongo_db, uid)
        return sid in resource_ids
    except Exception:
        logger.exception(
            "user_can_act_in_study: membership lookup failed (user=%s study=%s); "
            "failing closed",
            uid,
            sid,
        )
        return False


__all__ = [
    "parse_resource_access_value",
    "get_user_study_resource_ids",
    "user_can_access_study",
    "user_is_app_owner",
    "user_can_act_in_study",
]

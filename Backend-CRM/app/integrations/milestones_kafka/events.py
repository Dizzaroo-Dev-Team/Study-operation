"""
Envelope construction + the public publish helpers for site-milestone events.

Envelope shape (per the Data Platform integration guide):

    {
      "event_id":    "<uuid>",           # unique per publish (idempotency)
      "event_type":  "updated",          # created | updated | deleted
      "entity_type": "site_milestone",   # the kind of entity this event is about
      "entity_id":   "<siteId>",         # the entity's id (site id for milestones)
      "source":      "study_operations", # our app key
      "target":      "data_platform",    # router app key
      "payload":     { ...milestone fields... }  # no routing fields inside payload
    }

Routing lives in the envelope; ``payload`` carries milestone fields only.

``SiteMilestone`` is the canonical catalog of the milestones Study Operations
emits. Domain code publishes one with a single line, e.g.:

    from app.integrations.milestones_kafka import publish_site_milestone, SiteMilestone
    await publish_site_milestone(SiteMilestone.CTA_FULLY_EXECUTED, site_id=str(site.id))
"""
from __future__ import annotations

import logging
import uuid
from enum import Enum
from typing import Optional, Union

from app.config import settings

from .producer import publish_envelope

logger = logging.getLogger(__name__)

# Field length caps from the integration guide.
_MAX_SITE_ID = 100
_MAX_MILESTONE_ID = 100
_MAX_MILESTONE_NAME = 255


class MilestoneEventType(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"


# The kind of entity every milestone event describes (envelope routing field).
ENTITY_TYPE = "site_milestone"


class SiteMilestone(Enum):
    """
    Canonical site-milestone catalog. ``value`` is the wire ``milestoneId``;
    ``label`` is the human-readable ``milestoneName``.
    """

    FEASIBILITY_QUESTIONNAIRE_SENT = ("FEASIBILITY_QUESTIONNAIRE_SENT", "Feasibility Questionnaire Sent")
    SITE_QUALIFICATION_VISIT_SCHEDULED = ("SITE_QUALIFICATION_VISIT_SCHEDULED", "Site Qualification Visit Scheduled")
    SITE_QUALIFICATION_APPROVED = ("SITE_QUALIFICATION_APPROVED", "Site Qualification Approved")
    SITE_REJECTED = ("SITE_REJECTED", "Site Rejected")
    SITE_SELECTED = ("SITE_SELECTED", "Site Selected")
    BUDGET_APPROVED = ("BUDGET_APPROVED", "Budget Approved")
    CDA_FULLY_EXECUTED = ("CDA_FULLY_EXECUTED", "CDA Fully Executed")
    CTA_FULLY_EXECUTED = ("CTA_FULLY_EXECUTED", "CTA Fully Executed")
    SIV_SCHEDULED = ("SIV_SCHEDULED", "SIV Scheduled")
    SIV_CONDUCTED = ("SIV_CONDUCTED", "SIV Conducted")
    MONITORING_VISIT_PLANNED = ("MONITORING_VISIT_PLANNED", "Monitoring Visit Planned")
    IMV_CLOSED = ("IMV_CLOSED", "IMV Closed")
    MONITORING_FINDING_CLOSED = ("MONITORING_FINDING_CLOSED", "Monitoring Finding Closed")
    FINDING_CLOSED = ("FINDING_CLOSED", "Finding Closed")
    COV_CONDUCTED = ("COV_CONDUCTED", "COV Conducted")

    def __init__(self, milestone_id: str, label: str) -> None:
        self.milestone_id = milestone_id
        self.label = label


# milestoneId → SiteMilestone, for resolving raw string ids.
_BY_ID: dict[str, SiteMilestone] = {m.milestone_id: m for m in SiteMilestone}


def resolve_milestone(value: Union["SiteMilestone", str]) -> Optional[SiteMilestone]:
    if isinstance(value, SiteMilestone):
        return value
    return _BY_ID.get(str(value))


def _build_envelope(event_type: MilestoneEventType, entity_id: str, payload: dict) -> dict:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": event_type.value,
        "entity_type": ENTITY_TYPE,
        "entity_id": entity_id,
        "source": settings.milestones_source_app,
        "target": settings.milestones_target_app,
        "payload": payload,
    }


async def publish_site_milestone(
    milestone: Union[SiteMilestone, str],
    *,
    site_id: str,
    event_type: Union[MilestoneEventType, str] = MilestoneEventType.CREATED,
) -> bool:
    """
    Publish a site-milestone create/update for one site.

    Best-effort: self-guards on ``start_milestones_producer`` and returns False
    (instead of raising) when the producer is disabled/unavailable, the
    milestone is unknown, or required fields are missing — so callers in a
    request path are never broken.

    ``milestone`` may be a ``SiteMilestone`` or its raw id string. To remove a
    site's milestone, call ``delete_site_milestone`` instead.
    """
    if not settings.start_milestones_producer:
        return False

    if isinstance(event_type, str):
        try:
            event_type = MilestoneEventType(event_type)
        except ValueError:
            logger.exception("[milestones-kafka] unknown eventType=%r; skip", event_type)
            return False

    if event_type is MilestoneEventType.DELETED:
        return await delete_site_milestone(site_id=site_id)

    if not site_id:
        logger.error("[milestones-kafka] missing site_id; skip milestone=%r", milestone)
        return False

    resolved = resolve_milestone(milestone)
    if resolved is None:
        logger.error("[milestones-kafka] unknown milestone=%r; skip site=%s", milestone, site_id)
        return False

    payload = {
        "siteId": str(site_id)[:_MAX_SITE_ID],
        "milestoneId": resolved.milestone_id[:_MAX_MILESTONE_ID],
        "milestoneName": resolved.label[:_MAX_MILESTONE_NAME],
    }
    return await publish_envelope(
        _build_envelope(event_type, payload["siteId"], payload), key=payload["siteId"]
    )


async def delete_site_milestone(*, site_id: str) -> bool:
    """Publish a milestone ``deleted`` event (removes the site's milestone)."""
    if not settings.start_milestones_producer:
        return False
    if not site_id:
        logger.error("[milestones-kafka] missing site_id for delete; skip")
        return False
    site_id = str(site_id)[:_MAX_SITE_ID]
    return await publish_envelope(
        _build_envelope(MilestoneEventType.DELETED, site_id, {"siteId": site_id}), key=site_id
    )


# ─── Monitoring-visit classifier ──────────────────────────────────────────────
# Monitoring visit types are free-form strings (see monitoring/aggregator.py
# `_normalize_visit_type`). We classify by keyword so this works on raw OR
# normalized values. `phase` is the lifecycle moment the visit reached.

def classify_visit_milestone(visit_type: Optional[str], phase: str) -> Optional[SiteMilestone]:
    """
    Map a monitoring visit (type + lifecycle phase) to a milestone, or None.

    phase ∈ {"scheduled", "conducted", "closed"}:
      - scheduled: visit created          → SQV scheduled / SIV scheduled / generic planned
      - conducted: visit confirmed/held    → SQV approved / SIV conducted / COV conducted
      - closed:    visit closed & locked   → interim/on-site monitoring → IMV closed
    """
    t = (visit_type or "").strip().lower()
    is_qualification = "qualification" in t or "sqv" in t
    is_initiation = "initiation" in t or t == "siv"
    is_closeout = "close-out" in t or "close out" in t or "closeout" in t or t == "cov"

    if phase == "scheduled":
        if is_qualification:
            return SiteMilestone.SITE_QUALIFICATION_VISIT_SCHEDULED
        if is_initiation:
            return SiteMilestone.SIV_SCHEDULED
        return SiteMilestone.MONITORING_VISIT_PLANNED
    if phase == "conducted":
        if is_qualification:
            return SiteMilestone.SITE_QUALIFICATION_APPROVED
        if is_initiation:
            return SiteMilestone.SIV_CONDUCTED
        if is_closeout:
            return SiteMilestone.COV_CONDUCTED
        return None
    if phase == "closed":
        # Closing a generic interim / on-site monitoring visit.
        if not (is_qualification or is_initiation or is_closeout):
            return SiteMilestone.IMV_CLOSED
        return None
    return None


async def publish_visit_milestone(
    *, site_id: str, visit_type: Optional[str], phase: str
) -> bool:
    """Classify a monitoring visit event and publish the matching milestone (if any)."""
    if not settings.start_milestones_producer:
        return False
    milestone = classify_visit_milestone(visit_type, phase)
    if milestone is None:
        logger.debug(
            "[milestones-kafka] no milestone for visit_type=%r phase=%r; skip", visit_type, phase
        )
        return False
    return await publish_site_milestone(milestone, site_id=site_id)

"""
Site-milestone Kafka PRODUCER — Study Operations → Data Platform.

Study Operations is the upstream producer for site-milestone events. When the
site-status activation workflow advances, we publish a `site_milestone.*` event
onto the shared `sites.milestones.events` Event Hub topic. The Data Platform
consumes, persists, and forwards to downstream apps (e.g. NeuroDoc).

This is the app's Kafka PRODUCER over the shared Data Platform Event Hub
connection. (A future inbound IAM consumer is intended to reuse this same
connection; the old standalone IAM Kafka consumer has been removed.)

Public API:
  - ``start_milestones_producer`` / ``stop_milestones_producer`` (lifecycle,
    wired into the FastAPI lifespan in ``app.main``)
  - ``publish_site_milestone`` (best-effort fire-and-forget; domain code calls
    this — failures are logged and never bubble up into the request flow)
"""
from .producer import start_milestones_producer, stop_milestones_producer, publish_envelope
from .events import (
    publish_site_milestone,
    publish_visit_milestone,
    delete_site_milestone,
    classify_visit_milestone,
    resolve_milestone,
    MilestoneEventType,
    SiteMilestone,
)

__all__ = [
    "start_milestones_producer",
    "stop_milestones_producer",
    "publish_envelope",
    "publish_site_milestone",
    "publish_visit_milestone",
    "delete_site_milestone",
    "classify_visit_milestone",
    "resolve_milestone",
    "MilestoneEventType",
    "SiteMilestone",
]

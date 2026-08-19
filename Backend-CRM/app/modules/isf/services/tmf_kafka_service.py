"""
TMF document routing via Kafka.

Replaces the old email/Mailgun TMF path: when a user clicks "Enable TMF Routing"
on an ISF document, a mapped document payload is published to the Data Platform
``platform.documents`` topic. The Data Platform ingests it downstream.

The envelope conforms to the Data Platform's standard event envelope
(snake_case, routing in the envelope, entity payload under ``payload``):

    {
      "event_id":    "<new uuid per publish — Data Platform dedup key>",
      "event_type":  "document.created",
      "entity_type": "document",
      "entity_id":   "<STABLE uuid5 derived from the Mongo ObjectId — the Data
                      Platform upserts on this, so re-sends must reuse it>",
      "source":      "study_operations",
      "timestamp":   "<ISO-8601 UTC at publish time, e.g. 2026-07-12T18:06:19Z>",
      "payload": {
        "name":        "<document title — REQUIRED, dropped silently if absent>",
        "doc_type":    "<document type — REQUIRED, dropped silently if absent>",
        "scope":       "STUDY" | "PROJECT" | "GLOBAL",
        "study_id":    "<CRM Study.id uuid | null>",
        "project_id":  "<project uuid | null — never sent without study_id>",
        "description": "<description | null>",
        "tags":        ["<tag>", ...] | null,
        "metadata":    { ...custom_metadata or {} },
        "source_blob": "<short-lived Azure SAS read URL>",
        "status":      "<status | 'active'>",
        "created_by":  "<user id who triggered TMF routing — omitted if unknown>"
      }
    }

Consumer-side constraints: ``metadata`` must be a JSON object, ``tags`` a JSON
array of strings, and ``project_id`` without ``study_id`` is rejected.

Best-effort like the milestone producer: never raises into the request path.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.utils.log_sanitize import sfmt
from app.integrations.milestones_kafka import (
    publish_envelope,
    start_milestones_producer,
)

from . import azure_upload, isf_workflow_service
from .isf_workflow_service import _serialize_workflow_for_response

logger = logging.getLogger(__name__)

ENTITY_TYPE = "document"
EVENT_TYPE = "document.created"  # fully qualified entity.action form

# How long the SAS read URL in `source_blob` stays valid. Kept generous so the
# consumer can still fetch the blob if ingestion is delayed, retried, or replayed.
SAS_EXPIRY_HOURS = 24

# ISF documents are keyed by Mongo ObjectId, but the Data Platform requires the
# document id to be a UUID (its `resolve_document_id` calls `UUID(...)`). We derive
# a STABLE UUID from the ObjectId via uuid5 so re-publishes map to the same id
# (keeps the consumer's idempotency intact). Fixed namespace = deterministic.
DOCUMENT_ID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "study_operations/isf_document")


def _as_uuid_or_none(value) -> Optional[str]:
    """Return the value as a canonical UUID string, or None if it isn't a UUID."""
    if not value:
        return None
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _document_uuid(raw: dict, fallback_id: str) -> str:
    """Stable UUID for the document, derived from its Mongo ObjectId (uuid5)."""
    seed = str(
        raw.get("_id")
        or raw.get("documentId")
        or raw.get("document_id")
        or fallback_id
    )
    return str(uuid.uuid5(DOCUMENT_ID_NAMESPACE, seed))


async def _resolve_study_uuid(study_hint) -> Optional[str]:
    """
    Resolve a study reference to the CRM ``Study.id`` UUID.

    ``study_hint`` may already be a UUID (returned as-is) or the external
    ``study_id`` string (e.g. "STUDY-2024-001"), which we look up in Postgres.
    Returns None when it can't be resolved to a real UUID.
    """
    if not study_hint:
        return None

    already = _as_uuid_or_none(study_hint)
    if already:
        return already

    try:
        from sqlalchemy import select

        from app.db import AsyncSessionLocal
        from app.models.study import Study

        async with AsyncSessionLocal() as session:
            row = await session.execute(
                select(Study.id).where(Study.study_id == str(study_hint))
            )
            found = row.scalar_one_or_none()
            return str(found) if found else None
    except Exception as exc:  # noqa: BLE001 - resolution is best-effort
        logger.warning("Could not resolve study UUID for %r: %s", study_hint, exc)
        return None


def _first(doc: dict, *keys, default=None):
    """Return the first present, non-empty value among ``keys`` (handles both the
    snake_case `isf_documents` and camelCase `isfdocuments` collection shapes)."""
    for k in keys:
        v = doc.get(k)
        if v not in (None, ""):
            return v
    return default


def _to_sas_url(raw_blob: Optional[str]) -> Optional[str]:
    """
    Convert a stored blob URL into a short-lived Azure SAS read URL so the Data
    Platform consumer can download it from the private container. Falls back to
    the raw URL if SAS generation isn't possible (Azure not configured, etc.).
    """
    if not raw_blob:
        return None
    try:
        blob_name = raw_blob.split("/")[-1].split("?")[0]
        if blob_name:
            sas = azure_upload.generate_sas_url(blob_name, expiry_hours=SAS_EXPIRY_HOURS)
            if sas:
                return sas
    except Exception as exc:  # noqa: BLE001 - best-effort; never break publish
        logger.warning("Failed to build SAS URL for blob %r: %s", sfmt(raw_blob), exc)
    return raw_blob


def _build_document_payload(
    raw: dict, *, study_id: Optional[str], created_by: Optional[str] = None
) -> dict:
    """Map a raw Mongo ISF document to the Data Platform document payload."""
    meta = raw.get("custom_metadata") or raw.get("customMetadata") or raw.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}

    # Blob URL lives on the doc (file_url/fileUrl) or, as a fallback, inside metadata.
    raw_blob = _first(raw, "file_url", "fileUrl", "source_blob", "sourceBlob")
    if not raw_blob:
        raw_blob = (
            meta.get("source_blob")
            or meta.get("sourceBlob")
            or meta.get("file_url")
            or meta.get("fileUrl")
        )
    # Hand the consumer a SAS read URL (private container needs it), not the bare blob URL.
    source_blob = _to_sas_url(raw_blob)

    project_id = _first(raw, "project_id", "projectId")
    if not project_id:
        project_id = meta.get("project_id") or meta.get("projectId")
    # Data Platform requires a UUID (or null) here — never a raw non-UUID string.
    project_id = _as_uuid_or_none(project_id)
    # Consumer rejects project_id without study_id — never send that combination.
    if project_id and not study_id:
        logger.warning(
            "ISF document has project_id %s but no resolvable study_id; "
            "dropping project_id from TMF payload", sfmt(project_id),
        )
        project_id = None

    tags = raw.get("tags")
    if isinstance(tags, list):
        # Consumer requires a JSON array of strings.
        tags = [str(t) for t in tags if t not in (None, "")]
    else:
        tags = None

    # Scope is sent explicitly — the Data Platform must not infer it from
    # which IDs happen to be present.
    if study_id:
        scope = "STUDY"
    elif project_id:
        scope = "PROJECT"
    else:
        scope = "GLOBAL"

    payload = {
        "name": _first(raw, "title", "documentTitle", "name", "documentName"),
        "doc_type": _first(raw, "document_type", "documentType", "doc_type", "docType"),
        "scope": scope,
        # Already resolved to the CRM Study.id UUID (or None) by the caller.
        "study_id": study_id,
        "project_id": project_id,
        "description": _first(raw, "description"),
        "tags": tags,
        "metadata": meta,
        "source_blob": source_blob,
        "status": _first(raw, "status", default="active"),
    }
    if created_by:
        payload["created_by"] = created_by
    # Coerce ObjectId/datetime nested anywhere (e.g. inside metadata) to JSON-safe.
    return _serialize_workflow_for_response(payload)


async def route_document_to_tmf(
    *,
    db,
    document_id: str,
    study_id: Optional[str] = None,
    study_number: Optional[str] = None,
    created_by: Optional[str] = None,
) -> bool:
    """
    Publish the ISF document to the Data Platform ``platform.documents`` topic
    using the standard event envelope (``document.created``, stable ``entity_id``
    for upserts, fresh ``event_id`` per publish, ISO-8601 UTC ``timestamp``).
    Returns True on success, False otherwise (never raises).

    Args:
        db: Async MongoDB database handle (from get_database()).
        document_id: ISF document identifier (Mongo _id or business documentId).
        study_id / study_number: Optional study context (echoed onto the payload
            when the stored document does not already carry it).
        created_by: User id of whoever triggered TMF routing; omitted from the
            payload when unavailable.
    """
    doc_tuple = await isf_workflow_service._get_document(db, document_id)  # type: ignore[attr-defined]
    if not doc_tuple:
        logger.error("ISF document %s not found for TMF Kafka routing", sfmt(document_id))
        return False

    raw, _coll_name = doc_tuple

    # Resolve the study reference to the CRM Study.id UUID (falls back to the
    # study stored on the doc when the caller didn't pass one).
    study_hint = study_id or raw.get("study") or raw.get("study_id") or raw.get("studyId")
    resolved_study_id = await _resolve_study_uuid(study_hint)

    # Mapped Data Platform document payload (JSON-safe).
    payload = _build_document_payload(
        raw, study_id=resolved_study_id, created_by=created_by
    )

    # The consumer silently drops messages missing either of these.
    if not payload.get("name") or not payload.get("doc_type"):
        logger.warning(
            "ISF document %s is missing name and/or doc_type; the Data Platform "
            "will silently drop this message", sfmt(document_id),
        )

    # Stable per-document UUID: the Data Platform upserts on entity_id, so
    # re-sends and corrections MUST reuse it (never a fresh UUID per send).
    entity_id = _document_uuid(raw, document_id)

    envelope = {
        # Fresh UUID every publish — the Data Platform's dedup key.
        "event_id": str(uuid.uuid4()),
        "event_type": EVENT_TYPE,
        "entity_type": ENTITY_TYPE,
        "entity_id": entity_id,
        # Registered application key in the Data Platform's applications table.
        "source": settings.milestones_source_app,
        "timestamp": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "payload": payload,
    }

    # The producer is normally opened at startup; ensure it is connected here so
    # routing works even if only the documents flag path is exercised (idempotent).
    await start_milestones_producer()

    ok = await publish_envelope(
        envelope, topic=settings.documents_kafka_topic, key=entity_id
    )
    if ok:
        logger.info(
            "ISF document %s routed to TMF via Kafka topic %s",
            sfmt(document_id), settings.documents_kafka_topic,
        )
    else:
        logger.error(
            "ISF document %s TMF Kafka publish failed (producer unavailable?)",
            sfmt(document_id),
        )
    return ok

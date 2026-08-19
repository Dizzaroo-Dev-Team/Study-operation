"""Tests for the TMF document routing Kafka envelope (tmf_kafka_service).

Verifies the producer conforms to the Data Platform's standard event envelope:
``document.created`` event type, stable ``entity_id`` across re-sends, fresh
``event_id`` per publish, ISO-8601 UTC timestamp, explicit ``scope``, and the
consumer-side payload constraints (metadata object, tags array of strings,
no project_id without study_id).
"""
from __future__ import annotations

import re
import uuid

import pytest

from app.modules.isf.services import tmf_kafka_service as svc

STUDY_UUID = "f29f2acc-f534-4e6d-af5b-3860930b9cc1"
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def _raw_doc(**overrides) -> dict:
    doc = {
        "_id": "665f1c2b8f1b2a0012345678",
        "title": "MON-20260601064430-898499 Confirmation Letter",
        "document_type": "OTHER",
        "description": "ISF QC-validated confirmation letter routed to TMF",
        "status": "ACTIVE",
        "tags": ["isf", "tmf"],
        "custom_metadata": {"isf_document_id": "1783879546668", "site_id": "898499"},
        "file_url": "https://datasetaws.blob.core.windows.net/crm-isf-doc/doc.pdf",
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def published(monkeypatch):
    """Stub Kafka + Mongo + Azure and collect published envelopes."""
    envelopes: list[dict] = []

    async def fake_get_document(db, document_id):
        return _raw_doc(), "isf_documents"

    async def fake_start():
        return None

    async def fake_publish(envelope, *, topic, key):
        envelopes.append({"envelope": envelope, "topic": topic, "key": key})
        return True

    monkeypatch.setattr(svc.isf_workflow_service, "_get_document", fake_get_document)
    monkeypatch.setattr(svc, "start_milestones_producer", fake_start)
    monkeypatch.setattr(svc, "publish_envelope", fake_publish)
    monkeypatch.setattr(
        svc.azure_upload, "generate_sas_url", lambda name, expiry_hours: f"https://sas/{name}?sig=x"
    )
    return envelopes


async def test_envelope_conforms_to_standard_contract(published):
    ok = await svc.route_document_to_tmf(
        db=None, document_id="665f1c2b8f1b2a0012345678",
        study_id=STUDY_UUID, created_by="user-42",
    )
    assert ok is True

    env = published[0]["envelope"]
    assert env["event_type"] == "document.created"
    assert env["entity_type"] == "document"
    assert env["source"] == "study_operations"
    assert "target" not in env
    # event_id is a valid, fresh UUID; entity_id a valid stable UUID.
    uuid.UUID(env["event_id"])
    uuid.UUID(env["entity_id"])
    assert ISO_UTC_RE.match(env["timestamp"])
    # Message is keyed by the stable document id.
    assert published[0]["key"] == env["entity_id"]

    p = env["payload"]
    assert p["name"] == "MON-20260601064430-898499 Confirmation Letter"
    assert p["doc_type"] == "OTHER"
    assert p["scope"] == "STUDY"
    assert p["study_id"] == STUDY_UUID
    assert p["project_id"] is None
    assert p["tags"] == ["isf", "tmf"]
    assert isinstance(p["metadata"], dict)
    assert p["metadata"]["isf_document_id"] == "1783879546668"
    assert p["status"] == "ACTIVE"
    assert p["created_by"] == "user-42"
    assert p["source_blob"].startswith("https://sas/doc.pdf")


async def test_entity_id_stable_and_event_id_fresh_across_resends(published):
    for _ in range(2):
        assert await svc.route_document_to_tmf(
            db=None, document_id="665f1c2b8f1b2a0012345678", study_id=STUDY_UUID
        )
    first, second = (e["envelope"] for e in published)
    assert first["entity_id"] == second["entity_id"]
    assert first["event_id"] != second["event_id"]


async def test_created_by_omitted_when_unavailable(published):
    await svc.route_document_to_tmf(
        db=None, document_id="665f1c2b8f1b2a0012345678", study_id=STUDY_UUID
    )
    assert "created_by" not in published[0]["envelope"]["payload"]


def test_project_id_never_sent_without_study_id():
    payload = svc._build_document_payload(
        _raw_doc(project_id=str(uuid.uuid4())), study_id=None
    )
    assert payload["project_id"] is None
    assert payload["scope"] == "GLOBAL"


def test_scope_study_when_study_id_present():
    payload = svc._build_document_payload(_raw_doc(), study_id=STUDY_UUID)
    assert payload["scope"] == "STUDY"


def test_tags_coerced_to_array_of_strings_and_metadata_is_object():
    payload = svc._build_document_payload(
        _raw_doc(tags=["isf", 7, None], custom_metadata="not-a-dict"),
        study_id=STUDY_UUID,
    )
    assert payload["tags"] == ["isf", "7"]
    assert payload["metadata"] == {}


async def test_publish_failure_returns_false_without_raising(monkeypatch):
    async def fake_get_document(db, document_id):
        return _raw_doc(), "isf_documents"

    async def fake_start():
        return None

    async def failing_publish(envelope, *, topic, key):
        return False

    monkeypatch.setattr(svc.isf_workflow_service, "_get_document", fake_get_document)
    monkeypatch.setattr(svc, "start_milestones_producer", fake_start)
    monkeypatch.setattr(svc, "publish_envelope", failing_publish)
    monkeypatch.setattr(
        svc.azure_upload, "generate_sas_url", lambda name, expiry_hours: None
    )

    ok = await svc.route_document_to_tmf(
        db=None, document_id="665f1c2b8f1b2a0012345678", study_id=STUDY_UUID
    )
    assert ok is False

"""Route-level tests for the monitoring tab API (/api/monitor/*)."""
from __future__ import annotations


def test_dashboard_requires_authentication(monitor_client_anonymous):
    client, _ = monitor_client_anonymous
    response = client.get("/api/monitor/dashboard")
    assert response.status_code == 401


def test_dashboard_returns_paginated_shape(monitor_client):
    client, db = monitor_client
    db.seed_visit("MON-TEST-001")

    response = client.get("/api/monitor/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "items" in body
    assert "visits" in body
    assert "findings" in body
    assert "summary" in body
    assert body["total"] >= 1
    assert any(v["id"] == "MON-TEST-001" for v in body["items"])


def test_tables_status_lists_required_monitor_tables(monitor_client):
    client, _ = monitor_client
    response = client.get("/api/monitor/tables/status")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "monitoring_visits" in body["required_tables"]
    assert "monitoring_visit_reports" in body["required_tables"]
    assert body["missing_tables"] == []


def test_notifications_endpoint_returns_list(monitor_client, monkeypatch):
    client, db = monitor_client

    class _SessionCtx:
        def __init__(self, session_db):
            self._session_db = session_db

        async def __aenter__(self):
            return self._session_db

        async def __aexit__(self, *args):
            return None

    monkeypatch.setattr(
        "app.modules.monitoring.routes.dashboard.AsyncSessionLocal",
        lambda: _SessionCtx(db),
    )

    response = client.get("/api/monitor/notifications")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body["notifications"], list)
    assert "unread_count" in body


def test_visit_overview_not_found(monitor_client):
    client, _ = monitor_client
    response = client.get("/api/monitor/visits/MON-MISSING/overview")
    assert response.status_code == 404


def test_visit_overview_returns_expected_sections(monitor_client):
    client, db = monitor_client
    db.seed_visit("MON-OVERVIEW-1")

    response = client.get("/api/monitor/visits/MON-OVERVIEW-1/overview")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["visitDetails"]["visitType"] == "On-Site Monitoring"
    assert "siteContact" in body
    assert "sdvProgress" in body
    assert "objectives" in body
    assert "recentActivity" in body


def test_delete_visit_not_found(monitor_client):
    client, _ = monitor_client
    response = client.delete("/api/monitor/visits/MON-MISSING")
    assert response.status_code == 404


def test_delete_visit_success(monitor_client):
    client, db = monitor_client
    db.seed_visit("MON-DEL-1")

    response = client.delete("/api/monitor/visits/MON-DEL-1")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "deleted"
    assert "MON-DEL-1" not in db.visits
    assert db.committed is True


def test_visit_report_roundtrip_with_question_comments(monitor_client):
    client, db = monitor_client
    visit_id = "MON-REPORT-1"
    db.seed_visit(visit_id)

    empty = client.get(f"/api/monitor/visits/{visit_id}/visit-report")
    assert empty.status_code == 200, empty.text
    assert empty.json()["payload"] == {}

    payload = {
        "schemaVersion": 1,
        "q401": "Yes",
        "questionComments": {
            "q401Comment": "Site staff briefed on protocol amendments.",
            "q402Comment": "",
        },
    }
    save = client.put(
        f"/api/monitor/visits/{visit_id}/visit-report",
        json={"payload": payload},
    )
    assert save.status_code == 200, save.text
    assert save.json()["status"] == "saved"
    assert db.committed is True

    loaded = client.get(f"/api/monitor/visits/{visit_id}/visit-report")
    assert loaded.status_code == 200, loaded.text
    stored = loaded.json()["payload"]
    assert stored["q401"] == "Yes"
    assert stored["questionComments"]["q401Comment"] == "Site staff briefed on protocol amendments."


def test_create_visit_returns_scheduled_row(monitor_client, monkeypatch):
    client, db = monitor_client

    async def _resolve_site(db, **kwargs):
        return "SITE-RESOLVED"

    async def _resolve_study(db, **kwargs):
        return "STUDY-RESOLVED"

    monkeypatch.setattr(
        "app.modules.monitoring.routes.visits.resolve_monitor_site_id",
        _resolve_site,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.visits.resolve_monitor_study_id",
        _resolve_study,
    )

    response = client.post(
        "/api/monitor/visits",
        json={
            "site": "Test Site",
            "study": "Test Study",
            "cra": "CRA One",
            "type": "On-Site Monitoring",
            "date": "2026-06-15",
            "priority": "High",
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "Scheduled"
    assert body["site_id"] == "SITE-RESOLVED"
    assert body["study_id"] == "STUDY-RESOLVED"
    assert body["id"].startswith("MON-")
    assert body["id"] in db.visits

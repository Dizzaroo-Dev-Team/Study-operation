"""Shared fixtures for monitoring API route tests."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user_optional
from app.db import get_db
from app.modules.monitoring.aggregator import router as monitor_router


class FakeMappingsResult:
    def __init__(self, rows: Optional[List[Dict[str, Any]]] = None):
        self._rows = rows or []

    def mappings(self) -> "FakeMappingsResult":
        return self

    def first(self) -> Optional[Dict[str, Any]]:
        return self._rows[0] if self._rows else None

    def all(self) -> List[Dict[str, Any]]:
        return list(self._rows)

    def fetchall(self) -> List[Any]:
        return list(self._rows)

    def __iter__(self):
        return iter(self._rows)


class FakeScalarResult:
    def __init__(self, value: Any = None, rowcount: int = 0):
        self._value = value
        self.rowcount = rowcount

    def scalar(self) -> Any:
        return self._value

    def scalar_one_or_none(self) -> Any:
        return self._value

    def mappings(self) -> FakeMappingsResult:
        if isinstance(self._value, list):
            return FakeMappingsResult(self._value)
        if isinstance(self._value, dict):
            return FakeMappingsResult([self._value])
        return FakeMappingsResult()


class MonitorFakeDB:
    """Minimal in-memory stand-in for monitoring SQL executed in route tests."""

    def __init__(self) -> None:
        self.visits: Dict[str, Dict[str, Any]] = {}
        self.visit_reports: Dict[str, Dict[str, Any]] = {}
        self.objectives: Dict[str, List[Dict[str, Any]]] = {}
        self.activity: Dict[str, List[Dict[str, Any]]] = {}
        self.committed = False

    def seed_visit(self, visit_id: str, **fields: Any) -> None:
        now = datetime.now(timezone.utc)
        self.visits[visit_id] = {
            "id": visit_id,
            "site_id": "SITE-001",
            "study_id": "STUDY-001",
            "cra_name": "CRA Test",
            "status": "Scheduled",
            "visit_type": "On-Site Monitoring",
            "visit_date": "Apr 28, 2026",
            "visit_date_iso": "2026-04-28T09:00:00+00:00",
            "visit_end_date": "",
            "visit_end_date_iso": "",
            "duration": "Full Day (8 hours)",
            "estimated_duration_days": None,
            "protocol": "Test Protocol",
            "ind_number": "N/A",
            "sponsor": "N/A",
            "risk_level": "Medium",
            "priority": "Medium",
            "principal_investigator": "Dr. Test",
            "pi_email": "",
            "study_coordinator": "Coordinator",
            "coordinator_phone": "",
            "site_address": "123 Test St",
            "irb_approval": "N/A",
            "sdv_verified_subjects": 0,
            "sdv_total_subjects": 0,
            "subjects_enrolled": "0 / 0",
            "crf_completion": "0%",
            "query_rate": "0%",
            "last_sdv_date": "",
            "action_required_count": 0,
            "site_visit_number": 1,
            "updated_at": now,
            "closed_at": None,
            **fields,
        }
        self.objectives.setdefault(visit_id, [])
        self.activity.setdefault(visit_id, [])

    async def execute(self, query: Any, params: Optional[Dict[str, Any]] = None) -> Any:
        sql = str(query).lower()
        params = params or {}

        if "information_schema.tables" in sql:
            return FakeScalarResult(True)

        if "delete from monitoring_visits" in sql:
            vid = params.get("visit_id")
            if vid in self.visits:
                del self.visits[vid]
                return FakeScalarResult(rowcount=1)
            return FakeScalarResult(rowcount=0)

        if "select 1 from monitoring_visits" in sql:
            vid = params.get("visit_id")
            return FakeScalarResult(1 if vid in self.visits else None)

        if "select * from monitoring_visits" in sql:
            vid = params.get("visit_id")
            row = self.visits.get(vid)
            return FakeMappingsResult([row] if row else [])

        if "select payload" in sql and "monitoring_visit_reports" in sql:
            vid = params.get("visit_id")
            stored = self.visit_reports.get(vid)
            if not stored:
                return FakeMappingsResult([])
            return FakeMappingsResult(
                [{"payload": stored["payload"], "updated_at": stored.get("updated_at")}]
            )

        if "insert into monitoring_visit_reports" in sql:
            vid = params.get("visit_id")
            raw = params.get("payload_json")
            payload = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            self.visit_reports[vid] = {
                "payload": payload,
                "updated_at": datetime.now(timezone.utc),
            }
            return FakeScalarResult(rowcount=1)

        if "count(*) as c from monitoring_visit_objectives" in sql:
            vid = params.get("visit_id")
            count = len(self.objectives.get(vid, []))
            return FakeMappingsResult([{"c": count}])

        if "from monitoring_visit_objectives" in sql and "select id" in sql:
            vid = params.get("visit_id")
            rows = self.objectives.get(vid, [])
            return FakeMappingsResult(
                [
                    {
                        "id": r["id"],
                        "objective_text": r["text"],
                        "done": r["done"],
                        "tag_type": r.get("tagType"),
                    }
                    for r in rows
                ]
            )

        if "from monitoring_visit_activity" in sql:
            vid = params.get("visit_id")
            rows = self.activity.get(vid, [])
            return FakeMappingsResult(
                [
                    {
                        "initials": r.get("initials", "CR"),
                        "color": r.get("color", "#3b82f6"),
                        "activity_text": r.get("text", ""),
                        "activity_time": r.get("time", ""),
                        "created_at": r.get("created_at", datetime.now(timezone.utc)),
                    }
                    for r in rows
                ]
            )

        if "count(*)" in sql and "from monitoring_visits" in sql:
            return FakeScalarResult(len(self.visits))

        if "from monitoring_visits" in sql and "limit" in sql:
            rows = []
            for v in self.visits.values():
                rows.append(
                    {
                        "id": v["id"],
                        "site_id": v.get("site_id"),
                        "study_id": v.get("study_id"),
                        "cra_name": v.get("cra_name"),
                        "status": v.get("status"),
                        "closed_at": v.get("closed_at"),
                        "visit_type": v.get("visit_type"),
                        "risk_level": v.get("risk_level"),
                        "visit_date": v.get("visit_date"),
                        "visit_date_iso": v.get("visit_date_iso"),
                        "visit_end_date": v.get("visit_end_date"),
                        "visit_end_date_iso": v.get("visit_end_date_iso"),
                        "priority": v.get("priority"),
                        "estimated_duration_days": v.get("estimated_duration_days"),
                        "site_visit_number": v.get("site_visit_number"),
                        "site_name": v.get("site_id", "Unknown Site"),
                        "study_name": v.get("study_id", "Unknown Study"),
                        "open_findings": 0,
                    }
                )
            return FakeMappingsResult(rows)

        if "from monitoring_findings" in sql:
            return FakeMappingsResult([])

        if "insert into monitoring_visits" in sql:
            vid = params.get("id")
            if vid:
                self.seed_visit(
                    vid,
                    site_id=params.get("site_id"),
                    study_id=params.get("study_id"),
                    cra_name=params.get("cra_name"),
                    status=params.get("status"),
                    visit_type=params.get("visit_type"),
                    visit_date=params.get("visit_date"),
                    visit_date_iso=params.get("visit_date_iso"),
                    site_visit_number=params.get("site_visit_number"),
                )
            return FakeScalarResult(rowcount=1)

        return FakeMappingsResult([])

    async def commit(self) -> None:
        self.committed = True


@pytest.fixture
def monitor_fake_db() -> MonitorFakeDB:
    return MonitorFakeDB()


@pytest.fixture
def monitor_client(monkeypatch, monitor_fake_db: MonitorFakeDB):
    async def _noop_ensure_tables(db: Any) -> None:
        return None

    async def _noop_sync_objectives(db: Any, visit_id: str) -> None:
        return None

    async def _noop_sync_checklist(db: Any, visit_id: str, visit_type: str, **kwargs: Any) -> None:
        return None

    async def _noop_lock(db: Any, bucket: str) -> None:
        return None

    async def _next_seq(db: Any, bucket: str) -> int:
        return 1

    async def _noop_template(db: Any, org: str) -> None:
        return None

    async def _noop_append(db: Any, visit_id: str, text: str, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(
        "app.modules.monitoring.aggregator._ensure_monitor_tables",
        _noop_ensure_tables,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.dashboard._ensure_monitor_tables",
        _noop_ensure_tables,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.visits._ensure_monitor_tables",
        _noop_ensure_tables,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.post_visit_and_report._ensure_monitor_tables",
        _noop_ensure_tables,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.visits._sync_visit_objectives",
        _noop_sync_objectives,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.visits._sync_pre_visit_checklist",
        _noop_sync_checklist,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.visits._monitor_pg_advisory_lock_site_bucket",
        _noop_lock,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.visits._next_site_visit_sequence",
        _next_seq,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.post_visit_and_report._fetch_active_mvr_template_row",
        _noop_template,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.visits._append_visit_activity",
        _noop_append,
    )

    app = FastAPI()
    app.include_router(monitor_router)

    async def _user():
        return {"user_id": "u-test", "email": "cra@test.com", "name": "CRA Test"}

    async def _db():
        yield monitor_fake_db

    app.dependency_overrides[get_current_user_optional] = _user
    app.dependency_overrides[get_db] = _db
    return TestClient(app), monitor_fake_db


@pytest.fixture
def monitor_client_anonymous(monkeypatch, monitor_fake_db: MonitorFakeDB):
    async def _noop_ensure_tables(db: Any) -> None:
        return None

    monkeypatch.setattr(
        "app.modules.monitoring.aggregator._ensure_monitor_tables",
        _noop_ensure_tables,
    )
    monkeypatch.setattr(
        "app.modules.monitoring.routes.dashboard._ensure_monitor_tables",
        _noop_ensure_tables,
    )

    app = FastAPI()
    app.include_router(monitor_router)

    async def _no_user():
        return None

    async def _db():
        yield monitor_fake_db

    app.dependency_overrides[get_current_user_optional] = _no_user
    app.dependency_overrides[get_db] = _db
    return TestClient(app), monitor_fake_db

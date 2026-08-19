"""End-to-end tests for the visit report template + review lifecycle.

Covers both template modes (built-in/legacy "default" reports and custom MVR
templates) through the full workflow: draft → submit-for-review → reviewer
annotate → reject → author revise/reply → resubmit → approve, asserting at
each step that the report keeps rendering the template it was authored with
and never silently degrades to (or leaks) the live org template.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import get_current_user_optional
from app.db import get_db
from app.modules.monitoring.aggregator import router as monitor_router

from conftest import FakeMappingsResult, FakeScalarResult, MonitorFakeDB


# ── Extended fake DB with template / token / comment tables ──────────────────

class ReviewFakeDB(MonitorFakeDB):
    def __init__(self) -> None:
        super().__init__()
        self.templates: Dict[str, Dict[str, Any]] = {}
        self.tokens: Dict[str, Dict[str, Any]] = {}  # keyed by token value
        self.comments: Dict[str, Dict[str, Any]] = {}  # keyed by comment id
        self._clock = datetime.now(timezone.utc)

    def _tick(self) -> datetime:
        # Strictly increasing timestamps so "latest token" ordering is stable.
        self._clock = self._clock + timedelta(seconds=1)
        return self._clock

    def seed_template(
        self,
        template_id: str,
        *,
        name: str = "Custom MVR",
        schema: Optional[Dict[str, Any]] = None,
        version: int = 1,
        is_active: bool = False,
        lifecycle_status: str = "published",
        organization_id: str = "default",
    ) -> None:
        self.templates[template_id] = {
            "id": template_id,
            "organization_id": organization_id,
            "name": name,
            "schema": schema or {"fields": []},
            "version": version,
            "is_active": is_active,
            "lifecycle_status": lifecycle_status,
            "updated_at": self._tick(),
        }

    def latest_token_id(self, visit_id: str) -> Optional[str]:
        rows = [t for t in self.tokens.values() if t["visit_id"] == visit_id]
        if not rows:
            return None
        return max(rows, key=lambda t: t["created_at"])["id"]

    async def execute(self, query: Any, params: Optional[Dict[str, Any]] = None) -> Any:
        sql = " ".join(str(query).lower().split())
        params = params or {}

        # ── MVR templates ────────────────────────────────────────────────
        if "monitoring_mvr_templates" in sql:
            if sql.startswith("insert"):
                self.templates[params["id"]] = {
                    "id": params["id"],
                    "organization_id": params.get("oid", "default"),
                    "name": params.get("name", ""),
                    "schema": json.loads(params["schema"]) if isinstance(params.get("schema"), str) else (params.get("schema") or {}),
                    "version": int(params.get("version") or 1),
                    "is_active": bool(params.get("active", False)),
                    "lifecycle_status": params.get("lifecycle", "draft"),
                    "updated_at": self._tick(),
                }
                return FakeScalarResult(rowcount=1)
            if "coalesce(max(version)" in sql:
                oid = params.get("oid")
                versions = [t["version"] for t in self.templates.values() if t["organization_id"] == oid]
                return FakeMappingsResult([{"mv": max(versions) if versions else 0}])
            if sql.startswith("delete"):
                tid = params.get("id")
                existed = tid in self.templates
                if existed:
                    del self.templates[tid]
                return FakeScalarResult(rowcount=1 if existed else 0)
            if "is_active = true" in sql and "lifecycle_status = 'published'" in sql:
                oid = params.get("oid", "default")
                rows = [
                    dict(t)
                    for t in self.templates.values()
                    if t["organization_id"] == oid and t["is_active"] and t["lifecycle_status"] == "published"
                ]
                rows.sort(key=lambda t: t["version"], reverse=True)
                return FakeMappingsResult(rows[:1])
            if "where id = :id" in sql:
                row = self.templates.get(str(params.get("id", "")).strip())
                return FakeMappingsResult([dict(row)] if row else [])
            if "where organization_id = :oid" in sql:
                oid = params.get("oid", "default")
                rows = [dict(t) for t in self.templates.values() if t["organization_id"] == oid]
                return FakeMappingsResult(rows)
            return FakeMappingsResult([])

        # ── Review tokens ────────────────────────────────────────────────
        if "monitoring_visit_review_tokens" in sql and "monitoring_visit_review_comments" not in sql:
            if sql.startswith("insert"):
                self.tokens[params["token"]] = {
                    "id": params["id"],
                    "visit_id": params["visit_id"],
                    "token": params["token"],
                    "reviewer_email": params.get("reviewer_email", ""),
                    "author_email": params.get("author_email", ""),
                    "message": params.get("message", ""),
                    "is_valid": True,
                    "created_at": self._tick(),
                }
                return FakeScalarResult(rowcount=1)
            if "set is_valid = false" in sql and "where visit_id" in sql:
                for t in self.tokens.values():
                    if t["visit_id"] == params.get("visit_id"):
                        t["is_valid"] = False
                return FakeScalarResult(rowcount=1)
            if "set is_valid = false" in sql and "where token" in sql:
                t = self.tokens.get(params.get("token"))
                if t:
                    t["is_valid"] = False
                return FakeScalarResult(rowcount=1 if t else 0)
            if "where token = :token" in sql:
                t = self.tokens.get(params.get("token"))
                if t and t["visit_id"] == params.get("visit_id"):
                    return FakeMappingsResult([dict(t)])
                return FakeMappingsResult([])
            return FakeMappingsResult([])

        # ── Review comments ──────────────────────────────────────────────
        if "monitoring_visit_review_comments" in sql:
            if sql.startswith("insert"):
                self.comments[params["id"]] = {
                    "id": params["id"],
                    "visit_id": params["visit_id"],
                    "token_id": params["token_id"],
                    "highlighted_text": params.get("highlighted_text", ""),
                    "dom_path": params.get("dom_path", ""),
                    "start_offset": params.get("start_offset", 0),
                    "end_offset": params.get("end_offset", 0),
                    "comment_text": params.get("comment_text", ""),
                    "author_reply": None,
                    "author_reply_at": None,
                    "created_at": self._tick(),
                    "updated_at": self._tick(),
                }
                return FakeScalarResult(rowcount=1)
            if sql.startswith("update") and "author_reply" in sql:
                cmt = self.comments.get(params.get("comment_id"))
                if not cmt or cmt["visit_id"] != params.get("visit_id"):
                    return FakeMappingsResult([])
                cmt["author_reply"] = params.get("author_reply")
                cmt["author_reply_at"] = self._tick()
                cmt["updated_at"] = self._tick()
                return FakeMappingsResult([dict(cmt)])
            if sql.startswith("update") and "comment_text" in sql:
                cmt = self.comments.get(params.get("comment_id"))
                if not cmt or cmt["visit_id"] != params.get("visit_id"):
                    return FakeScalarResult(rowcount=0)
                cmt["comment_text"] = params.get("comment_text")
                cmt["updated_at"] = self._tick()
                return FakeScalarResult(rowcount=1)
            if sql.startswith("delete"):
                cmt = self.comments.get(params.get("comment_id"))
                if not cmt or cmt["visit_id"] != params.get("visit_id"):
                    return FakeScalarResult(rowcount=0)
                del self.comments[params["comment_id"]]
                return FakeScalarResult(rowcount=1)
            # Latest-round scoped SELECT used by _get_review_comments.
            visit_id = params.get("visit_id")
            latest = self.latest_token_id(visit_id)
            rows = [
                dict(c)
                for c in self.comments.values()
                if c["visit_id"] == visit_id and c["token_id"] == latest
            ]
            rows.sort(key=lambda c: c["created_at"])
            return FakeMappingsResult(rows)

        # ── Visit report writes not covered by base fake ─────────────────
        if "insert into monitoring_visit_reports" in sql and "payload_json" not in sql:
            raw = params.get("payload")
            payload = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            self.visit_reports[params["visit_id"]] = {
                "payload": payload,
                "updated_at": self._tick(),
            }
            return FakeScalarResult(rowcount=1)
        if sql.startswith("update monitoring_visit_reports"):
            raw = params.get("payload")
            payload = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
            self.visit_reports[params["visit_id"]] = {
                "payload": payload,
                "updated_at": self._tick(),
            }
            return FakeScalarResult(rowcount=1)

        if "select site_visit_number from monitoring_visits" in sql:
            v = self.visits.get(params.get("visit_id"))
            return FakeMappingsResult(
                [{"site_visit_number": v.get("site_visit_number")}] if v else []
            )

        return await super().execute(query, params)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def review_db() -> ReviewFakeDB:
    return ReviewFakeDB()


@pytest.fixture
def review_client(monkeypatch, review_db: ReviewFakeDB):
    async def _noop_ensure(db: Any) -> None:
        return None

    for target in (
        "app.modules.monitoring.aggregator._ensure_monitor_tables",
        "app.modules.monitoring.routes.visit_report_review._ensure_monitor_tables",
        "app.modules.monitoring.routes.post_visit_and_report._ensure_monitor_tables",
    ):
        monkeypatch.setattr(target, _noop_ensure)

    sent_emails: List[Dict[str, Any]] = []

    def _capture_email(**kwargs: Any) -> None:
        sent_emails.append(kwargs)

    monkeypatch.setattr(
        "app.modules.monitoring.routes.visit_report_review.enqueue_email",
        _capture_email,
    )

    app = FastAPI()
    app.include_router(monitor_router)

    async def _user():
        return {"user_id": "u-test", "email": "cra@test.com", "name": "CRA Test"}

    async def _db():
        yield review_db

    app.dependency_overrides[get_current_user_optional] = _user
    app.dependency_overrides[get_db] = _db
    return TestClient(app), review_db, sent_emails


# ── Schema helpers ────────────────────────────────────────────────────────────

def custom_schema() -> Dict[str, Any]:
    return {
        "fields": [
            {"id": "sec_a", "type": "section", "label": "Section A"},
            {"id": "f_summary", "type": "textarea", "label": "Summary"},
            {"id": "f_rating", "type": "text", "label": "Rating"},
            {"id": "sec_b", "type": "section", "label": "Section B"},
            {"id": "f_issues", "type": "textarea", "label": "Issues"},
        ]
    }


def other_schema() -> Dict[str, Any]:
    return {
        "fields": [
            {"id": "g_one", "type": "text", "label": "G One"},
            {"id": "g_two", "type": "text", "label": "G Two"},
        ]
    }


CUSTOM_TID = "tpl-custom-1"
OTHER_TID = "tpl-other-2"
VISIT = "MON-RPT-1"


def seed_custom_report(db: ReviewFakeDB, *, status: str = "Draft", snapshot: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "schemaVersion": 1,
        "reportStatus": status,
        "templateId": CUSTOM_TID,
        "templateVersion": 1,
        "submissionData": {"f_summary": "All good", "f_rating": "Satisfactory"},
    }
    if snapshot:
        payload["templateSnapshot"] = {
            "id": CUSTOM_TID,
            "name": "Custom MVR",
            "version": 1,
            "schema": custom_schema(),
        }
    db.visit_reports[VISIT] = {"payload": payload, "updated_at": datetime.now(timezone.utc)}
    return payload


def submit_for_review(client: TestClient, visit_id: str = VISIT) -> str:
    res = client.post(
        f"/api/monitor/visits/{visit_id}/visit-report/submit-for-review",
        json={"reviewer_email": "sponsor@test.com", "author_email": "cra@test.com", "message": "please review"},
    )
    assert res.status_code == 200, res.text
    return res.json()["review_url"].split("token=")[1]


# ══════════════════════════════════════════════════════════════════════════════
# Draft behavior: which template is served / how drafts follow the live one
# ══════════════════════════════════════════════════════════════════════════════

def test_draft_gets_live_custom_template(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["activeTemplate"]["id"] == CUSTOM_TID
    assert body["activeTemplate"]["schema"] == custom_schema()
    assert body["templateSynced"] is False


def test_draft_with_no_live_template_uses_builtin(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report")
    assert res.status_code == 200
    assert res.json()["activeTemplate"] is None  # frontend falls back to built-in form


def test_draft_resyncs_when_live_template_changes(review_client):
    """Drafts (only) follow the live template; removed fields are archived, not lost."""
    client, db, _ = review_client
    db.seed_visit(VISIT)
    seed_custom_report(db, status="Draft")
    db.seed_template(OTHER_TID, schema=other_schema(), version=2, is_active=True)

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report")
    body = res.json()
    assert body["templateSynced"] is True
    payload = body["payload"]
    assert payload["templateId"] == OTHER_TID
    assert payload["submissionData"] == {}  # custom fields not in new template
    assert payload["archivedData"]["f_summary"] == "All good"  # preserved, not deleted


def test_legacy_freeform_draft_is_never_force_synced(review_client):
    """A report with no templateId must not be archived just because a live template exists."""
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.visit_reports[VISIT] = {
        "payload": {"schemaVersion": 1, "reportStatus": "Draft", "summary": "legacy text", "q401": "Yes"},
        "updated_at": datetime.now(timezone.utc),
    }
    db.seed_template(OTHER_TID, schema=other_schema(), is_active=True)

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report")
    body = res.json()
    assert body["templateSynced"] is False
    assert body["payload"]["summary"] == "legacy text"
    assert "archivedData" not in body["payload"]


# ══════════════════════════════════════════════════════════════════════════════
# Submit for review: template freezing + token + email
# ══════════════════════════════════════════════════════════════════════════════

def test_submit_freezes_custom_template_and_creates_token(review_client):
    client, db, emails = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db, status="Draft")

    token = submit_for_review(client)

    stored = db.visit_reports[VISIT]["payload"]
    assert stored["reportStatus"] == "In Review"
    snap = stored["templateSnapshot"]
    assert snap["id"] == CUSTOM_TID
    assert snap["schema"] == custom_schema()  # full schema, not filtered

    tok = db.tokens[token]
    assert tok["is_valid"] is True
    assert tok["reviewer_email"] == "sponsor@test.com"
    assert len(emails) == 1 and emails[0]["to"] == "sponsor@test.com"


def test_submit_preserves_existing_snapshot_on_resubmit(review_client):
    """Resubmit must not refreeze from the live row — the author revised against the snapshot."""
    client, db, _ = review_client
    db.seed_visit(VISIT)
    seed_custom_report(db, status="Rejected", snapshot=True)
    # The template row was edited in place since the snapshot was taken.
    edited = custom_schema()
    edited["fields"].append({"id": "f_new", "type": "text", "label": "Added later"})
    db.seed_template(CUSTOM_TID, schema=edited, is_active=True)

    submit_for_review(client)

    snap = db.visit_reports[VISIT]["payload"]["templateSnapshot"]
    assert snap["schema"] == custom_schema()  # original snapshot kept
    assert all(f["id"] != "f_new" for f in snap["schema"]["fields"])


def test_submit_with_deleted_template_never_freezes_full_live_template(review_client):
    """templateId row gone → snapshot is derived and filtered to the report's own fields."""
    client, db, _ = review_client
    db.seed_visit(VISIT)
    payload = seed_custom_report(db, status="Draft")
    payload["templateId"] = "tpl-deleted"
    # A different live template exists with fields the report never used.
    live = {
        "fields": [
            {"id": "f_summary", "type": "text", "label": "Summary"},
            {"id": "g_unrelated", "type": "text", "label": "Unrelated"},
        ]
    }
    db.seed_template(OTHER_TID, schema=live, is_active=True)

    submit_for_review(client)

    snap = db.visit_reports[VISIT]["payload"]["templateSnapshot"]
    ids = [f["id"] for f in snap["schema"]["fields"]]
    assert "f_summary" in ids  # field with data survives
    assert "g_unrelated" not in ids  # live-only field never leaks into the frozen report


def test_submit_legacy_report_snapshot_filters_live_template(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.visit_reports[VISIT] = {
        "payload": {"schemaVersion": 1, "reportStatus": "Draft", "summary": "legacy", "q401": "Yes"},
        "updated_at": datetime.now(timezone.utc),
    }
    db.seed_template(OTHER_TID, schema=other_schema(), is_active=True)

    submit_for_review(client)

    snap = db.visit_reports[VISIT]["payload"].get("templateSnapshot")
    if snap is not None:
        ids = [f["id"] for f in snap["schema"]["fields"]]
        assert "g_one" not in ids and "g_two" not in ids


def test_submit_invalidates_previous_tokens(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)

    token1 = submit_for_review(client)
    token2 = submit_for_review(client)
    assert db.tokens[token1]["is_valid"] is False
    assert db.tokens[token2]["is_valid"] is True


# ══════════════════════════════════════════════════════════════════════════════
# Reviewer view (public link)
# ══════════════════════════════════════════════════════════════════════════════

def test_reviewer_sees_frozen_custom_template(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    token = submit_for_review(client)

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report/review", params={"token": token})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["template"]["id"] == CUSTOM_TID
    assert body["template"]["schema"] == custom_schema()
    assert body["payload"]["submissionData"]["f_summary"] == "All good"
    assert body["reviewer_email"] == "sponsor@test.com"
    assert body["message"] == "please review"


def test_reviewer_template_snapshot_wins_over_live_edits(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    token = submit_for_review(client)

    # Org edits the template after submission.
    edited = custom_schema()
    edited["fields"][1]["label"] = "Summary (renamed)"
    db.templates[CUSTOM_TID]["schema"] = edited

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report/review", params={"token": token})
    labels = [f["label"] for f in res.json()["template"]["schema"]["fields"]]
    assert "Summary" in labels and "Summary (renamed)" not in labels


def test_reviewer_view_with_deleted_template_and_no_snapshot(review_client):
    """Older in-flight reports: template row deleted, no snapshot → derived, not None/live."""
    client, db, _ = review_client
    db.seed_visit(VISIT)
    payload = seed_custom_report(db, status="In Review")
    db.tokens["tok-x"] = {
        "id": "tokid-x", "visit_id": VISIT, "token": "tok-x",
        "reviewer_email": "sponsor@test.com", "author_email": "", "message": "",
        "is_valid": True, "created_at": datetime.now(timezone.utc),
    }
    live = {
        "fields": [
            {"id": "f_summary", "type": "text", "label": "Summary"},
            {"id": "g_extra", "type": "text", "label": "Extra"},
        ]
    }
    db.seed_template(OTHER_TID, schema=live, is_active=True)
    assert payload["templateId"] == CUSTOM_TID and CUSTOM_TID not in db.templates

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report/review", params={"token": "tok-x"})
    body = res.json()
    assert body["template"] is not None
    ids = [f["id"] for f in body["template"]["schema"]["fields"]]
    assert "g_extra" not in ids


def test_reviewer_link_invalid_or_used(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    seed_custom_report(db)

    missing = client.get(f"/api/monitor/visits/{VISIT}/visit-report/review", params={"token": "nope"})
    assert missing.status_code == 404

    db.tokens["dead"] = {
        "id": "tokid-d", "visit_id": VISIT, "token": "dead",
        "reviewer_email": "", "author_email": "", "message": "",
        "is_valid": False, "created_at": datetime.now(timezone.utc),
    }
    used = client.get(f"/api/monitor/visits/{VISIT}/visit-report/review", params={"token": "dead"})
    assert used.status_code == 410


# ══════════════════════════════════════════════════════════════════════════════
# Inline comments (reviewer) + author replies
# ══════════════════════════════════════════════════════════════════════════════

def test_reviewer_comment_crud_and_latest_round_scoping(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    token1 = submit_for_review(client)

    save = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/comments",
        json={"token": token1, "highlighted_text": "All good", "dom_path": "#f_summary",
              "start_offset": 0, "end_offset": 8, "comment_text": "Too vague"},
    )
    assert save.status_code == 200, save.text
    comment_id = save.json()["id"]

    upd = client.patch(
        f"/api/monitor/visits/{VISIT}/visit-report/review/comments/{comment_id}",
        json={"token": token1, "comment_text": "Please quantify findings"},
    )
    assert upd.status_code == 200

    listed = client.get(f"/api/monitor/visits/{VISIT}/visit-report/comments").json()["comments"]
    assert len(listed) == 1
    assert listed[0]["comment_text"] == "Please quantify findings"

    # New review round → previous round's comments are no longer actionable.
    submit_for_review(client)
    listed2 = client.get(f"/api/monitor/visits/{VISIT}/visit-report/comments").json()["comments"]
    assert listed2 == []


def test_author_reply_only_allowed_while_rejected(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    token = submit_for_review(client)

    cid = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/comments",
        json={"token": token, "highlighted_text": "x", "comment_text": "fix this"},
    ).json()["id"]

    # Still In Review → replies blocked.
    blocked = client.patch(
        f"/api/monitor/visits/{VISIT}/visit-report/comments/{cid}/reply",
        json={"author_reply": "will do"},
    )
    assert blocked.status_code == 400

    rej = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/reject",
        json={"token": token, "reason": "needs detail"},
    )
    assert rej.status_code == 200

    ok = client.patch(
        f"/api/monitor/visits/{VISIT}/visit-report/comments/{cid}/reply",
        json={"author_reply": "Addressed in section A"},
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["comment"]["author_reply"] == "Addressed in section A"


# ══════════════════════════════════════════════════════════════════════════════
# Rejection
# ══════════════════════════════════════════════════════════════════════════════

def test_reject_requires_reason(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    seed_custom_report(db)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    token = submit_for_review(client)

    res = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/reject",
        json={"token": token},
    )
    assert res.status_code == 400


def test_reject_sets_status_reason_baseline_and_invalidates_token(review_client):
    client, db, emails = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    token = submit_for_review(client)
    emails.clear()

    res = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/reject",
        json={"token": token, "reason": "Numbers missing in Section A"},
    )
    assert res.status_code == 200
    stored = db.visit_reports[VISIT]["payload"]
    assert stored["reportStatus"] == "Rejected"
    assert stored["rejectionReason"] == "Numbers missing in Section A"
    baseline = stored["revisionBaseline"]
    assert baseline["submissionData"]["f_summary"] == "All good"
    assert stored["templateSnapshot"]["id"] == CUSTOM_TID  # snapshot survives rejection

    assert db.tokens[token]["is_valid"] is False
    again = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/reject",
        json={"token": token, "reason": "twice"},
    )
    assert again.status_code == 410

    assert len(emails) == 1 and emails[0]["to"] == "cra@test.com"  # author notified


def test_rejected_report_keeps_custom_template_for_author(review_client):
    """THE original bug: after rejection the author must still see the custom template."""
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    token = submit_for_review(client)
    client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/reject",
        json={"token": token, "reason": "revise"},
    )

    # Worst case: a DIFFERENT template is live when the author reopens the report.
    db.templates[CUSTOM_TID]["is_active"] = False
    db.seed_template(OTHER_TID, schema=other_schema(), version=2, is_active=True)

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report")
    body = res.json()
    assert body["templateSynced"] is False  # rejected reports never re-sync
    assert body["activeTemplate"]["id"] == CUSTOM_TID  # frozen template served
    assert body["activeTemplate"]["schema"] == custom_schema()
    payload = body["payload"]
    assert payload["templateId"] == CUSTOM_TID  # not swapped to the live template
    assert payload["submissionData"]["f_summary"] == "All good"  # nothing archived


def test_saving_rejected_report_does_not_swap_template(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    token = submit_for_review(client)
    client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/reject",
        json={"token": token, "reason": "revise"},
    )
    db.templates[CUSTOM_TID]["is_active"] = False
    db.seed_template(OTHER_TID, schema=other_schema(), version=2, is_active=True)

    stored = db.visit_reports[VISIT]["payload"]
    revised = dict(stored)
    revised["submissionData"] = dict(stored["submissionData"], f_summary="Now with numbers: 3 findings")
    save = client.put(f"/api/monitor/visits/{VISIT}/visit-report", json={"payload": revised})
    assert save.status_code == 200

    after = db.visit_reports[VISIT]["payload"]
    assert after["templateId"] == CUSTOM_TID
    assert after["submissionData"]["f_summary"] == "Now with numbers: 3 findings"
    assert after["templateSnapshot"]["id"] == CUSTOM_TID
    assert after["revisionBaseline"]["submissionData"]["f_summary"] == "All good"
    assert not after.get("archivedData")


def test_full_reject_revise_resubmit_approve_cycle(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)

    token1 = submit_for_review(client)
    client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/reject",
        json={"token": token1, "reason": "revise"},
    )

    # Author revises and resubmits; a different template goes live meanwhile.
    db.templates[CUSTOM_TID]["is_active"] = False
    db.seed_template(OTHER_TID, schema=other_schema(), version=2, is_active=True)
    stored = db.visit_reports[VISIT]["payload"]
    revised = dict(stored)
    revised["submissionData"] = dict(stored["submissionData"], f_summary="Revised")
    client.put(f"/api/monitor/visits/{VISIT}/visit-report", json={"payload": revised})
    token2 = submit_for_review(client)

    # Reviewer round 2 still sees the original custom template + revised data.
    review = client.get(
        f"/api/monitor/visits/{VISIT}/visit-report/review", params={"token": token2}
    ).json()
    assert review["template"]["id"] == CUSTOM_TID
    assert review["payload"]["submissionData"]["f_summary"] == "Revised"

    approve = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/approve",
        json={"token": token2},
    )
    assert approve.status_code == 200

    final = db.visit_reports[VISIT]["payload"]
    assert final["reportStatus"] == "Approved"
    assert final["templateSnapshot"]["id"] == CUSTOM_TID
    assert db.tokens[token2]["is_valid"] is False


# ══════════════════════════════════════════════════════════════════════════════
# Approval + locking
# ══════════════════════════════════════════════════════════════════════════════

def test_approve_locks_template_and_notifies_author(review_client):
    client, db, emails = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    token = submit_for_review(client)
    emails.clear()

    res = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/approve",
        json={"token": token},
    )
    assert res.status_code == 200
    stored = db.visit_reports[VISIT]["payload"]
    assert stored["reportStatus"] == "Approved"
    assert stored["templateSnapshot"]["id"] == CUSTOM_TID
    assert len(emails) == 1 and emails[0]["to"] == "cra@test.com"

    # Approved reports never re-sync to a newer live template.
    db.templates[CUSTOM_TID]["is_active"] = False
    db.seed_template(OTHER_TID, schema=other_schema(), version=2, is_active=True)
    body = client.get(f"/api/monitor/visits/{VISIT}/visit-report").json()
    assert body["templateSynced"] is False
    assert body["activeTemplate"]["id"] == CUSTOM_TID
    assert body["payload"]["templateId"] == CUSTOM_TID


def test_approve_captures_snapshot_for_reports_that_predate_snapshots(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    payload = seed_custom_report(db, status="In Review")
    assert "templateSnapshot" not in payload
    db.tokens["tok-a"] = {
        "id": "tokid-a", "visit_id": VISIT, "token": "tok-a",
        "reviewer_email": "sponsor@test.com", "author_email": "", "message": "",
        "is_valid": True, "created_at": datetime.now(timezone.utc),
    }

    res = client.post(
        f"/api/monitor/visits/{VISIT}/visit-report/review/approve",
        json={"token": "tok-a"},
    )
    assert res.status_code == 200
    snap = db.visit_reports[VISIT]["payload"]["templateSnapshot"]
    assert snap["id"] == CUSTOM_TID


def test_in_review_report_is_locked_against_template_sync(review_client):
    client, db, _ = review_client
    db.seed_visit(VISIT)
    db.seed_template(CUSTOM_TID, schema=custom_schema(), is_active=True)
    seed_custom_report(db)
    submit_for_review(client)

    db.templates[CUSTOM_TID]["is_active"] = False
    db.seed_template(OTHER_TID, schema=other_schema(), version=2, is_active=True)

    body = client.get(f"/api/monitor/visits/{VISIT}/visit-report").json()
    assert body["templateSynced"] is False
    assert body["payload"]["templateId"] == CUSTOM_TID
    assert body["activeTemplate"]["id"] == CUSTOM_TID


# ══════════════════════════════════════════════════════════════════════════════
# customTemplateFields (legacy-layout custom templates)
# ══════════════════════════════════════════════════════════════════════════════

def test_frozen_template_derivation_keeps_custom_template_fields(review_client):
    """Answers stored under customTemplateFields must count as report data."""
    client, db, _ = review_client
    db.seed_visit(VISIT)
    schema = {
        "fields": [
            {"id": "cf_extra", "type": "text", "label": "Extra Question"},
            {"id": "cf_unused", "type": "text", "label": "Never answered"},
        ]
    }
    db.seed_template(CUSTOM_TID, schema=schema, is_active=True)
    db.visit_reports[VISIT] = {
        "payload": {
            "schemaVersion": 1,
            "reportStatus": "In Review",
            "templateId": "tpl-deleted",
            "customTemplateFields": {"cf_extra": "answered"},
        },
        "updated_at": datetime.now(timezone.utc),
    }
    db.tokens["tok-c"] = {
        "id": "tokid-c", "visit_id": VISIT, "token": "tok-c",
        "reviewer_email": "sponsor@test.com", "author_email": "", "message": "",
        "is_valid": True, "created_at": datetime.now(timezone.utc),
    }

    res = client.get(f"/api/monitor/visits/{VISIT}/visit-report/review", params={"token": "tok-c"})
    ids = [f["id"] for f in res.json()["template"]["schema"]["fields"]]
    assert "cf_extra" in ids
    assert "cf_unused" not in ids

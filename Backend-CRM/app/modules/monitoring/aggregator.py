import asyncio
import html
import json
import hmac
import hashlib
import base64
import os
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import get_db
from app.integrations.smtp_service import smtp_service
from app.modules.monitoring.auth import require_monitor_auth

router = APIRouter(
    prefix="/api/monitor",
    tags=["monitor"],
    dependencies=[Depends(require_monitor_auth)],
)



# ── Pydantic models ───────────────────────────────────────────────────────────



class PreVisitSummarySendBody(BaseModel):
    content: str = Field(..., min_length=1)
    cc_emails: str = ""


class PreVisitAcknowledgeBody(BaseModel):
    token: str = Field(..., min_length=10)




_TABLES_VERIFIED = False

# Serialize monitor DDL bootstrap across all connections/workers. Concurrent
# ALTER TABLE + SELECT on the same catalogs deadlocks Postgres when multiple
# requests hit _ensure_monitor_tables before _TABLES_VERIFIED flips true.
_MONITOR_SCHEMA_ADVISORY_KEY = (88273421, 33472811)


# ── AI Pre-Visit Summary Generator ────────────────────────────────────────────



class VisitRescheduleSubmit(BaseModel):
    token: str
    proposed_datetime_iso: str = Field(..., min_length=1)
    proposed_end_datetime_iso: Optional[str] = None
    proposed_slots: Optional[List[Dict[str, str]]] = None
    reason: str = Field(..., min_length=1)


class VisitRescheduleDecisionSubmit(BaseModel):
    decision: str = Field(..., min_length=1)  # approved | rejected
    reason: Optional[str] = None
    selected_slot_index: Optional[int] = None


PROTOCOL_VISIT_OBJECTIVES: List[str] = [
    "Ensure the site follows the approved protocol.",
    "Protect participant safety and ethical rights.",
    "Verify proper consent process.",
    "Ensure data accuracy and integrity.",
    "Ensure proper handling of study drug/device.",
    "Ensure timely and accurate data handling.",
    "Monitor site efficiency and resolve risks.",
    "Ensure regulatory documentation is complete and up to date.",
]

_PRE_VISIT_ON_SITE_MONITORING: List[str] = [
    "Confirmation letter with agenda shared with the site",
    "EDC data reviewed (missing data, queries)",
    "SDV targets defined (risk-based %)",
    "Open queries identified",
    "Enrollment status reviewed",
    "Screen failures tracked",
    "SAE/AE listings reviewed",
    "Previous action items reviewed",
    "CAPA status checked",
    "Outstanding issues flagged",
    "IP accountability logs reviewed remotely",
    "Dispensing records checked",
    "Protocol deviations reviewed",
    "High-risk patients/sites flagged",
    "KRI dashboard reviewed",
]

PRE_VISIT_CHECKLIST_TEMPLATES: Dict[str, List[str]] = {
    "site initiation visit": [
        "Confirmation letter with agenda shared with the site",
        "IRB/EC approval obtained",
        "Regulatory binder completeness (ICF, protocol, IB, approvals)",
        "Investigator CVs and licenses verified",
        "Delegation of Authority (DOA) log drafted",
        "CTA fully executed",
        "Budget finalized and approved",
        "Site payment terms confirmed",
        "Investigational Product (IP) shipment confirmed",
        "Pharmacy readiness verified",
        "Lab kits and manuals available",
        "EDC access granted and tested",
        "IWRS/IRT configured",
        "eTMF structure ready",
        "Site staff training scheduled",
        "Protocol training materials ready",
        "GCP certificates available",
    ],
    "site qualification visit": [
        "Confirmation letter with agenda shared with the site",
        "Feasibility questionnaire reviewed",
        "Regulatory binder draft reviewed",
        "Investigator CVs and licenses verified",
        "Site facilities tour scheduled",
        "Pharmacy and lab capabilities assessed",
        "Staff qualifications reviewed",
        "Protocol feasibility confirmed",
        "Budget and contract status reviewed",
        "IP storage readiness assessed",
        "EDC/eSource readiness discussed",
        "Site initiation timeline agreed",
    ],
    "on-site monitoring": list(_PRE_VISIT_ON_SITE_MONITORING),
    "ad-hoc monitoring visit": list(_PRE_VISIT_ON_SITE_MONITORING),
    "for-cause visit": list(_PRE_VISIT_ON_SITE_MONITORING),
    "remote monitoring": [
        "Confirmation letter with agenda shared with the site",
        "Remote access to EDC/eSource confirmed",
        "Secure document sharing enabled",
        "Video call scheduled with site",
        "SDV/SDR plan defined",
        "Critical data points identified",
        "Query backlog reviewed",
        "Regulatory documents uploaded in eTMF",
        "ICF scans available",
        "Source documents shared",
        "Key site staff availability confirmed",
    ],
    "centralized monitoring": [
        "Confirmation letter with agenda shared with the site",
        "Data pulled from EDC, CTMS, safety systems",
        "Data cleaned and standardized",
        "Enrollment rate vs plan",
        "Query rate / aging",
        "Protocol deviation rate",
        "SAE reporting timelines",
        "Cross-site comparison",
        "Outlier detection (site/patient level)",
        "Data inconsistency patterns",
        "Sites requiring onsite visit flagged",
        "High-risk patients identified",
        "Data anomalies escalated",
    ],
    "close-out visit": [
        "Confirmation letter with agenda shared with the site",
        "All patients completed or discontinued",
        "Last Patient Last Visit (LPLV) confirmed",
        "Database lock status verified",
        "All queries resolved",
        "SDV completed (100% or per plan)",
        "Protocol deviations finalized",
        "IP reconciliation completed",
        "Drug return/destruction documented",
        "Regulatory binder complete",
        "Essential documents filed in eTMF",
        "Archival readiness confirmed",
        "Final invoice prepared",
        "Payments reconciled",
    ],
}

FOLLOW_UP_LETTER_DEFAULT_CONTENT = """Date: [Letter Date]

To:
[PI Name With Degree]
[Site Name Line]
[Department Division]
[Address Street]
[Address City Region Postal Country]

From:
[Monitor Name Full]
[Sponsor Organization Name]
[Monitor Email Address]
[Monitor Telephone Number]

Subject: Follow-Up Letter — Monitoring Visit | [Study Display Name] | Protocol [Study Protocol Ref] | Site [Clinical Site Identifier] | Visit Date: [Clinical Visit Date]

--------------------------------------------------------------------------------
1. INTRODUCTION
--------------------------------------------------------------------------------

Dear [PI Dear Name],

This letter is issued as a follow-up to the monitoring visit conducted at [Site Name Line] (Site ID: [Clinical Site Identifier]) on [Clinical Visit Date] as part of the [Study Display Name] (Protocol Number: [Study Protocol Ref]) sponsored by [Sponsor Organization Name].

The purpose of this correspondence is to formally document the findings, observations, and action items identified during the visit, and to confirm the timelines required for their resolution. We appreciate the cooperation and assistance provided by you and your study team during the visit.

--------------------------------------------------------------------------------
2. SUMMARY OF FINDINGS
--------------------------------------------------------------------------------

The following findings were identified during the monitoring visit. Each finding is categorized by area and assigned a severity level: Critical, Major, or Minor.

| Category              | Finding Description | Severity | Reference |
|-----------------------|---------------------|----------|-----------|
| Regulatory Documents  |                     |          |           |
| Informed Consent      |                     |          |           |
| Source Data / SDV     |                     |          |           |
| IP Management         |                     |          |           |
| Safety Reporting      |                     |          |           |
| Protocol Compliance   |                     |          |           |
| Data Quality          |                     |          |           |
| Staff Training        |                     |          |           |

(Optional — Provide a brief narrative summary highlighting the most important observations, positive findings, and areas requiring immediate attention.)

--------------------------------------------------------------------------------
3. ACTION ITEMS
--------------------------------------------------------------------------------

The table below summarizes all action items arising from this monitoring visit. Please ensure that all items are addressed within the specified timelines and that a written response is submitted to the monitor by [Written Response Due Date].

| # | Action Item / Finding | Required Action | Due Date | Priority |
|---|-----------------------|-----------------|----------|---------|
| 1 |                       |                 |          |         |
| 2 |                       |                 |          |         |
| 3 |                       |                 |          |         |
| 4 |                       |                 |          |         |
| 5 |                       |                 |          |         |
| 6 |                       |                 |          |         |

--------------------------------------------------------------------------------
4. TIMELINES FOR RESOLUTION
--------------------------------------------------------------------------------

| Severity Level | Required Response Timeline | Escalation Timeline |
|----------------|----------------------------|---------------------|
| Critical       | Within 48 hours of receipt | Immediate sponsor notification |
| Major          | Within 7 calendar days | Escalation if unresolved within 14 days |
| Minor          | Within 14 calendar days | Escalation if unresolved within 30 days |

Please confirm receipt of this letter and provide your written response addressing each action item by [Written Response Due Date Long]. Your response should be directed to [Monitor Email Address] with a copy to [Sponsor Contact Name And Email].

--------------------------------------------------------------------------------
5. CLOSING REMARKS
--------------------------------------------------------------------------------

We recognize and appreciate the efforts of your team in conducting this study in accordance with Good Clinical Practice (ICH-GCP E6 R2) guidelines and applicable regulatory requirements. The findings noted in this letter are intended to support the continuous improvement of study conduct and data quality at your site.

Should you require clarification on any of the items raised in this letter, or if you wish to discuss any of the findings, please do not hesitate to contact the undersigned monitor. We look forward to your timely response and continued collaboration.

--------------------------------------------------------------------------------
AUTHORIZATION
--------------------------------------------------------------------------------

Monitor Name          [Monitor Name Full]
Monitor Signature     
Date                  [Authorization Date]
Sponsor / CRO Contact [Sponsor Contact Role Line]
Response Due Date     [Written Response Due Date Long]

CONFIDENTIAL                                                          Page 1 of 2
"""


def _urlsafe_b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _urlsafe_b64_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("utf-8"))


def _build_visit_confirmation_token(
    visit_id: str,
    actor_role: str,
    ttl_seconds: int = 60 * 60 * 24 * 14,
) -> str:
    """
    Build a signed token containing visit_id + actor_role + expiry.
    Format: base64url("visit_id:actor_role:exp").base64url(hmac_sha256(secret, payload))
    """
    role = actor_role if actor_role in {"pi", "coordinator"} else "pi"
    exp = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
    payload = f"{visit_id}:{role}:{exp}".encode("utf-8")
    sig = hmac.new(settings.secret_key.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_urlsafe_b64(payload)}.{_urlsafe_b64(sig)}"


def _decode_visit_confirmation_token(token: str, expected_visit_id: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        payload = _urlsafe_b64_decode(payload_b64)
        sig = _urlsafe_b64_decode(sig_b64)
        expected_sig = hmac.new(settings.secret_key.encode("utf-8"), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            return None

        payload_text = payload.decode("utf-8")
        visit_id, actor_role, exp_raw = payload_text.rsplit(":", 2)
        if visit_id != expected_visit_id:
            return None
        if actor_role not in {"pi", "coordinator"}:
            return None
        exp = int(exp_raw)
        now_ts = int(datetime.now(timezone.utc).timestamp())
        if now_ts > exp:
            return None
        return {"visit_id": visit_id, "actor_role": actor_role, "exp": exp}
    except Exception:
        return None


def _build_previsit_report_ack_token(visit_id: str, ttl_seconds: int = 60 * 60 * 24 * 30) -> str:
    """HMAC token for site to acknowledge pre-visit report without login (payload: visit_id:previsit_report_ack:exp)."""
    exp = int(datetime.now(timezone.utc).timestamp()) + ttl_seconds
    payload = f"{visit_id}:previsit_report_ack:{exp}".encode("utf-8")
    sig = hmac.new(settings.secret_key.encode("utf-8"), payload, hashlib.sha256).digest()
    return f"{_urlsafe_b64(payload)}.{_urlsafe_b64(sig)}"


def _decode_previsit_report_ack_token(token: str, expected_visit_id: str) -> Optional[Dict[str, Any]]:
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts
        payload = _urlsafe_b64_decode(payload_b64)
        sig = _urlsafe_b64_decode(sig_b64)
        expected_sig = hmac.new(settings.secret_key.encode("utf-8"), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        payload_text = payload.decode("utf-8")
        visit_id, purpose, exp_raw = payload_text.rsplit(":", 2)
        if visit_id != expected_visit_id or purpose != "previsit_report_ack":
            return None
        exp = int(exp_raw)
        if int(datetime.now(timezone.utc).timestamp()) > exp:
            return None
        return {"visit_id": visit_id, "exp": exp}
    except Exception:
        return None


def _parse_proposed_datetime_iso(raw: str) -> str:
    """Validate proposed slot and return a normalized UTC ISO-8601 string (…Z) for storage."""
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty")
    normalized = s[:-1] + "+00:00" if s.endswith("Z") else s
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    u = dt.astimezone(timezone.utc)
    return u.strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _format_utc_label_from_iso(iso_utc: str) -> str:
    """Convert ISO UTC string into a human-friendly label."""
    normalized = (iso_utc or "").strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    u = dt.astimezone(timezone.utc)
    return u.strftime("%B %d, %Y %I:%M %p UTC")


async def _sync_visit_objectives(db: AsyncSession, visit_id: str) -> None:
    existing_rows = await db.execute(
        text(
            """
            SELECT id, objective_text, done
            FROM monitoring_visit_objectives
            WHERE visit_id = :visit_id
            ORDER BY display_order, id
            """
        ),
        {"visit_id": visit_id},
    )
    existing = existing_rows.mappings().all()
    done_by_text: Dict[str, bool] = {
        str(row["objective_text"]): bool(row["done"])
        for row in existing
        if row.get("objective_text")
    }

    # Keep objectives canonical across visits and preserve checked state where text matches.
    await db.execute(
        text("DELETE FROM monitoring_visit_objectives WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )

    for idx, text_value in enumerate(PROTOCOL_VISIT_OBJECTIVES, start=1):
        await db.execute(
            text(
                """
                INSERT INTO monitoring_visit_objectives
                    (visit_id, objective_text, done, tag_type, display_order)
                VALUES
                    (:visit_id, :objective_text, :done, :tag_type, :display_order)
                """
            ),
            {
                "visit_id": visit_id,
                "objective_text": text_value,
                "done": done_by_text.get(text_value, False),
                "tag_type": "required",
                "display_order": idx,
            },
        )


def _build_visit_date_fields_from_date_and_time(
    visit_date_iso_input: str,
    time_hhmm: Optional[str] = None,
) -> tuple[str, str]:
    """
    visit_date_iso_input: YYYY-MM-DD from the client, or empty.
    time_hhmm: optional HH:MM (24h, HTML time input). Defaults to 08:00 if date is set and time is empty.
    Returns (visit_date display string, visit_date_iso with Z / UTC).
    """
    dpart = (visit_date_iso_input or "").strip()
    if not dpart:
        return ("TBD", "")
    try:
        y, mo, d_ = (int(x) for x in dpart.split("-", 2))
    except ValueError:
        return (visit_date_iso_input, "")

    h, mi = 8, 0
    raw_t = (time_hhmm or "").strip()
    if raw_t:
        try:
            tparts = raw_t.replace(".", ":").split(":")
            h = int(tparts[0]) % 24
            mi = int(tparts[1]) if len(tparts) > 1 else 0
            if mi < 0 or mi > 59:
                mi = 0
        except (ValueError, IndexError):
            h, mi = 8, 0

    dt_utc = datetime(y, mo, d_, h, mi, 0, tzinfo=timezone.utc)
    visit_date_iso = dt_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
    h12 = dt_utc.hour % 12
    if h12 == 0:
        h12 = 12
    ampm = "AM" if dt_utc.hour < 12 else "PM"
    t_disp = f"{h12}:{dt_utc.minute:02d} {ampm}"
    month_str = dt_utc.strftime("%B %d, %Y")
    return (f"{month_str} · {t_disp}", visit_date_iso)


def _build_optional_visit_date_fields(
    visit_date_iso_input: str,
    time_hhmm: Optional[str] = None,
) -> tuple[str, str]:
    dpart = (visit_date_iso_input or "").strip()
    if not dpart:
        return ("", "")
    return _build_visit_date_fields_from_date_and_time(dpart, time_hhmm)


def _display_and_iso_from_stored_iso(iso: str) -> tuple[str, str]:
    """Parse a stored UTC ISO instant into (display label, visit_*_iso Z string)."""
    normalized = (iso or "").strip().replace("Z", "+00:00")
    if not normalized:
        return ("", "")
    dt = datetime.fromisoformat(normalized)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    u = dt.astimezone(timezone.utc)
    ymd = u.strftime("%Y-%m-%d")
    hhmm = f"{u.hour:02d}:{u.minute:02d}"
    return _build_visit_date_fields_from_date_and_time(ymd, hhmm)


def _effective_visit_schedule_from_row(visit: dict) -> dict[str, str]:
    """
    Resolve the dates/times the UI should show for a visit.

    While status is ``Reschedule Requested``, prefer the proposed slot stored on
    the visit row (site has asked for new dates; letter/logistics should reflect
    the request). After sponsor approval the canonical ``visit_date*`` /
    ``visit_end_date*`` columns are updated and used instead.
    """
    status = str(visit.get("status") or "").strip().lower()
    proposed_start = str(visit.get("reschedule_proposed_datetime_iso") or "").strip()
    proposed_end = str(visit.get("reschedule_proposed_end_datetime_iso") or "").strip()

    if status == "reschedule requested" and proposed_start:
        start_display, start_iso = _display_and_iso_from_stored_iso(proposed_start)
        end_src = proposed_end or proposed_start
        end_display, end_iso = _display_and_iso_from_stored_iso(end_src)
        return {
            "visitDate": start_display,
            "visitDateIso": start_iso,
            "endDate": end_display,
            "endDateIso": end_iso,
        }

    return {
        "visitDate": str(visit.get("visit_date") or ""),
        "visitDateIso": str(visit.get("visit_date_iso") or ""),
        "endDate": str(visit.get("visit_end_date") or ""),
        "endDateIso": str(visit.get("visit_end_date_iso") or ""),
    }


def _parse_optional_decimal(raw: Any) -> Optional[Decimal]:
    if raw is None:
        return None
    if isinstance(raw, Decimal):
        return raw
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    text_val = str(raw).strip()
    if not text_val:
        return None
    try:
        return Decimal(text_val)
    except InvalidOperation:
        return None


def _normalize_visit_type(raw_type: str) -> str:
    s = (raw_type or "").strip().lower()
    if s in {
        "on-site",
        "on site",
        "on-site monitoring",
        "onsite monitoring",
        "on-site monitoring visit",
        "on site monitoring visit",
        "on-site visit",
        "on site visit",
    }:
        return "on-site monitoring"
    if s in {"remote", "remote monitoring", "remote monitoring visit", "remote visit"}:
        return "remote monitoring"
    if s in {
        "site qualification",
        "site qualification visit",
        "sqv",
        "site qualification visit (sqv)",
    }:
        return "site qualification visit"
    if s in {"routine", "routine visit", "routine monitoring visit"}:
        return "on-site monitoring"
    if s in {"centralized", "centralized monitoring", "centralized monitoring visit", "centralized visit"}:
        return "remote monitoring"
    if s in {
        "ad-hoc",
        "ad hoc",
        "ad-hoc monitoring",
        "ad hoc monitoring",
        "ad-hoc monitoring visit",
        "ad hoc monitoring visit",
        "for-cause",
        "for cause",
        "for-cause visit",
        "for cause visit",
        "for-cause monitoring visit",
        "for cause monitoring visit",
    }:
        return "ad-hoc monitoring visit"
    if s in {
        "initiation",
        "initiation visit",
        "site initiation",
        "site initiation visit",
    }:
        return "site initiation visit"
    if s in {
        "close-out",
        "close out",
        "close-out visit",
        "close out visit",
        "close-out monitoring visit",
        "close out monitoring visit",
    }:
        return "close-out visit"
    return "on-site monitoring"




async def _sync_pre_visit_checklist(
    db: AsyncSession, visit_id: str, visit_type: str, *, replace_template: bool = False
) -> None:
    """Ensure pre-visit checklist rows exist for this visit.

    By default (replace_template=False), used on GET /pre-visit: seed only when the checklist
    is empty. Avoids DELETE+reinsert on every read, which invalidated row ids and raced with
    PATCH toggles so CRAs could not reliably check items before sending the report.

    When replace_template=True (e.g. visit type changed on update), rebuild from template while
    preserving done state keyed by item_text where possible.
    """
    template_key = _normalize_visit_type(visit_type)
    canonical_items = PRE_VISIT_CHECKLIST_TEMPLATES.get(
        template_key, PRE_VISIT_CHECKLIST_TEMPLATES["on-site monitoring"]
    )

    existing_rows = await db.execute(
        text(
            """
            SELECT item_text, done
            FROM monitoring_pre_visit_checklist
            WHERE visit_id = :visit_id
            ORDER BY display_order ASC, id ASC
            """
        ),
        {"visit_id": visit_id},
    )
    existing = existing_rows.mappings().all()

    if not replace_template and len(existing) > 0:
        return

    done_by_text: Dict[str, bool] = {
        str(row["item_text"]): bool(row["done"])
        for row in existing
        if row.get("item_text")
    }
    legacy_agenda_keys = {
        "Agenda shared with site",
        "Agenda shared with the site",
    }

    await db.execute(
        text("DELETE FROM monitoring_pre_visit_checklist WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )
    for idx, item_text in enumerate(canonical_items, start=1):
        await db.execute(
            text(
                """
                INSERT INTO monitoring_pre_visit_checklist
                    (visit_id, item_text, done, tag_type, display_order)
                VALUES
                    (:visit_id, :item_text, :done, :tag_type, :display_order)
                """
            ),
            {
                "visit_id": visit_id,
                "item_text": item_text,
                "done": (
                    done_by_text.get(item_text, False)
                    if item_text != "Confirmation letter with agenda shared with the site"
                    else (
                        done_by_text.get("Confirmation letter with agenda shared with the site", False)
                        or any(done_by_text.get(k, False) for k in legacy_agenda_keys)
                    )
                ),
                "tag_type": "required",
                "display_order": idx,
            },
        )


def _visit_label_from_site_number(site_visit_number: Optional[Any], visit_id: str) -> str:
    """UI label: Visit #n per site when available; otherwise stable id."""
    try:
        n = int(site_visit_number) if site_visit_number is not None else None
    except (TypeError, ValueError):
        n = None
    if n is not None and n >= 1:
        return f"Visit #{n}"
    return visit_id


def _rewrite_visit_id_in_text(activity_text: Optional[str], visit_id: str, site_visit_number: Optional[Any]) -> str:
    """Replace embedded MON-… id in stored activity copy with Visit #n when possible."""
    if not activity_text:
        return ""
    label = _visit_label_from_site_number(site_visit_number, visit_id)
    if not visit_id or label == visit_id:
        return str(activity_text)
    return str(activity_text).replace(visit_id, label)


async def _append_visit_activity(
    db: AsyncSession,
    visit_id: str,
    activity_text: str,
    initials: str = "SY",
    color: str = "blue",
) -> None:
    now_utc = datetime.now(timezone.utc)
    display_time = now_utc.strftime("%b %d, %Y %I:%M %p UTC")
    await db.execute(
        text(
            """
            INSERT INTO monitoring_visit_activity (visit_id, initials, color, activity_text, activity_time)
            VALUES (:visit_id, :initials, :color, :activity_text, :activity_time);
            """
        ),
        {
            "visit_id": visit_id,
            "initials": initials,
            "color": color,
            "activity_text": activity_text,
            "activity_time": display_time,
        },
    )


def _normalize_visit_site_bucket(site_id: Optional[str]) -> str:
    """Bucket key for per-site visit numbering (must match SQL COALESCE(site_id, ''))."""
    return (site_id or "").strip()


async def _monitor_pg_advisory_lock_site_bucket(db: AsyncSession, bucket: str) -> None:
    """Serialize allocate-next for one site bucket (transaction-scoped advisory lock)."""
    await db.execute(
        text("SELECT pg_advisory_xact_lock((abs(hashtext(CAST(:bucket AS TEXT))))::bigint)"),
        {"bucket": bucket},
    )


async def _next_site_visit_sequence(db: AsyncSession, bucket: str) -> int:
    """Next 1-based visit number for this site bucket. Caller must hold bucket advisory lock."""
    r = await db.execute(
        text(
            """
            SELECT COALESCE(MAX(site_visit_number), 0) AS m
            FROM monitoring_visits
            WHERE COALESCE(site_id, '') = CAST(:bucket AS TEXT)
            """
        ),
        {"bucket": bucket},
    )
    row = r.mappings().first() or {}
    return int(row.get("m") or 0) + 1


async def _purge_legacy_default_mvr_template(db: AsyncSession) -> None:
    """Remove the old auto-seeded 'Default MVR' template; it is no longer offered."""
    await db.execute(
        text(
            """
            DELETE FROM monitoring_mvr_templates
            WHERE organization_id = 'default'
              AND TRIM(name) = 'Default MVR'
            """
        )
    )


async def _ensure_mvr_templates_lifecycle_column(db: AsyncSession) -> None:
    await db.execute(
        text(
            """
            ALTER TABLE monitoring_mvr_templates
            ADD COLUMN IF NOT EXISTS lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'published'
            """
        )
    )




async def _ensure_monitor_tables(db: AsyncSession) -> None:
    global _TABLES_VERIFIED
    if _TABLES_VERIFIED:
        return

    await db.execute(
        text(
            "SELECT pg_advisory_lock(:k1, :k2)"
        ),
        {"k1": _MONITOR_SCHEMA_ADVISORY_KEY[0], "k2": _MONITOR_SCHEMA_ADVISORY_KEY[1]},
    )
    try:
        if _TABLES_VERIFIED:
            return

        exists_row = await db.execute(
            text(
                "SELECT to_regclass('public.monitoring_visits') IS NOT NULL AS present"
            )
        )
        _ = exists_row.scalar()  # consume the result; CREATE TABLE IF NOT EXISTS handles both cases

        # Run CREATE TABLE (idempotent) and ALTER TABLE migrations on every cold start
        # so that existing databases automatically gain new columns.
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_visits (
                    id VARCHAR(100) PRIMARY KEY,
                    site_id VARCHAR(100),
                    study_id VARCHAR(100),
                    cra_name VARCHAR(255) NOT NULL DEFAULT '',
                    status VARCHAR(50) NOT NULL DEFAULT 'Scheduled',
                    priority VARCHAR(20) NOT NULL DEFAULT 'Medium',
                    visit_type VARCHAR(100) NOT NULL,
                    visit_date VARCHAR(100) NOT NULL,
                    visit_date_iso VARCHAR(40) NOT NULL DEFAULT '',
                    visit_end_date VARCHAR(100) NOT NULL DEFAULT '',
                    visit_end_date_iso VARCHAR(40) NOT NULL DEFAULT '',
                    estimated_duration_days NUMERIC(10,2),
                    duration VARCHAR(100) NOT NULL,
                    protocol VARCHAR(100) NOT NULL,
                    ind_number VARCHAR(100) NOT NULL,
                    sponsor VARCHAR(255) NOT NULL,
                    risk_level VARCHAR(50) NOT NULL,
                    principal_investigator VARCHAR(255) NOT NULL,
                    pi_email VARCHAR(255) NOT NULL,
                    study_coordinator VARCHAR(255) NOT NULL,
                    coordinator_phone VARCHAR(100) NOT NULL,
                    site_address TEXT NOT NULL,
                    irb_approval VARCHAR(255) NOT NULL,
                    sdv_verified_subjects INTEGER NOT NULL DEFAULT 0,
                    sdv_total_subjects INTEGER NOT NULL DEFAULT 0,
                    subjects_enrolled VARCHAR(100) NOT NULL,
                    crf_completion VARCHAR(50) NOT NULL,
                    query_rate VARCHAR(100) NOT NULL,
                    last_sdv_date VARCHAR(100) NOT NULL,
                    action_required_count INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        # Migrate existing tables: add columns that didn't exist before.
        # IF NOT EXISTS makes these safe to run every time.
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS site_id VARCHAR(100);"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS study_id VARCHAR(100);"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS cra_name VARCHAR(255) NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS cra_email VARCHAR(255) NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'Scheduled';"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS visit_date_iso VARCHAR(40) NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS priority VARCHAR(20) NOT NULL DEFAULT 'Medium';"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS visit_end_date VARCHAR(100) NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS visit_end_date_iso VARCHAR(40) NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS estimated_duration_days NUMERIC(10,2);"))
        await db.execute(
            text(
                "ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS reschedule_proposed_datetime_iso VARCHAR(80) NOT NULL DEFAULT '';"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS reschedule_proposed_end_datetime_iso VARCHAR(80) NOT NULL DEFAULT '';"
            )
        )
        await db.execute(text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS reschedule_reason TEXT NOT NULL DEFAULT '';"))
        await db.execute(
            text(
                "ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS reschedule_requested_at TIMESTAMP WITH TIME ZONE NULL;"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS reschedule_requested_by_role VARCHAR(50) NOT NULL DEFAULT '';"
            )
        )
        await db.execute(
            text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS site_visit_number INTEGER;")
        )
        await db.execute(
            text("ALTER TABLE monitoring_visits ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP WITH TIME ZONE;")
        )

        missed = await db.scalar(
            text(
                """
                SELECT COUNT(*)::int
                FROM monitoring_visits
                WHERE site_visit_number IS NULL OR site_visit_number < 1
                """
            )
        )
        if missed and int(missed) > 0:
            await db.execute(
                text(
                    """
                    UPDATE monitoring_visits mv
                    SET site_visit_number = sub.rn
                    FROM (
                        SELECT
                            id,
                            ROW_NUMBER() OVER (
                                PARTITION BY COALESCE(site_id, '')
                                ORDER BY COALESCE(created_at, TIMESTAMP '1970-01-01'), id::text
                            )::INTEGER AS rn
                        FROM monitoring_visits
                    ) sub
                    WHERE mv.id = sub.id
                      AND (
                            mv.site_visit_number IS NULL
                            OR mv.site_visit_number < 1
                      )
                    """
                )
            )

        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_visit_objectives (
                    id SERIAL PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    objective_text TEXT NOT NULL,
                    done BOOLEAN NOT NULL DEFAULT FALSE,
                    tag_type VARCHAR(50) NOT NULL DEFAULT 'optional',
                    display_order INTEGER NOT NULL DEFAULT 0,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_visit_activity (
                    id SERIAL PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    initials VARCHAR(20) NOT NULL,
                    color VARCHAR(50) NOT NULL,
                    activity_text TEXT NOT NULL,
                    activity_time VARCHAR(100) NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_monitoring_visit_objectives_visit_id ON monitoring_visit_objectives(visit_id);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_monitoring_visit_activity_visit_id ON monitoring_visit_activity(visit_id);"
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_confirmation_letters (
                    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    last_sent VARCHAR(100) NOT NULL DEFAULT '',
                    delivery_status VARCHAR(50) NOT NULL DEFAULT 'Draft',
                    cc_emails TEXT NOT NULL DEFAULT '',
                    confirmed_by_role VARCHAR(50) NOT NULL DEFAULT '',
                    confirmed_by_name VARCHAR(255) NOT NULL DEFAULT '',
                    confirmed_by_email VARCHAR(255) NOT NULL DEFAULT '',
                    confirmed_at TIMESTAMP WITH TIME ZONE NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        await db.execute(text("ALTER TABLE monitoring_confirmation_letters ADD COLUMN IF NOT EXISTS confirmed_by_role VARCHAR(50) NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_confirmation_letters ADD COLUMN IF NOT EXISTS cc_emails TEXT NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_confirmation_letters ADD COLUMN IF NOT EXISTS confirmed_by_name VARCHAR(255) NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_confirmation_letters ADD COLUMN IF NOT EXISTS confirmed_by_email VARCHAR(255) NOT NULL DEFAULT '';"))
        await db.execute(text("ALTER TABLE monitoring_confirmation_letters ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMP WITH TIME ZONE NULL;"))
        await db.execute(text("ALTER TABLE monitoring_follow_up_letters ADD COLUMN IF NOT EXISTS ack_token VARCHAR(128) UNIQUE;"))
        await db.execute(text("ALTER TABLE monitoring_follow_up_letters ADD COLUMN IF NOT EXISTS acknowledged_at TIMESTAMP WITH TIME ZONE;"))
        await db.execute(text("ALTER TABLE monitoring_follow_up_letters ADD COLUMN IF NOT EXISTS ack_status VARCHAR(50) NOT NULL DEFAULT 'pending';"))
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_pre_visit (
                    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    risk VARCHAR(20) NOT NULL DEFAULT 'high',
                    agenda TEXT NOT NULL DEFAULT '',
                    visit_date VARCHAR(20) NOT NULL DEFAULT '',
                    pending_actions JSONB NOT NULL DEFAULT '[]'::JSONB,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_pre_visit ADD COLUMN IF NOT EXISTS pre_visit_report_status VARCHAR(50) NOT NULL DEFAULT 'DRAFT';"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_pre_visit ADD COLUMN IF NOT EXISTS pre_visit_reviewed_at TIMESTAMP WITH TIME ZONE;"
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_pre_visit_checklist (
                    id SERIAL PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    item_text TEXT NOT NULL,
                    done BOOLEAN NOT NULL DEFAULT FALSE,
                    tag_type VARCHAR(50) NOT NULL DEFAULT 'optional',
                    display_order INTEGER NOT NULL DEFAULT 0
                );
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_findings (
                    id VARCHAR(120) PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    category VARCHAR(100) NOT NULL,
                    description TEXT NOT NULL,
                    severity VARCHAR(50) NOT NULL,
                    status VARCHAR(50) NOT NULL,
                    site VARCHAR(255) NOT NULL,
                    assignee_initials VARCHAR(20) NOT NULL,
                    assignee_name VARCHAR(255) NOT NULL,
                    assignee_color VARCHAR(50) NOT NULL,
                    due_date VARCHAR(50) NOT NULL,
                    due_color VARCHAR(20) NOT NULL,
                    resolution TEXT NOT NULL DEFAULT ''
                );
                """
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_findings ADD COLUMN IF NOT EXISTS resolution TEXT NOT NULL DEFAULT '';"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_findings ADD COLUMN IF NOT EXISTS subject_id VARCHAR(100) NOT NULL DEFAULT '';"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_findings ADD COLUMN IF NOT EXISTS reference VARCHAR(500) NOT NULL DEFAULT '';"
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_finding_action_items (
                    id VARCHAR(140) PRIMARY KEY,
                    finding_id VARCHAR(120) NOT NULL REFERENCES monitoring_findings(id) ON DELETE CASCADE,
                    assignee_initials VARCHAR(20) NOT NULL DEFAULT '',
                    assignee_name VARCHAR(255) NOT NULL DEFAULT '',
                    assignee_color VARCHAR(50) NOT NULL DEFAULT 'blue',
                    due_date VARCHAR(50) NOT NULL DEFAULT 'TBD',
                    closed_date VARCHAR(50) NOT NULL DEFAULT '',
                    resolution TEXT NOT NULL DEFAULT '',
                    display_order INTEGER NOT NULL DEFAULT 0
                );
                """
            )
        )
        await db.execute(
            text(
                """
                ALTER TABLE monitoring_finding_action_items
                ADD COLUMN IF NOT EXISTS closed_date VARCHAR(50) NOT NULL DEFAULT '';
                """
            )
        )
        await db.execute(
            text(
                """
                ALTER TABLE monitoring_finding_action_items
                ADD COLUMN IF NOT EXISTS task_mode VARCHAR(20) NOT NULL DEFAULT '';
                """
            )
        )
        await db.execute(
            text(
                """
                ALTER TABLE monitoring_finding_action_items
                ADD COLUMN IF NOT EXISTS task_id VARCHAR(140);
                """
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_monitoring_finding_action_items_finding_id "
                "ON monitoring_finding_action_items (finding_id);"
            )
        )
        await db.execute(
            text(
                """
                DO $$
                BEGIN
                  IF EXISTS (
                    SELECT 1 FROM information_schema.columns c
                    WHERE c.table_schema = 'public'
                      AND c.table_name = 'monitoring_findings'
                      AND c.column_name = 'id'
                      AND c.character_maximum_length IS NOT NULL
                      AND c.character_maximum_length < 120
                  ) THEN
                    ALTER TABLE monitoring_findings ALTER COLUMN id TYPE VARCHAR(120);
                  END IF;
                END $$;
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_documents (
                    id SERIAL PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    category VARCHAR(100) NOT NULL,
                    icon VARCHAR(20) NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    size VARCHAR(50) NOT NULL,
                    date VARCHAR(100) NOT NULL,
                    uploader_initials VARCHAR(20) NOT NULL,
                    uploader_name VARCHAR(255) NOT NULL,
                    uploader_color VARCHAR(50) NOT NULL
                );
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_threads (
                    id SERIAL PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    title VARCHAR(255) NOT NULL,
                    participants VARCHAR(500) NOT NULL,
                    last_msg VARCHAR(100) NOT NULL,
                    unread INTEGER NOT NULL DEFAULT 0
                );
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_messages (
                    id SERIAL PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    sender VARCHAR(255) NOT NULL,
                    initials VARCHAR(20) NOT NULL,
                    color VARCHAR(50) NOT NULL,
                    text VARCHAR(2000) NOT NULL,
                    time VARCHAR(100) NOT NULL,
                    is_me BOOLEAN NOT NULL DEFAULT FALSE
                );
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_post_visit (
                    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    summary TEXT NOT NULL DEFAULT '',
                    critical_issues TEXT NOT NULL DEFAULT '',
                    rating VARCHAR(100) NOT NULL DEFAULT 'Satisfactory',
                    follow_up VARCHAR(100) NOT NULL DEFAULT 'Yes — Within 30 days',
                    next_date VARCHAR(20) NOT NULL DEFAULT '',
                    action_plan TEXT NOT NULL DEFAULT '',
                    recommendations TEXT NOT NULL DEFAULT '',
                    cra_name VARCHAR(255) NOT NULL DEFAULT '',
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_follow_up_letters (
                    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    content TEXT NOT NULL,
                    last_sent VARCHAR(100) NOT NULL DEFAULT '',
                    delivery_status VARCHAR(50) NOT NULL DEFAULT 'Draft',
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    ack_token VARCHAR(128) UNIQUE,
                    acknowledged_at TIMESTAMP WITH TIME ZONE,
                    ack_status VARCHAR(50) DEFAULT 'pending'
                );
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_visit_reports (
                    visit_id VARCHAR(100) PRIMARY KEY REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_visit_review_tokens (
                    id UUID PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    token VARCHAR(255) NOT NULL UNIQUE,
                    reviewer_email VARCHAR(255) NOT NULL,
                    author_email VARCHAR(255) NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    used_at TIMESTAMP WITH TIME ZONE NULL
                );
                """
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mvrt_token ON monitoring_visit_review_tokens(token);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mvrt_visit_id ON monitoring_visit_review_tokens(visit_id);"
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_visit_review_comments (
                    id UUID PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    token_id UUID NOT NULL REFERENCES monitoring_visit_review_tokens(id) ON DELETE CASCADE,
                    highlighted_text TEXT NOT NULL DEFAULT '',
                    dom_path TEXT NOT NULL DEFAULT '',
                    start_offset INTEGER NOT NULL DEFAULT 0,
                    end_offset INTEGER NOT NULL DEFAULT 0,
                    comment_text TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mvrc_visit_id ON monitoring_visit_review_comments(visit_id);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mvrc_token_id ON monitoring_visit_review_comments(token_id);"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_visit_review_comments "
                "ADD COLUMN IF NOT EXISTS author_reply TEXT NOT NULL DEFAULT '';"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE monitoring_visit_review_comments "
                "ADD COLUMN IF NOT EXISTS author_reply_at TIMESTAMP WITH TIME ZONE NULL;"
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS visit_reschedule_requests (
                    id UUID PRIMARY KEY,
                    visit_id VARCHAR(100) NOT NULL REFERENCES monitoring_visits(id) ON DELETE CASCADE,
                    proposed_date TIMESTAMP WITH TIME ZONE NOT NULL,
                    reason TEXT NOT NULL,
                    decision_reason TEXT NOT NULL DEFAULT '',
                    status VARCHAR(20) NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    decided_at TIMESTAMP WITH TIME ZONE NULL
                );
                """
            )
        )
        await db.execute(
            text(
                "ALTER TABLE visit_reschedule_requests ADD COLUMN IF NOT EXISTS decision_reason TEXT NOT NULL DEFAULT '';"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE visit_reschedule_requests ADD COLUMN IF NOT EXISTS proposed_end_date TIMESTAMP WITH TIME ZONE NULL;"
            )
        )
        await db.execute(
            text(
                "ALTER TABLE visit_reschedule_requests ADD COLUMN IF NOT EXISTS proposed_slots JSONB NOT NULL DEFAULT '[]'::jsonb;"
            )
        )
        await db.execute(
            text(
                """
                DO $$
                BEGIN
                  IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conname = 'ck_visit_reschedule_requests_status'
                  ) THEN
                    ALTER TABLE visit_reschedule_requests
                    ADD CONSTRAINT ck_visit_reschedule_requests_status
                    CHECK (status IN ('pending', 'approved', 'rejected'));
                  END IF;
                END $$;
                """
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_visit_reschedule_requests_visit_id ON visit_reschedule_requests(visit_id);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_visit_reschedule_requests_status_created_at ON visit_reschedule_requests(status, created_at DESC);"
            )
        )
        await db.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS monitoring_mvr_templates (
                    id UUID PRIMARY KEY,
                    organization_id VARCHAR(100) NOT NULL DEFAULT 'default',
                    name VARCHAR(255) NOT NULL DEFAULT 'MVR Template',
                    schema JSONB NOT NULL DEFAULT '{}'::jsonb,
                    version INTEGER NOT NULL DEFAULT 1,
                    is_active BOOLEAN NOT NULL DEFAULT FALSE,
                    lifecycle_status VARCHAR(20) NOT NULL DEFAULT 'published',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_mvr_templates_org_active ON monitoring_mvr_templates(organization_id, is_active);"
            )
        )
        await _ensure_mvr_templates_lifecycle_column(db)
        await _purge_legacy_default_mvr_template(db)
        # Phase 3-B perf indexes (idempotent)
        await db.execute(
            text("CREATE INDEX IF NOT EXISTS idx_monitoring_findings_visit_id ON monitoring_findings (visit_id);")
        )
        await db.execute(
            text("CREATE INDEX IF NOT EXISTS idx_monitoring_findings_status ON monitoring_findings (status);")
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_monitoring_visits_site_status_date "
                "ON monitoring_visits (site_id, status, visit_date_iso);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_monitoring_pre_visit_checklist_visit_id "
                "ON monitoring_pre_visit_checklist (visit_id);"
            )
        )
        await db.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_monitoring_documents_visit_id "
                "ON monitoring_documents (visit_id);"
            )
        )
        await db.commit()
        _TABLES_VERIFIED = True
    finally:
        await db.execute(
            text(
                "SELECT pg_advisory_unlock(:k1, :k2)"
            ),
            {"k1": _MONITOR_SCHEMA_ADVISORY_KEY[0], "k2": _MONITOR_SCHEMA_ADVISORY_KEY[1]},
        )


async def bootstrap_monitor_tables_at_startup() -> None:
    """Run monitor DDL once at application startup (Phase 3-D)."""
    from app.db import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await _ensure_monitor_tables(db)


def _status_from_risk(risk_level: str) -> str:
    risk = (risk_level or "").lower()
    if risk == "high":
        return "In Progress"
    if risk == "medium":
        return "Scheduled"
    return "Scheduled"


async def _require_monitoring_visit(db: AsyncSession, visit_id: str) -> None:
    """Ensure the visit exists. Demo auto-seed was removed — it inserted the same SITE-001 / April 28 row for every new visit id."""
    res = await db.execute(
        text("SELECT 1 FROM monitoring_visits WHERE id = :visit_id LIMIT 1"),
        {"visit_id": visit_id},
    )
    if res.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Visit not found")


# ── Visit Report Review Workflow ──────────────────────────────────────────────

class SubmitForReviewBody(BaseModel):
    reviewer_email: str = Field(..., min_length=1)
    message: Optional[str] = None
    author_email: Optional[str] = None


class SaveAnnotationBody(BaseModel):
    token: str = Field(..., min_length=1)
    highlighted_text: str = Field(..., min_length=1)
    dom_path: str = ""
    start_offset: int = 0
    end_offset: int = 0
    comment_text: str = Field(..., min_length=1)


class UpdateAnnotationBody(BaseModel):
    token: str = Field(..., min_length=1)
    comment_text: str = Field(..., min_length=1)


class AuthorReplyBody(BaseModel):
    author_reply: str = Field(..., min_length=1, max_length=5000)


class ApproveRejectBody(BaseModel):
    token: str = Field(..., min_length=1)
    reason: Optional[str] = None


async def _get_valid_token(db: AsyncSession, token: str, visit_id: str) -> Dict[str, Any]:
    """Validate a review token and return its row; raise 404/410 on failure."""
    tok_row = await db.execute(
        text(
            """
            SELECT id, is_valid, reviewer_email, author_email, message
            FROM monitoring_visit_review_tokens
            WHERE token = :token AND visit_id = :visit_id
            LIMIT 1
            """
        ),
        {"token": token, "visit_id": visit_id},
    )
    tok = tok_row.mappings().first()
    if not tok:
        raise HTTPException(status_code=404, detail="Review link not found or has expired")
    if not tok.get("is_valid"):
        raise HTTPException(status_code=410, detail="This review link has already been used or invalidated")
    return dict(tok)


async def _get_report_payload(db: AsyncSession, visit_id: str) -> Dict[str, Any]:
    rpt_row = await db.execute(
        text("SELECT payload FROM monitoring_visit_reports WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )
    rpt = rpt_row.mappings().first()
    if not rpt:
        return {}
    raw_pl = rpt.get("payload")
    if isinstance(raw_pl, dict):
        return dict(raw_pl)
    if isinstance(raw_pl, str):
        try:
            parsed = json.loads(raw_pl)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


async def _get_review_comments(db: AsyncSession, visit_id: str) -> List[Dict[str, Any]]:
    # Only return comments from the most recent review round (latest token). Each
    # submit-for-review creates a new token, so comments tied to older tokens belong to
    # prior rounds that the author has already addressed. Returning them would let the
    # author re-edit previously-fixed fields; scoping to the latest round keeps only the
    # currently-actionable comments (and their fields) editable.
    cmt_rows = await db.execute(
        text(
            """
            SELECT c.id, c.token_id, c.highlighted_text, c.dom_path,
                   c.start_offset, c.end_offset, c.comment_text,
                   c.author_reply, c.author_reply_at, c.created_at, c.updated_at
            FROM monitoring_visit_review_comments c
            WHERE c.visit_id = :visit_id
              AND c.token_id = (
                  SELECT t.id
                  FROM monitoring_visit_review_tokens t
                  WHERE t.visit_id = :visit_id
                  ORDER BY t.created_at DESC
                  LIMIT 1
              )
            ORDER BY c.created_at ASC
            """
        ),
        {"visit_id": visit_id},
    )
    comments = []
    for row in cmt_rows.mappings():
        cmt = dict(row)
        if cmt.get("id"):
            cmt["id"] = str(cmt["id"])
        if cmt.get("token_id"):
            cmt["token_id"] = str(cmt["token_id"])
        if cmt.get("created_at") and hasattr(cmt["created_at"], "isoformat"):
            cmt["created_at"] = cmt["created_at"].isoformat()
        if cmt.get("updated_at") and hasattr(cmt["updated_at"], "isoformat"):
            cmt["updated_at"] = cmt["updated_at"].isoformat()
        if cmt.get("author_reply_at") and hasattr(cmt["author_reply_at"], "isoformat"):
            cmt["author_reply_at"] = cmt["author_reply_at"].isoformat()
        comments.append(cmt)
    return comments




# ── AI Summary Generation ──────────────────────────────────────────────────────






# --- Dashboard cluster split-off (Phase 2.2f) -------------------------------
from app.modules.monitoring.routes.dashboard import router as _dashboard_router
router.include_router(_dashboard_router)

# --- Visits cluster split-off (Phase 2.2g) ----------------------------------
from app.modules.monitoring.routes.visits import router as _visits_router
router.include_router(_visits_router)

# --- Confirmation letter cluster split-off (Phase 2.2h) ---------------------
from app.modules.monitoring.routes.confirmation_letter import router as _confirmation_letter_router
router.include_router(_confirmation_letter_router)

# --- Reschedule cluster split-off (Phase 2.2i) ------------------------------
from app.modules.monitoring.routes.reschedule import router as _reschedule_router
router.include_router(_reschedule_router)

# --- Pre-visit cluster split-off (Phase 2.2j) -------------------------------
from app.modules.monitoring.routes.pre_visit import router as _pre_visit_router
router.include_router(_pre_visit_router)

# --- Post-visit + visit report cluster split-off (Phase 2.2k) ---------------
from app.modules.monitoring.routes.post_visit_and_report import router as _post_visit_and_report_router
router.include_router(_post_visit_and_report_router)

# --- Follow-up letter cluster split-off (Phase 2.2l) ------------------------
from app.modules.monitoring.routes.follow_up_letter import router as _follow_up_letter_router
router.include_router(_follow_up_letter_router)

# --- Close + acknowledge cluster split-off (Phase 2.2m) ---------------------
from app.modules.monitoring.routes.close_ack import router as _close_ack_router
router.include_router(_close_ack_router)

# --- Visit report review cluster split-off (Phase 2.2e) ---------------------
from app.modules.monitoring.routes.visit_report_review import router as _visit_report_review_router
router.include_router(_visit_report_review_router)

# --- Visit messaging cluster split-off (Phase 2.2d) -------------------------
from app.modules.monitoring.routes.visit_messaging import router as _visit_messaging_router
router.include_router(_visit_messaging_router)

# --- Findings cluster split-off (Phase 2.2c) ---------------------------------
from app.modules.monitoring.routes.findings import router as _findings_router
router.include_router(_findings_router)

# --- MVR templates split-off (Phase 2.2) -------------------------------------
# Helpers are re-exported so _persist_visit_report_payload + _sync_mvr_payload_with_template
# (which still live in this file) keep their unchanged call sites. Endpoints are
# mounted via include_router so /api/monitor/mvr-templates/* URLs are byte-identical.

# --- AI cluster split-off (Phase 2.2b) ---------------------------------------
from app.modules.monitoring.routes.ai import router as _ai_router
router.include_router(_ai_router)

from app.modules.monitoring.routes.mvr_templates import (
    _fetch_active_mvr_template_row,
    _fetch_mvr_template_row_by_id,
    _mvr_template_public,
    _next_mvr_template_version,
    router as _mvr_templates_router,
)
router.include_router(_mvr_templates_router)

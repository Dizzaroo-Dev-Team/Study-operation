"""REST API: monitoring visit findings (per-visit issue tracker)."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_optional
from app.db import get_db
from app.utils.log_sanitize import sfmt

router = APIRouter(tags=["monitor"])
logger = logging.getLogger(__name__)


# --- Private helpers --------------------------------------------------------

def _scoped_finding_id_prefix(visit_id: str) -> str:
    return f"{visit_id}__F-"


def _next_per_visit_finding_id(visit_id: str, existing_ids: Iterable[str]) -> str:
    """Sequential finding id per visit: {visit_id}__F-01, __F-02, ... (globally unique PK)."""
    prefix = _scoped_finding_id_prefix(visit_id)
    max_n = 0
    for raw in existing_ids:
        sid = str(raw or "")
        if sid.startswith(prefix):
            tail = sid[len(prefix) :]
            try:
                max_n = max(max_n, int(tail))
            except ValueError:
                continue
    return f"{visit_id}__F-{max_n + 1:02d}"


def _finding_id_sort_number(finding_id: str) -> int:
    m = re.search(r"__F-(\d+)$", str(finding_id))
    if m:
        return int(m.group(1))
    m2 = re.match(r"^F-(\d+)$", str(finding_id))
    if m2:
        return int(m2.group(1))
    return 0


def _due_color_for_severity(severity: str) -> str:
    s = (severity or "").strip().lower()
    if s == "critical":
        return "red"
    if s == "major":
        return "orange"
    return "muted"


# Lazy imports of cross-cluster helpers that still live in app.modules.monitoring.aggregator.
async def _ensure_tables(db: AsyncSession) -> None:
    from app.modules.monitoring.aggregator import _ensure_monitor_tables
    await _ensure_monitor_tables(db)


async def _require_visit(db: AsyncSession, visit_id: str) -> None:
    from app.modules.monitoring.aggregator import _require_monitoring_visit
    await _require_monitoring_visit(db, visit_id)


async def _append_activity(db: AsyncSession, visit_id: str, message: str, **kwargs) -> None:
    from app.modules.monitoring.aggregator import _append_visit_activity
    await _append_visit_activity(db, visit_id, message, **kwargs)


def _finding_display_code(finding_id: str) -> str:
    m = re.search(r"__F-(\d+)$", str(finding_id))
    if m:
        return f"F-{int(m.group(1)):02d}"
    if str(finding_id).startswith("F-"):
        return str(finding_id)
    return str(finding_id)


def _parse_finding_due_to_iso(due: Optional[str]) -> Optional[str]:
    """Map stored finding due_date strings to YYYY-MM-DD for Tasks, when possible."""
    raw_full = (due or "").strip()
    if not raw_full or raw_full.upper() == "TBD":
        return None
    now_y = datetime.now().year
    # ISO date or datetime prefix
    head = raw_full[:10]
    if len(head) == 10 and head[4] == "-" and head[7] == "-":
        for fmt in ("%Y-%m-%d",):
            try:
                return datetime.strptime(head, fmt).date().isoformat()
            except ValueError:
                break
    for fmt in ("%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw_full, fmt).date().isoformat()
        except ValueError:
            continue
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(raw_full, fmt).date().isoformat()
        except ValueError:
            continue
    for glue, fmt in ((f", {now_y}", "%b %d, %Y"), (f", {now_y}", "%B %d, %Y"), (f" {now_y}", "%b %d %Y"), (f" {now_y}", "%B %d %Y")):
        try:
            return datetime.strptime(raw_full + glue, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _compact_finding_task_copy(
    *,
    display_code: str,
    category: str,
    severity: str,
    description: str,
    subject_id: str,
    reference: str,
    site_address: str,
    assignee_name: str,
    due_date: str,
    visit_label: str,
    resolution: str,
) -> tuple[str, str]:
    """Short title + one-line body when LLM is unavailable or fails."""
    one = re.sub(r"\s+", " ", (description or "").strip())
    title = f"{category} ({severity})"
    if one:
        snippet = one[:52] + ("…" if len(one) > 52 else "")
        title = f"{title}: {snippet}"
    title = title[:100]

    meta: list[str] = [display_code]
    sid = (subject_id or "").strip()
    if sid:
        meta.append(f"Subj {sid}")
    ref = (reference or "").strip()
    if ref:
        meta.append(ref[:36] + ("…" if len(ref) > 36 else ""))
    due_s = (due_date or "").strip()
    if due_s and due_s.upper() != "TBD":
        meta.append(due_s[:22])
    who = (assignee_name or "").strip()
    if who:
        meta.append(who[:36])

    site_short = (site_address or "").strip()[:44]
    tail = site_short or visit_label
    res = (resolution or "").strip()
    res_bit = f" — {res[:64]}{'…' if len(res) > 64 else ''}" if res else ""

    body = " · ".join(meta) + f" @ {tail}{res_bit}"
    if len(body) > 260:
        body = body[:257] + "…"
    return title, body


async def _finding_task_title_and_description_llm_or_compact(
    *,
    display_code: str,
    category: str,
    severity: str,
    description: str,
    subject_id: str,
    reference: str,
    site_address: str,
    assignee_name: str,
    due_date: str,
    visit_id: str,
    visit_label: str,
    site_visit_number: Any,
    resolution: str,
    protocol: str,
    visit_date: str,
) -> tuple[str, str]:
    from app.modules.monitoring.aggregator import _rewrite_visit_id_in_text

    compact_title, compact_body = _compact_finding_task_copy(
        display_code=display_code,
        category=category,
        severity=severity,
        description=description,
        subject_id=subject_id,
        reference=reference,
        site_address=site_address,
        assignee_name=assignee_name,
        due_date=due_date,
        visit_label=visit_label,
        resolution=resolution,
    )

    def _finalize(title: str, body: str) -> tuple[str, str]:
        return (
            _rewrite_visit_id_in_text(title, visit_id, site_visit_number),
            _rewrite_visit_id_in_text(body, visit_id, site_visit_number),
        )

    from app.integrations.ai import ai_service

    if not ai_service.is_available():
        return _finalize(compact_title, compact_body)

    facts = {
        "finding": display_code,
        "visit": visit_label,
        "severity": severity,
        "category": category,
        "finding": (description or "").strip()[:800],
        "subject": (subject_id or "").strip(),
        "reference": (reference or "").strip()[:300],
        "assignee": (assignee_name or "").strip(),
        "due": (due_date or "").strip(),
        "site": (site_address or "").strip()[:200],
        "protocol": (protocol or "").strip(),
        "visitWhen": (visit_date or "").strip()[:120],
        "nextStep": (resolution or "").strip()[:400],
    }
    prompt = (
        "You write very short CRM tasks for clinical monitors.\n"
        'Return ONLY valid JSON with exactly two string keys: "title" and "description".\n'
        "Rules:\n"
        "- title: max 70 characters, plain text. Start with the severity (Critical, Major, or Minor), a colon, then a tight summary.\n"
        "- description: max 200 characters, plain text. One or two short sentences: what the finding is and what the assignee should do next.\n"
        "- When referring to a monitoring visit, use the provided visit label (e.g. Visit #1), never a long internal id.\n"
        "No markdown, bullets, field labels, or the word JSON.\n\n"
        f"Facts: {json.dumps(facts, ensure_ascii=False)}"
    )

    try:
        parsed = await ai_service.generate_json(prompt)
        if isinstance(parsed, dict):
            t = re.sub(r"\s+", " ", str(parsed.get("title") or "").strip())
            d = re.sub(r"\s+", " ", str(parsed.get("description") or "").strip())
            if t and d and len(t) >= 8:
                if len(t) > 72:
                    t = t[:69] + "…"
                if len(d) > 200:
                    d = d[:197] + "…"
                return _finalize(t, d)
    except Exception as exc:
        logger.debug("Finding task LLM summary failed, using compact copy: %s", exc, exc_info=True)

    return _finalize(compact_title, compact_body)


def _action_item_id_prefix(finding_id: str) -> str:
    return f"{finding_id}__AI-"


def _next_action_item_id(finding_id: str, existing_ids: Iterable[str]) -> str:
    prefix = _action_item_id_prefix(finding_id)
    max_n = 0
    for raw in existing_ids:
        sid = str(raw or "")
        if sid.startswith(prefix):
            tail = sid[len(prefix) :]
            try:
                max_n = max(max_n, int(tail))
            except ValueError:
                continue
    return f"{finding_id}__AI-{max_n + 1:02d}"


def _serialize_action_item_row(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "assignee": {
            "initials": row["assignee_initials"],
            "name": row["assignee_name"],
            "color": row["assignee_color"],
        },
        "dueDate": row["due_date"],
        "closedDate": row.get("closed_date") or "",
        "resolution": row.get("resolution") or "",
        "taskMode": row.get("task_mode") or None,
        "taskId": row.get("task_id") or None,
    }


def _normalize_action_items_payload(payload: Dict[str, Any]) -> list[Dict[str, str]]:
    """Extract action items from API payload; fall back to legacy single-item fields."""
    raw_items = payload.get("actionItems") or payload.get("action_items")
    if isinstance(raw_items, list) and raw_items:
        out: list[Dict[str, str]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            assignee = item.get("assignee") if isinstance(item.get("assignee"), dict) else {}
            out.append(
                {
                    "assigneeInitials": str(
                        item.get("assigneeInitials")
                        or assignee.get("initials")
                        or payload.get("assigneeInitials")
                        or "SC"
                    ).strip(),
                    "assigneeName": str(
                        item.get("assigneeName")
                        or assignee.get("name")
                        or payload.get("assigneeName")
                        or "Unassigned"
                    ).strip(),
                    "assigneeColor": str(
                        item.get("assigneeColor")
                        or assignee.get("color")
                        or payload.get("assigneeColor")
                        or "blue"
                    ).strip(),
                    "dueDate": str(item.get("dueDate") or item.get("due_date") or "TBD").strip() or "TBD",
                    "closedDate": str(item.get("closedDate") or item.get("closed_date") or "").strip(),
                    "resolution": str(item.get("resolution") or "").strip(),
                    "taskMode": str(item.get("taskMode") or item.get("task_mode") or "").strip(),
                    # Existing action items carry their own row id (e.g. F-01__AI-01) so
                    # _replace_finding_action_items can tell an edited item apart from a
                    # brand-new one and avoid re-creating its linked Task on every save.
                    "id": str(item.get("id") or "").strip(),
                }
            )
        if out:
            return out

    return [
        {
            "assigneeInitials": str(payload.get("assigneeInitials") or "SC").strip(),
            "assigneeName": str(payload.get("assigneeName") or "Unassigned").strip(),
            "assigneeColor": str(payload.get("assigneeColor") or "blue").strip(),
            "dueDate": str(payload.get("dueDate") or "TBD").strip() or "TBD",
            "closedDate": str(payload.get("closedDate") or payload.get("closed_date") or "").strip(),
            "resolution": str(payload.get("resolution") or "").strip(),
            "taskMode": str(payload.get("taskMode") or payload.get("task_mode") or "").strip(),
        }
    ]


async def _load_action_items_for_finding(db: AsyncSession, finding_id: str) -> list[Dict[str, Any]]:
    rows = await db.execute(
        text(
            """
            SELECT id, assignee_initials, assignee_name, assignee_color, due_date, closed_date, resolution, task_mode
            FROM monitoring_finding_action_items
            WHERE finding_id = :finding_id
            ORDER BY display_order ASC, id ASC
            """
        ),
        {"finding_id": finding_id},
    )
    items = [_serialize_action_item_row(r) for r in rows.mappings().all()]
    return items


async def _load_action_items_map(db: AsyncSession, finding_ids: Iterable[str]) -> Dict[str, list[Dict[str, Any]]]:
    ids = [str(i) for i in finding_ids if str(i or "").strip()]
    if not ids:
        return {}
    rows = await db.execute(
        text(
            """
            SELECT id, finding_id, assignee_initials, assignee_name, assignee_color, due_date, closed_date, resolution, task_mode
            FROM monitoring_finding_action_items
            WHERE finding_id = ANY(:finding_ids)
            ORDER BY finding_id ASC, display_order ASC, id ASC
            """
        ),
        {"finding_ids": ids},
    )
    out: Dict[str, list[Dict[str, Any]]] = {}
    for row in rows.mappings().all():
        fid = str(row["finding_id"])
        out.setdefault(fid, []).append(_serialize_action_item_row(row))
    return out


def _legacy_action_items_from_finding_row(row: Any) -> list[Dict[str, Any]]:
    return [
        {
            "id": f"{row['id']}__AI-01",
            "assignee": {
                "initials": row["assignee_initials"],
                "name": row["assignee_name"],
                "color": row["assignee_color"],
            },
            "dueDate": row["due_date"],
            "closedDate": row.get("closed_date") or "",
            "resolution": row.get("resolution") or "",
            "taskMode": None,
        }
    ]


async def _replace_finding_action_items(
    db: AsyncSession,
    finding_id: str,
    items: list[Dict[str, str]],
) -> list[Dict[str, Any]]:
    """Upsert a finding's action items.

    Action items that already existed (identified by the row id the client
    echoes back) keep their row and their linked `task_id` so re-saving a
    finding does not spawn a duplicate Task for an item that already has one.
    Only items with no matching existing row are treated as new and get a
    fresh id with no task_id (the caller is responsible for creating their
    Task and linking it back via `_link_task_to_action_item`).
    """
    current_rows = await db.execute(
        text("SELECT id, task_id FROM monitoring_finding_action_items WHERE finding_id = :finding_id"),
        {"finding_id": finding_id},
    )
    task_id_by_row_id: Dict[str, Optional[str]] = {
        str(r["id"]): r["task_id"] for r in current_rows.mappings().all()
    }
    existing_ids = list(task_id_by_row_id.keys())

    resolved: list[Dict[str, Any]] = []
    keep_ids: set[str] = set()
    for idx, item in enumerate(items):
        incoming_id = str(item.get("id") or "").strip()
        if incoming_id and incoming_id in task_id_by_row_id:
            row_id = incoming_id
            task_id = task_id_by_row_id[row_id]
        else:
            row_id = _next_action_item_id(finding_id, existing_ids)
            existing_ids.append(row_id)
            task_id = None
        keep_ids.add(row_id)
        resolved.append({"row_id": row_id, "task_id": task_id, "item": item, "display_order": idx})

    stale_ids = [rid for rid in task_id_by_row_id if rid not in keep_ids]
    if stale_ids:
        await db.execute(
            text(
                "DELETE FROM monitoring_finding_action_items "
                "WHERE finding_id = :finding_id AND id = ANY(:ids)"
            ),
            {"finding_id": finding_id, "ids": stale_ids},
        )

    saved: list[Dict[str, Any]] = []
    for row in resolved:
        item = row["item"]
        await db.execute(
            text(
                """
                INSERT INTO monitoring_finding_action_items (
                    id, finding_id, assignee_initials, assignee_name, assignee_color,
                    due_date, closed_date, resolution, task_mode, task_id, display_order
                ) VALUES (
                    :id, :finding_id, :assignee_initials, :assignee_name, :assignee_color,
                    :due_date, :closed_date, :resolution, :task_mode, :task_id, :display_order
                )
                ON CONFLICT (id) DO UPDATE SET
                    assignee_initials = EXCLUDED.assignee_initials,
                    assignee_name = EXCLUDED.assignee_name,
                    assignee_color = EXCLUDED.assignee_color,
                    due_date = EXCLUDED.due_date,
                    closed_date = EXCLUDED.closed_date,
                    resolution = EXCLUDED.resolution,
                    task_mode = EXCLUDED.task_mode,
                    display_order = EXCLUDED.display_order
                """
            ),
            {
                "id": row["row_id"],
                "finding_id": finding_id,
                "assignee_initials": item.get("assigneeInitials") or "SC",
                "assignee_name": item.get("assigneeName") or "Unassigned",
                "assignee_color": item.get("assigneeColor") or "blue",
                "due_date": item.get("dueDate") or "TBD",
                "closed_date": item.get("closedDate") or "",
                "resolution": item.get("resolution") or "",
                "task_mode": item.get("taskMode") or "",
                "task_id": row["task_id"],
                "display_order": row["display_order"],
            },
        )
        saved.append(
            {
                "id": row["row_id"],
                "assignee": {
                    "initials": item.get("assigneeInitials") or "SC",
                    "name": item.get("assigneeName") or "Unassigned",
                    "color": item.get("assigneeColor") or "blue",
                },
                "dueDate": item.get("dueDate") or "TBD",
                "closedDate": item.get("closedDate") or "",
                "resolution": item.get("resolution") or "",
                "taskMode": item.get("taskMode") or None,
                "taskId": row["task_id"],
            }
        )
    return saved


async def _link_task_to_action_item(row_id: str, task_id: str) -> None:
    """Stamp a freshly created Mongo Task's id back onto its action item row.

    Runs from a BackgroundTask, after the request's own `db` session has
    already been closed, so it opens a fresh session rather than reusing one.
    """
    from app.db.postgres import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        await db.execute(
            text("UPDATE monitoring_finding_action_items SET task_id = :task_id WHERE id = :id"),
            {"task_id": task_id, "id": row_id},
        )
        await db.commit()


def _serialize_finding(row: Any, action_items: list[Dict[str, Any]], visit_id: str) -> Dict[str, Any]:
    primary = action_items[0] if action_items else _legacy_action_items_from_finding_row(row)[0]
    return {
        "id": row["id"],
        "visitId": visit_id,
        "category": row["category"],
        "description": row["description"],
        "severity": row["severity"],
        "status": row["status"],
        "site": row["site"],
        "assignee": primary["assignee"],
        "dueDate": primary["dueDate"],
        "dueColor": row["due_color"],
        "resolution": primary.get("resolution") or "",
        "subjectId": (row.get("subject_id") or "").strip(),
        "reference": (row.get("reference") or "").strip(),
        "actionItems": action_items,
    }


async def _load_visit_context_for_tasks(db: AsyncSession, visit_id: str) -> Dict[str, Any]:
    from app.modules.monitoring.aggregator import _visit_label_from_site_number

    visit_row = await db.execute(
        text(
            """
            SELECT site_id, protocol, visit_date, site_address, site_visit_number
            FROM monitoring_visits
            WHERE id = :visit_id
            LIMIT 1
            """
        ),
        {"visit_id": visit_id},
    )
    v = visit_row.mappings().first() or {}
    site_visit_number = v.get("site_visit_number")
    return {
        "site_id": str(v.get("site_id") or "").strip(),
        "protocol": str(v.get("protocol") or "").strip(),
        "visit_date": str(v.get("visit_date") or "").strip(),
        "site_address": str(v.get("site_address") or "").strip(),
        "site_visit_number": site_visit_number,
        "visit_label": _visit_label_from_site_number(site_visit_number, visit_id),
    }


def _requested_by_from_user(current_user: Optional[dict]) -> Optional[str]:
    if not current_user:
        return None
    return (
        (current_user.get("name") or "").strip()
        or (current_user.get("displayName") or "").strip()
        or (current_user.get("email") or "").strip()
        or None
    )


async def _create_task_for_monitoring_finding_action_item(
    *,
    visit_id: str,
    finding_id: str,
    category: str,
    description: str,
    severity: str,
    assignee_name: str,
    due_date: str,
    resolution: str,
    subject_id: str,
    reference: str,
    site_id: str,
    protocol: str,
    visit_date: str,
    site_address: str,
    visit_label: str,
    site_visit_number: Any,
    task_mode: str = "",
    requested_by: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
) -> str:
    """Insert a global Tasks row (Mongo) summarizing a monitoring finding action item.

    Returns the new Task's id so the caller can link it back to the action
    item row it was created from.
    """
    from app.modules.operations.repositories import TaskRepository

    code = _finding_display_code(finding_id)

    title, body = await _finding_task_title_and_description_llm_or_compact(
        display_code=code,
        category=category,
        severity=severity,
        description=description,
        subject_id=subject_id,
        reference=reference,
        site_address=site_address,
        assignee_name=assignee_name,
        due_date=due_date,
        visit_id=visit_id,
        visit_label=visit_label,
        site_visit_number=site_visit_number,
        resolution=resolution,
        protocol=protocol,
        visit_date=visit_date,
    )

    task_data: Dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "title": title,
        "description": body,
        "status": "open",
        "assigneeName": (assignee_name or "").strip() or None,
        "assignedTo": (assignee_name or "").strip() or None,
        "role": "CRA",
        "taskMode": task_mode or None,
        "requestedBy": requested_by,
        "assigneeId": None,
        "createdByUserId": created_by_user_id,
        "links": {
            "siteId": site_id or None,
            "monitoringVisitId": visit_id,
            "monitoringReportId": None,
            "conversationId": None,
            "messageId": None,
        },
    }
    due_iso = _parse_finding_due_to_iso(due_date)
    if due_iso:
        task_data["dueDate"] = due_iso
    if site_id:
        task_data["siteId"] = site_id
    task_data["monitoringVisitId"] = visit_id

    await TaskRepository.create(task_data)
    return task_data["id"]


async def _background_create_tasks_for_finding(
    *,
    visit_id: str,
    finding_id: str,
    category: str,
    description: str,
    severity: str,
    subject_id: str,
    reference: str,
    site_id: str,
    protocol: str,
    visit_date: str,
    site_address: str,
    visit_label: str,
    site_visit_number: Any,
    action_items: list[Dict[str, Any]],
    requested_by: Optional[str] = None,
    created_by_user_id: Optional[str] = None,
) -> None:
    """Run after the finding API responds — LLM task summaries must not block the UI.

    `action_items` are serialized rows (see `_serialize_action_item_row`) that
    the caller has already filtered down to ones with no linked Task
    (`taskId` falsy), so this never creates a duplicate Task for an action
    item that already has one from a previous save.
    """
    for item in action_items:
        row_id = str(item.get("id") or "").strip()
        assignee = item.get("assignee") or {}
        try:
            task_id = await _create_task_for_monitoring_finding_action_item(
                visit_id=visit_id,
                finding_id=finding_id,
                category=category,
                description=description,
                severity=severity,
                assignee_name=str(assignee.get("name") or "Unassigned"),
                due_date=str(item.get("dueDate") or "TBD"),
                resolution=str(item.get("resolution") or ""),
                subject_id=subject_id,
                reference=reference,
                site_id=site_id,
                protocol=protocol,
                visit_date=visit_date,
                site_address=site_address,
                visit_label=visit_label,
                site_visit_number=site_visit_number,
                task_mode=str(item.get("taskMode") or ""),
                requested_by=requested_by,
                created_by_user_id=created_by_user_id,
            )
            if row_id and task_id:
                await _link_task_to_action_item(row_id, task_id)
        except Exception as exc:
            logger.warning(
                "Background task creation failed for finding %s action item (visit %s): %s",
                finding_id,
                visit_id,
                exc,
                exc_info=True,
            )


# --- Endpoints --------------------------------------------------------------

@router.get("/visits/{visit_id}/findings")
async def get_findings(visit_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    await _require_visit(db, visit_id)
    vst = await db.execute(
        text("SELECT status FROM monitoring_visits WHERE id = :visit_id LIMIT 1"),
        {"visit_id": visit_id},
    )
    vst_row = vst.mappings().first()
    if vst_row and str(vst_row.get("status") or "").strip().lower() == "archived":
        return []
    rows = await db.execute(text("SELECT * FROM monitoring_findings WHERE visit_id = :visit_id"), {"visit_id": visit_id})
    raw_rows = rows.mappings().all()
    action_map = await _load_action_items_map(db, [str(r["id"]) for r in raw_rows])
    findings = []
    for row in raw_rows:
        fid = str(row["id"])
        action_items = action_map.get(fid) or _legacy_action_items_from_finding_row(row)
        findings.append(_serialize_finding(row, action_items, visit_id))
    findings.sort(key=lambda item: _finding_id_sort_number(str(item["id"])))
    return findings


@router.post("/visits/{visit_id}/findings")
async def add_finding(
    visit_id: str,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    await _ensure_tables(db)
    id_rows = await db.execute(
        text("SELECT id FROM monitoring_findings WHERE visit_id = :visit_id"),
        {"visit_id": visit_id},
    )
    existing_ids = [str(r[0]) for r in id_rows.fetchall()]
    next_id = _next_per_visit_finding_id(visit_id, existing_ids)
    action_items = _normalize_action_items_payload(payload)
    primary = action_items[0]
    finding_text = str(payload.get("finding") or payload.get("description") or "").strip()
    await db.execute(
        text(
            """
            INSERT INTO monitoring_findings (
                id, visit_id, category, description, severity, status, site,
                assignee_initials, assignee_name, assignee_color, due_date, due_color, resolution, subject_id, reference
            ) VALUES (
                :id, :visit_id, :category, :description, :severity, 'Open', 'City Medical',
                :assignee_initials, :assignee_name, :assignee_color, :due_date, 'orange', :resolution, :subject_id, :reference
            );
            """
        ),
        {
            "id": next_id,
            "visit_id": visit_id,
            "category": payload.get("category", "General"),
            "description": finding_text,
            "severity": payload.get("severity", "Major"),
            "assignee_initials": primary.get("assigneeInitials", "SC"),
            "assignee_name": primary.get("assigneeName", "Unassigned"),
            "assignee_color": primary.get("assigneeColor", "blue"),
            "due_date": primary.get("dueDate", "TBD"),
            "resolution": primary.get("resolution", ""),
            "subject_id": str(payload.get("subjectId") or payload.get("subject_id") or "").strip()[:100],
            "reference": str(payload.get("reference") or "").strip()[:500],
        },
    )
    await _replace_finding_action_items(db, next_id, action_items)
    await _append_activity(
        db,
        visit_id,
        f"Added finding {next_id}: {payload.get('category', 'General')}",
        initials=primary.get("assigneeInitials", "SC"),
        color=primary.get("assigneeColor", "blue"),
    )
    await db.commit()

    created_row_res = await db.execute(
        text("SELECT * FROM monitoring_findings WHERE id = :finding_id AND visit_id = :visit_id"),
        {"finding_id": next_id, "visit_id": visit_id},
    )
    created_row = created_row_res.mappings().first()
    created_action_items = await _load_action_items_for_finding(db, next_id)

    visit_ctx = await _load_visit_context_for_tasks(db, visit_id)
    category = str(payload.get("category", "General") or "General")
    description = finding_text
    severity = str(payload.get("severity", "Major") or "Major")
    subject_id = str(payload.get("subjectId") or payload.get("subject_id") or "").strip()[:100]
    reference = str(payload.get("reference") or "").strip()[:500]

    requested_by = _requested_by_from_user(current_user)
    created_by_user_id = (current_user or {}).get("user_id")

    # A brand-new finding's action items never have a linked Task yet, but
    # filter on taskId anyway so this stays correct if that ever changes.
    new_action_items = [ai for ai in created_action_items if not ai.get("taskId")]
    if new_action_items:
        background_tasks.add_task(
            _background_create_tasks_for_finding,
            visit_id=visit_id,
            finding_id=next_id,
            category=category,
            description=description,
            severity=severity,
            subject_id=subject_id,
            reference=reference,
            site_id=visit_ctx["site_id"],
            protocol=visit_ctx["protocol"],
            visit_date=visit_ctx["visit_date"],
            site_address=visit_ctx["site_address"],
            visit_label=visit_ctx["visit_label"],
            site_visit_number=visit_ctx["site_visit_number"],
            action_items=new_action_items,
            requested_by=requested_by,
            created_by_user_id=created_by_user_id,
        )

    # Public Notice Board: a new finding on a visit is a real site event the
    # rest of the team should see. Look up the visit's site/study so the
    # notice lands on the right board. Best-effort.
    try:
        from app.utils.system_notices import post_site_event_notice
        info = (
            await db.execute(
                text(
                    "SELECT site_id, study_id, site_visit_number "
                    "FROM monitoring_visits WHERE id = :id"
                ),
                {"id": visit_id},
            )
        ).mappings().first()
        if info and info.get("site_id"):
            cat = payload.get("category", "General") or "General"
            sev = payload.get("severity", "Major") or "Major"
            desc = finding_text
            short = (desc[:80] + "…") if len(desc) > 80 else desc
            num = info.get("site_visit_number")
            visit_label = f"visit #{num}" if num else "visit"
            await post_site_event_notice(
                db,
                site_ref=info["site_id"],
                study_ref=info.get("study_id"),
                event_type="monitoring_finding_created",
                message=(
                    f"Finding {next_id} ({cat}, {sev}) added to {visit_label}"
                    + (f": {short}" if short else ".")
                ),
                metadata={
                    "visit_id": visit_id,
                    "finding_id": next_id,
                    "category": cat,
                    "severity": sev,
                    "assignee_name": payload.get("assigneeName"),
                    "due_date": payload.get("dueDate"),
                },
            )
    except Exception:
        logger.exception("add_finding: notice-board hook failed for visit %s", sfmt(visit_id))

    if created_row:
        return _serialize_finding(created_row, created_action_items, visit_id)
    return {"id": next_id}


@router.patch("/visits/{visit_id}/findings/{finding_id}")
async def patch_finding(
    visit_id: str,
    finding_id: str,
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    current_user: Optional[dict] = Depends(get_current_user_optional),
):
    await _ensure_tables(db)
    row = await db.execute(
        text(
            "SELECT * FROM monitoring_findings WHERE id = :finding_id AND visit_id = :visit_id"
        ),
        {"finding_id": finding_id, "visit_id": visit_id},
    )
    cur = row.mappings().first()
    if not cur:
        # Fallback: if client is holding a stale visit_id while the finding id is valid,
        # still allow editing by resolving the finding to its actual visit.
        by_id = await db.execute(
            text("SELECT * FROM monitoring_findings WHERE id = :finding_id"),
            {"finding_id": finding_id},
        )
        cur = by_id.mappings().first()
        if not cur:
            raise HTTPException(status_code=404, detail="Finding not found")
        visit_id = str(cur["visit_id"])

    category = (payload.get("category") if payload.get("category") is not None else cur["category"]) or "General"
    description = (
        payload.get("finding")
        if payload.get("finding") is not None
        else payload.get("description")
        if payload.get("description") is not None
        else cur["description"]
    ) or ""
    severity = (payload.get("severity") if payload.get("severity") is not None else cur["severity"]) or "Major"
    status_val = (payload.get("status") if payload.get("status") is not None else cur["status"]) or "Open"
    resolution = payload.get("resolution") if "resolution" in payload else cur["resolution"]
    if resolution is None:
        resolution = ""

    if "subjectId" in payload or "subject_id" in payload:
        subject_id_val = str(payload.get("subjectId") or payload.get("subject_id") or "").strip()[:100]
    else:
        subject_id_val = str(cur.get("subject_id") or "").strip()[:100]

    if "reference" in payload:
        reference_val = str(payload.get("reference") or "").strip()[:500]
    else:
        reference_val = str(cur.get("reference") or "").strip()[:500]

    initials = payload.get("assigneeInitials") if payload.get("assigneeInitials") is not None else cur["assignee_initials"]
    name = payload.get("assigneeName") if payload.get("assigneeName") is not None else cur["assignee_name"]
    color = payload.get("assigneeColor") if payload.get("assigneeColor") is not None else cur["assignee_color"]
    due_date = payload.get("dueDate") if payload.get("dueDate") is not None else cur["due_date"]
    if due_date is None:
        due_date = "TBD"

    action_items_payload_present = "actionItems" in payload or "action_items" in payload
    if action_items_payload_present:
        normalized_items = _normalize_action_items_payload(payload)
        primary = normalized_items[0]
        initials = primary.get("assigneeInitials") or initials
        name = primary.get("assigneeName") or name
        color = primary.get("assigneeColor") or color
        due_date = primary.get("dueDate") or due_date
        resolution = primary.get("resolution") or resolution

    due_color = _due_color_for_severity(severity)

    await db.execute(
        text(
            """
            UPDATE monitoring_findings SET
                category = :category,
                description = :description,
                severity = :severity,
                status = :status,
                assignee_initials = :assignee_initials,
                assignee_name = :assignee_name,
                assignee_color = :assignee_color,
                due_date = :due_date,
                due_color = :due_color,
                resolution = :resolution,
                subject_id = :subject_id,
                reference = :reference
            WHERE id = :finding_id AND visit_id = :visit_id
            """
        ),
        {
            "finding_id": finding_id,
            "visit_id": visit_id,
            "category": category,
            "description": description,
            "severity": severity,
            "status": status_val,
            "assignee_initials": initials or "SC",
            "assignee_name": name or "Unassigned",
            "assignee_color": color or "blue",
            "due_date": due_date,
            "due_color": due_color,
            "resolution": resolution or "",
            "subject_id": subject_id_val,
            "reference": reference_val,
        },
    )

    saved_action_items: list[Dict[str, Any]]
    if action_items_payload_present:
        saved_action_items = await _replace_finding_action_items(db, finding_id, normalized_items)
    else:
        saved_action_items = await _load_action_items_for_finding(db, finding_id)
        if not saved_action_items:
            saved_action_items = _legacy_action_items_from_finding_row(cur)

    await _append_activity(db, visit_id, f"Updated finding {finding_id}")
    await db.commit()

    # Editing a finding can add new action items (e.g. a second responsible
    # person/action). Only items with no linked Task yet get one created here
    # — items that already have a task_id from a prior save are skipped so
    # re-saving doesn't spawn duplicate Tasks.
    new_action_items = [ai for ai in saved_action_items if not ai.get("taskId")] if action_items_payload_present else []
    if new_action_items:
        visit_ctx = await _load_visit_context_for_tasks(db, visit_id)
        requested_by = _requested_by_from_user(current_user)
        created_by_user_id = (current_user or {}).get("user_id")
        background_tasks.add_task(
            _background_create_tasks_for_finding,
            visit_id=visit_id,
            finding_id=finding_id,
            category=category,
            description=description,
            severity=severity,
            subject_id=subject_id_val,
            reference=reference_val,
            site_id=visit_ctx["site_id"],
            protocol=visit_ctx["protocol"],
            visit_date=visit_ctx["visit_date"],
            site_address=visit_ctx["site_address"],
            visit_label=visit_ctx["visit_label"],
            site_visit_number=visit_ctx["site_visit_number"],
            action_items=new_action_items,
            requested_by=requested_by,
            created_by_user_id=created_by_user_id,
        )

    return {
        "id": finding_id,
        "visit_id": visit_id,
        "category": category,
        "description": description,
        "severity": severity,
        "status": status_val,
        "site": cur["site"],
        "assignee": {
            "initials": initials or "SC",
            "name": name or "Unassigned",
            "color": color or "blue",
        },
        "dueDate": due_date,
        "dueColor": due_color,
        "resolution": resolution or "",
        "subjectId": subject_id_val,
        "reference": reference_val,
        "actionItems": saved_action_items,
    }


@router.patch("/visits/{visit_id}/findings/{finding_id}/resolve")
async def resolve_finding(visit_id: str, finding_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    await db.execute(
        text("UPDATE monitoring_findings SET status = 'resolved' WHERE id = :finding_id AND visit_id = :visit_id"),
        {"finding_id": finding_id, "visit_id": visit_id},
    )
    await _append_activity(db, visit_id, f"Resolved finding {finding_id}")
    await db.commit()

    # Kafka: a resolved monitoring finding publishes MONITORING_FINDING_CLOSED
    # and FINDING_CLOSED to the Data Platform. The site_id lives on the parent
    # visit, so resolve it via visit_id. Best-effort & self-guarded — never
    # breaks the already-committed resolve.
    try:
        from app.integrations.milestones_kafka import publish_site_milestone, SiteMilestone

        site_row = (
            await db.execute(
                text("SELECT site_id FROM monitoring_visits WHERE id = :id"),
                {"id": visit_id},
            )
        ).mappings().first()
        if site_row and site_row.get("site_id"):
            site_id = str(site_row["site_id"])
            await publish_site_milestone(SiteMilestone.MONITORING_FINDING_CLOSED, site_id=site_id)
            await publish_site_milestone(SiteMilestone.FINDING_CLOSED, site_id=site_id)
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "resolve_finding: milestone Kafka hook failed for finding %s", sfmt(finding_id)
        )

    return {"status": "resolved"}


@router.delete("/visits/{visit_id}/findings/{finding_id}")
async def delete_finding(visit_id: str, finding_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    await db.execute(text("DELETE FROM monitoring_findings WHERE id = :finding_id AND visit_id = :visit_id"), {"finding_id": finding_id, "visit_id": visit_id})
    await _append_activity(db, visit_id, f"Deleted finding {finding_id}")
    await db.commit()
    return {"status": "deleted"}

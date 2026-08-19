"""Display helpers for CRM tasks linked to monitoring visits."""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.monitoring.aggregator import _visit_label_from_site_number

MON_VISIT_ID_RE = re.compile(r"MON-\d{14}-\d{6}")


def _collect_visit_ids_from_tasks(tasks: Iterable[dict]) -> list[str]:
    ids: set[str] = set()
    for task in tasks:
        raw = task.get("monitoringVisitId")
        if not raw and isinstance(task.get("links"), dict):
            raw = task["links"].get("monitoringVisitId")
        if raw:
            ids.add(str(raw).strip())
        for field in ("title", "description"):
            val = str(task.get(field) or "")
            for match in MON_VISIT_ID_RE.findall(val):
                ids.add(match)
    return sorted(i for i in ids if i)


async def monitoring_visit_label_map(db: AsyncSession, visit_ids: Iterable[str]) -> Dict[str, str]:
    """Map opaque MON-… visit ids to human labels like Visit #1."""
    ids = sorted({str(v).strip() for v in visit_ids if str(v or "").strip()})
    if not ids:
        return {}
    rows = await db.execute(
        text("SELECT id, site_visit_number FROM monitoring_visits WHERE id = ANY(:ids)"),
        {"ids": ids},
    )
    out: Dict[str, str] = {}
    for row in rows.mappings().all():
        vid = str(row["id"])
        label = _visit_label_from_site_number(row.get("site_visit_number"), vid)
        if label != vid:
            out[vid] = label
    return out


def rewrite_task_doc_visit_labels(task: dict, label_map: Dict[str, str]) -> dict:
    if not label_map:
        return task
    updated = dict(task)
    for field in ("title", "description"):
        val = updated.get(field)
        if not val:
            continue
        text_val = str(val)
        for visit_id, label in label_map.items():
            text_val = text_val.replace(visit_id, label)
        updated[field] = text_val
    return updated


async def rewrite_tasks_for_display(db: AsyncSession, tasks: List[dict]) -> List[dict]:
    label_map = await monitoring_visit_label_map(db, _collect_visit_ids_from_tasks(tasks))
    if not label_map:
        return tasks
    return [rewrite_task_doc_visit_labels(t, label_map) for t in tasks]

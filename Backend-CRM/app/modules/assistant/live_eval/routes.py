"""Read-only live-eval score surface for the in-house dashboard.

Deliberately READ-ONLY: the table is append-only (ALCOA+) and rows are written
exclusively by the background scorer. Nothing here mutates. Auth-guarded like
every other assistant route. No external dashboard — this feeds our own
frontend page only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select

from app.auth import get_current_user
from app.db import AsyncSessionLocal
from app.modules.assistant.live_eval.models import LiveEvalScore

router = APIRouter(prefix="/assistant/live-evals", tags=["Assistant live evals"])


def _row_summary(row: LiveEvalScore) -> dict:
    return {
        "id": str(row.id),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "user_id": row.user_id,
        "session_id": row.session_id,
        "message_preview": row.message_preview,
        "scored_mode": row.scored_mode,
        "judge_model": row.judge_model,
        "overall_passed": row.overall_passed,
        "metrics": [
            {"name": m.get("name"), "score": m.get("score"),
             "passed": m.get("passed"), "applicable": m.get("applicable", True)}
            for m in (row.metrics or [])
        ],
    }


@router.get("/status")
async def status(current_user: dict = Depends(get_current_user)):
    """Current flags so the dashboard can show honest banners."""
    from app.config import settings

    return {
        "enabled": bool(settings.enable_live_evals),
        "judge_enabled": bool(settings.enable_live_judge),
        "judge_model": settings.live_eval_judge_model,
        "sample_rate": float(settings.live_eval_sample_rate),
    }


@router.get("/scores")
async def list_scores(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    metric: Optional[str] = Query(None, description="Only turns that ran this metric"),
    failing_only: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    async with AsyncSessionLocal() as db:
        q = select(LiveEvalScore).order_by(LiveEvalScore.created_at.desc())
        if failing_only:
            q = q.where(LiveEvalScore.overall_passed.is_(False))
        q = q.offset(offset).limit(limit * 3 if metric else limit)
        rows = (await db.execute(q)).scalars().all()
    out = []
    for row in rows:
        if metric and not any(m.get("name") == metric for m in (row.metrics or [])):
            continue
        out.append(_row_summary(row))
        if len(out) >= limit:
            break
    return out


@router.get("/scores/{score_id}")
async def get_score(score_id: str, current_user: dict = Depends(get_current_user)):
    """Full detail — per-metric score, pass/fail AND the judge/check reason."""
    import uuid as _uuid

    try:
        score_uuid = _uuid.UUID(score_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="score not found")
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            select(LiveEvalScore).where(LiveEvalScore.id == score_uuid)
        )).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="score not found")
    data = _row_summary(row)
    data["answer_preview"] = row.answer_preview
    data["metrics"] = row.metrics or []   # full entries, including reasons
    return data


@router.get("/summary")
async def summary(
    hours: int = Query(24, ge=1, le=24 * 14),
    current_user: dict = Depends(get_current_user),
):
    """Pass-rate trend (hourly buckets) + per-metric aggregates for the window."""
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    async with AsyncSessionLocal() as db:
        rows = (await db.execute(
            select(LiveEvalScore)
            .where(LiveEvalScore.created_at >= since)
            .order_by(LiveEvalScore.created_at.asc())
            .limit(5000)
        )).scalars().all()

    buckets: dict = {}
    per_metric: dict = {}
    for row in rows:
        ts = row.created_at
        bucket = ts.replace(minute=0, second=0, microsecond=0).isoformat()
        b = buckets.setdefault(bucket, {"bucket": bucket, "total": 0, "passed": 0})
        b["total"] += 1
        b["passed"] += 1 if row.overall_passed else 0
        for m in (row.metrics or []):
            if not m.get("applicable", True):
                continue
            pm = per_metric.setdefault(m.get("name"), {"total": 0, "passed": 0})
            pm["total"] += 1
            pm["passed"] += 1 if m.get("passed") else 0
    return {
        "window_hours": hours,
        "turns_scored": len(rows),
        "trend": sorted(buckets.values(), key=lambda b: b["bucket"]),
        "per_metric": per_metric,
    }

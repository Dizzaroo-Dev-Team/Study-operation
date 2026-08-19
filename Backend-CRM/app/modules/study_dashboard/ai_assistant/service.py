"""
End-to-end AI assistant orchestrator.

Pipeline:
  1. Ask Gemini for { status, narrative, sql, chart, reason_if_no_data }.
  2. If the LLM says "no_data" → return immediately.
  3. Validate + normalize the SQL via sql_guard.
  4. Execute inside a SET-TRANSACTION-READ-ONLY transaction with an 8s
     statement timeout against study_db_01. Always rolls back.
  5. Coerce JSON-unsafe scalars (dates, decimals, datetimes) to strings/floats
     so the response serialises cleanly.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from ..schemas import (
    AssistantData,
    AssistantResponse,
    ChartSpec,
)
from .llm import call_llm
from .sdtm_schema import get_allowed_tables
from .sql_guard import SqlGuardError, validate_and_normalize_sql

logger = logging.getLogger(__name__)

_STATEMENT_TIMEOUT = "8s"
_HARD_ROW_CAP = 1000


def _coerce(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _coerce_chart(raw: Any) -> Optional[ChartSpec]:
    if not isinstance(raw, dict):
        return None
    try:
        return ChartSpec(
            type=raw.get("type") or "table",
            title=str(raw.get("title") or "Result"),
            x_field=raw.get("x_field"),
            y_field=raw.get("y_field"),
            series_field=raw.get("series_field"),
            value_field=raw.get("value_field"),
        )
    except Exception:  # pydantic ValidationError or anything funky
        return None


async def answer_query(
    session: AsyncSession,
    question: str,
    history: Optional[list[dict]] = None,
) -> AssistantResponse:
    if not question or not question.strip():
        return AssistantResponse(
            status="rejected",
            reason="Empty question.",
        )

    # ── 1. LLM call ─────────────────────────────────────────────────────────
    try:
        llm_out = await call_llm(question, history)
    except Exception as exc:
        logger.exception("LLM call failed")
        return AssistantResponse(status="execution_error", reason=f"LLM error: {exc}")

    status = str(llm_out.get("status", "")).lower()
    narrative = llm_out.get("narrative")
    raw_sql = llm_out.get("sql")
    chart = _coerce_chart(llm_out.get("chart"))
    reason_if_no_data = llm_out.get("reason_if_no_data")

    # ── 2. no_data short-circuit ────────────────────────────────────────────
    if status == "no_data" or not raw_sql:
        return AssistantResponse(
            status="no_data",
            narrative=narrative,
            reason=reason_if_no_data or "The schema does not contain the data needed to answer this question.",
        )

    # ── 3. Validate SQL ─────────────────────────────────────────────────────
    try:
        normalized_sql = validate_and_normalize_sql(raw_sql, get_allowed_tables())
    except SqlGuardError as guard_err:
        return AssistantResponse(
            status="rejected",
            narrative=narrative,
            sql=raw_sql,
            reason=str(guard_err),
        )

    # ── 4. Execute inside read-only transaction ─────────────────────────────
    started = time.perf_counter()
    try:
        async with session.begin():
            await session.execute(text("SET TRANSACTION READ ONLY"))
            await session.execute(text(f"SET LOCAL statement_timeout = '{_STATEMENT_TIMEOUT}'"))
            result = await session.execute(text(normalized_sql))
            columns = list(result.keys())
            raw_rows = result.fetchall()
    except SQLAlchemyError as db_err:
        return AssistantResponse(
            status="execution_error",
            narrative=narrative,
            sql=normalized_sql,
            chart=chart,
            reason=str(db_err.orig) if getattr(db_err, "orig", None) else str(db_err),
        )

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # Defensive cap (LIMIT clause should already cover this)
    if len(raw_rows) > _HARD_ROW_CAP:
        raw_rows = raw_rows[:_HARD_ROW_CAP]

    rows = [[_coerce(v) for v in row] for row in raw_rows]

    return AssistantResponse(
        status="ok",
        narrative=narrative,
        sql=normalized_sql,
        chart=chart,
        data=AssistantData(columns=columns, rows=rows),
        row_count=len(rows),
        elapsed_ms=elapsed_ms,
    )

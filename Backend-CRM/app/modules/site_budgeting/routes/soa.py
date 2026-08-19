"""REST API: Schedule of Activities (SoA) import + AI-driven preview/apply visit-matrix generation."""
from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import (
    BudgetLineItem,
    BudgetVisitMatrix,
    CostElement,
    VisitSchedule,
)
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import budget_totals_cache

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Site Budgeting"])


@router.post("/templates/{template_id}/soa-import")
async def soa_import(
    template_id: UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Parse an uploaded Schedule of Activities file (JSON, XML, CSV, or plain text)
    and use an LLM to map SOA assessments to cost elements in the catalog.

    Returns suggested visits, activity-based fee mappings, milestone mappings,
    unmatched items, and low-confidence flags - all for user review before import.
    """
    import json as _json

    content_bytes = await file.read()
    soa_text = content_bytes.decode("utf-8", errors="replace")

    # Load all active cost elements to give the LLM context
    result = await db.execute(
        select(CostElement).where(CostElement.is_active == True).order_by(CostElement.code)
    )
    all_elements = result.scalars().all()
    elements_list = [
        {"code": e.code, "name": e.name, "cost_type": e.cost_type or "PER_VISIT"}
        for e in all_elements
    ]

    elements_json_str = _json.dumps(elements_list, indent=2)
    prompt = f"""You are an expert clinical trial budget analyst.

Below is a Schedule of Activities (SOA) document from a clinical trial protocol.
It may be a table, JSON, XML, or text description.

Your task:
1. Extract all VISIT names/labels (e.g., Screening, Day 1, Week 4, End of Treatment).
2. Extract all ASSESSMENT/PROCEDURE rows (e.g., ECG, Vital Signs, Blood Draw, PK Sample).
3. For each assessment, determine which visit(s) it occurs in.
4. Map each assessment to the most appropriate cost element from the catalog below.
5. Classify each assessment as ACTIVITY (per-visit fee) or MILESTONE (fixed event-based fee).
6. Flag items where you have low confidence (< 0.75) in the mapping.
7. List any SOA items with no good match in the catalog as "unmatched".

COST ELEMENT CATALOG (code, name, cost_type):
{elements_json_str}

SCHEDULE OF ACTIVITIES INPUT:
---
{soa_text[:8000]}
---

Respond ONLY with valid JSON in this exact structure:
{{
  "visits": ["Visit name 1", "Visit name 2"],
  "activity_mappings": [
    {{
      "soa_item": "ECG",
      "cost_element_code": "ECG-001",
      "cost_element_name": "12-Lead ECG",
      "visit_flags": ["Screening", "Day 1"],
      "confidence": 0.95,
      "notes": ""
    }}
  ],
  "milestone_mappings": [
    {{
      "soa_item": "Site Initiation Visit",
      "cost_element_code": "SIV-001",
      "cost_element_name": "Site Initiation Visit",
      "confidence": 0.90,
      "notes": ""
    }}
  ],
  "unmatched": ["Novel Assessment XYZ"],
  "low_confidence_items": ["PK Sample Collection"]
}}"""

    # Try Gemini first, fall back to returning a parse-error response
    llm_response: dict = {}
    llm_error: str | None = None

    try:
        import google.generativeai as genai  # type: ignore
        import os

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        genai.configure(api_key=api_key)

        preferred_models = [
            os.environ.get("GOOGLE_GEMINI_MODEL", ""),
            "gemini-3.5-flash",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
        ]

        model = None
        for model_id in preferred_models:
            if not model_id:
                continue
            try:
                model = genai.GenerativeModel(model_id)
                break
            except Exception:
                continue

        if model is None:
            raise ValueError("No Gemini model could be initialized")

        # genai.generate_content is sync and can take 5-30s; offload to the
        # default thread executor so the event loop is free to serve other
        # requests during the SoA import. Without this every concurrent SoA
        # import serialized at one-per-process.
        response = await asyncio.get_running_loop().run_in_executor(
            None, lambda: model.generate_content(prompt)
        )
        raw_text = response.text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            raw_text = raw_text.split("```", 2)[1]
            if raw_text.startswith("json"):
                raw_text = raw_text[4:]
            if raw_text.endswith("```"):
                raw_text = raw_text[:-3]
            raw_text = raw_text.strip()

        llm_response = _json.loads(raw_text)

    except Exception as exc:
        llm_error = str(exc)
        llm_response = {
            "visits": [],
            "activity_mappings": [],
            "milestone_mappings": [],
            "unmatched": [],
            "low_confidence_items": [],
        }

    return {
        "template_id": str(template_id),
        "filename": file.filename,
        "llm_error": llm_error,
        **llm_response,
    }


# --- SoA -> Visit Matrix (AI maps activities -> cost elements only) ---------

@router.get("/generate/soa-ids")
async def list_soa_study_ids(
    trial_id: UUID | None = None,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Return the studies available in the MongoDB SoA collection, enriched with the
    human-readable study **name** from the CRM ``studies`` table (SoA only stores
    the protocol id), for UI autocomplete + presence checks.

    When ``trial_id`` is supplied, also resolve that study's external id + name and
    whether it exists in the SoA database, so the UI can auto-fill / show a banner.

    The SoA cluster is an *external* dependency; if it is unconfigured or
    unreachable we must not 500 the whole Budget Configuration screen. Degrade
    gracefully to an empty list plus an ``error`` string.
    """
    from app.models.study import Study
    from app.modules.site_budgeting.services.mongo_service import list_soa_ids

    # 1. Distinct protocol ids from Mongo (graceful on outage).
    try:
        soa_ids = await list_soa_ids()
    except Exception as exc:  # RuntimeError (unconfigured) or pymongo connection errors
        logger.warning("[SOA_MONGO] soa-ids lookup failed: %s", exc)
        # Still resolve the selected study's name so the banner can render.
        selected = await _resolve_selected_study(db, trial_id, soa_id_set=set())
        return {"studies": [], "selected": selected, "available": False, "error": str(exc)}

    # 2. Map external study_id -> name from the CRM studies table.
    name_by_extid: dict[str, str] = {}
    if soa_ids:
        rows = (
            await db.execute(
                select(Study.study_id, Study.name).where(Study.study_id.in_(soa_ids))
            )
        ).all()
        name_by_extid = {sid: nm for sid, nm in rows}

    studies = [
        {"study_id": sid, "name": name_by_extid.get(sid), "in_crm": sid in name_by_extid}
        for sid in soa_ids
    ]

    selected = await _resolve_selected_study(
        db, trial_id, soa_id_set={s.lower() for s in soa_ids}
    )
    return {"studies": studies, "selected": selected, "available": True, "error": None}


async def _resolve_selected_study(
    db: AsyncSession, trial_id: UUID | None, soa_id_set: set[str]
) -> dict[str, Any] | None:
    """Resolve a budgeting trial_id (studies.id) to its external id + name + SoA presence."""
    if trial_id is None:
        return None
    from app.models.study import Study

    row = (
        await db.execute(select(Study.study_id, Study.name).where(Study.id == trial_id))
    ).first()
    if not row:
        return None
    ext_id, name = row
    return {
        "trial_id": str(trial_id),
        "study_id": ext_id,
        "name": name,
        "in_soa": bool(ext_id) and str(ext_id).lower() in soa_id_set,
    }


@router.get("/generate/soa-debug", include_in_schema=False)
async def debug_soa_mongo():
    """Debug (no auth): scan Atlas cluster, find scheduleofactivities."""
    from app.modules.site_budgeting.services.mongo_service import debug_scan
    return await debug_scan()


@router.post("/generate/{study_id}/preview")
async def soa_matrix_preview(
    study_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Step 1 of 2: Fetch SoA from MongoDB, use AI to map activities -> cost_element codes.
    Returns a preview of the visit matrix plan - nothing written to DB.

    Frontend shows the mapping table, user can confirm or adjust, then calls /apply.
    """
    from app.modules.site_budgeting.services.mongo_service import fetch_soa
    from app.modules.site_budgeting.services.ai_budget_service import generate_matrix_preview

    soa_doc = await fetch_soa(study_id)
    if not soa_doc:
        raise HTTPException(
            status_code=404,
            detail=f"No SoA found for protocolId/study_id='{study_id}'.",
        )

    els_q = await db.execute(
        select(CostElement).where(CostElement.is_active == True)
    )
    elements = [
        {"code": el.code, "name": el.name, "cost_type": el.cost_type or ""}
        for el in els_q.scalars().all()
    ]

    try:
        result = await generate_matrix_preview(soa_doc, elements)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return result


class SoaApplyBody(BaseModel):
    template_id: UUID
    matrix_plan: list[dict[str, Any]]  # [{visit_name, element_code, quantity}]


@router.post("/generate/{study_id}/apply")
async def soa_matrix_apply(
    study_id: str,
    body: SoaApplyBody,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Step 2 of 2: Apply the confirmed matrix plan to the database.

    For each (visit_name, element_code, quantity) in matrix_plan:
      1. Find or create VisitSchedule row (trial-scoped)
      2. Find or create BudgetLineItem for cost_element in template
      3. Upsert BudgetVisitMatrix (line_item_id, visit_id, units)

    The existing cost engine then computes all totals - no costs are set here.
    """
    template_id = body.template_id

    tmpl = await repo.get_template(db, template_id)
    if not tmpl:
        raise HTTPException(status_code=404, detail="Template not found")

    trial_id = tmpl.trial_id

    all_els = await db.execute(select(CostElement).where(CostElement.is_active == True))
    code_to_el: dict[str, CostElement] = {el.code: el for el in all_els.scalars().all()}

    inserted_visits = 0
    inserted_lines = 0
    inserted_cells = 0
    skipped = 0

    # Deduplicate: multiple activities may map to the same element for the same visit.
    # Keep the highest quantity for each (visit_name, element_code) pair.
    deduped: dict[tuple[str, str], Decimal] = {}
    for row in body.matrix_plan:
        vn = str(row.get("visit_name") or "").strip()
        ec = str(row.get("element_code") or "").strip()
        qty = Decimal(str(row.get("quantity") or 1))
        if vn and ec:
            key = (vn, ec)
            deduped[key] = max(deduped.get(key, Decimal("0")), qty)
        else:
            skipped += 1

    for (visit_name, element_code), quantity in deduped.items():
        el = code_to_el.get(element_code)
        if not el:
            skipped += 1
            continue

        # 1. Find or create VisitSchedule for this trial + visit_name
        vs_q = await db.execute(
            select(VisitSchedule).where(
                VisitSchedule.trial_id == trial_id,
                VisitSchedule.visit_name == visit_name,
            )
        )
        vs = vs_q.scalar_one_or_none()
        if not vs:
            order_q = await db.execute(
                select(VisitSchedule.visit_order)
                .where(VisitSchedule.trial_id == trial_id)
                .order_by(VisitSchedule.visit_order.desc())
                .limit(1)
            )
            last_order = order_q.scalar_one_or_none() or 0
            vs = VisitSchedule(
                trial_id=trial_id,
                budget_template_id=template_id,
                visit_name=visit_name,
                visit_order=last_order + 10,
                is_active=True,
            )
            db.add(vs)
            await db.flush()
            inserted_visits += 1

        # 2. Find or create BudgetLineItem for (template, cost_element)
        li_q = await db.execute(
            select(BudgetLineItem).where(
                BudgetLineItem.budget_template_id == template_id,
                BudgetLineItem.cost_element_id == el.id,
            )
        )
        li = li_q.scalar_one_or_none()
        if not li:
            sort_q = await db.execute(
                select(BudgetLineItem.sort_order)
                .where(BudgetLineItem.budget_template_id == template_id)
                .order_by(BudgetLineItem.sort_order.desc())
                .limit(1)
            )
            last_sort = sort_q.scalar_one_or_none() or 0
            li = BudgetLineItem(
                budget_template_id=template_id,
                cost_element_id=el.id,
                is_excluded=False,
                sort_order=last_sort + 10,
            )
            db.add(li)
            await db.flush()
            inserted_lines += 1

        # 3. Upsert BudgetVisitMatrix
        bvm_q = await db.execute(
            select(BudgetVisitMatrix).where(
                BudgetVisitMatrix.budget_line_item_id == li.id,
                BudgetVisitMatrix.visit_schedule_id == vs.id,
            )
        )
        bvm = bvm_q.scalar_one_or_none()
        if bvm:
            bvm.units = quantity
        else:
            db.add(BudgetVisitMatrix(
                budget_line_item_id=li.id,
                visit_schedule_id=vs.id,
                units=quantity,
                is_excluded=False,
            ))
            await db.flush()  # make visible to subsequent SELECTs in same transaction
            inserted_cells += 1

    await db.commit()
    budget_totals_cache.clear_all()

    return {
        "template_id": str(template_id),
        "inserted_visits": inserted_visits,
        "inserted_lines": inserted_lines,
        "inserted_cells": inserted_cells,
        "skipped": skipped,
    }

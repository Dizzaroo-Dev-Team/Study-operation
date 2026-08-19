"""
Planned Enrollment + Rollup Budget endpoints.

Mounted at `/api/budgeting`:

  GET   /country-budgets?trial_id=<uuid>
        -> [{ country_code, template_id, name }]
        Country codes that already have a COUNTRY-level BudgetTemplate under
        the given trial. Drives the country dropdown in Planned Enrollment.

  GET   /planned-enrollment?study_id=<uuid>
        -> [{ id, site_id, site_name, site_code, country_code, planned_patients,
              planned_activation_date, ... }]
        One row per site under the study (LEFT JOIN — sites without a plan
        come back with nulls so the UI can render an empty editable row).

  PUT   /planned-enrollment
        body: { study_id, site_id, country_code, planned_patients,
                planned_activation_date }
        Upsert keyed on (study_id, site_id).

  DELETE /planned-enrollment/{plan_id}

  GET   /rollup-budget?study_id=<uuid>
        -> [{ site_id, site_name, country_code, planned_patients,
               variable_cost, fixed_cost, total_cost }]
        Per-site rollup. variable = per_patient_total of country-budget,
        fixed = milestone_total, total = (variable * patients) + fixed.
        Sites with no plan or no country budget come back with zeros.
"""
from __future__ import annotations

import logging
from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.models import Site, Study, StudySite
from app.modules.site_budgeting.db_models import (
    BudgetTemplate,
    SiteEnrollmentPlan,
)
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.services import budget_service
from app.modules.site_budgeting.utils.request_cache import RequestMemo

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Site Budgeting — Planned Enrollment"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class PlannedEnrollmentUpsert(BaseModel):
    study_id: UUID
    site_id: UUID
    country_code: Optional[str] = Field(default=None, max_length=8)
    planned_patients: int = Field(default=0, ge=0)
    planned_activation_date: Optional[date] = None


# ─── Country budgets ──────────────────────────────────────────────────────────

@router.get("/country-budgets")
async def list_country_budgets(
    trial_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
) -> list[dict[str, Any]]:
    """Country codes that already have a COUNTRY-level template under this trial."""
    rows = (
        await db.execute(
            select(
                BudgetTemplate.id,
                BudgetTemplate.country_code,
                BudgetTemplate.name,
            )
            .where(BudgetTemplate.trial_id == trial_id)
            .where(BudgetTemplate.template_level == "COUNTRY")
            .where(BudgetTemplate.country_code.isnot(None))
            .order_by(BudgetTemplate.country_code)
        )
    ).all()
    return [
        {
            "template_id": str(t_id),
            "country_code": cc,
            "name": name,
        }
        for (t_id, cc, name) in rows
    ]


# ─── Planned enrollment ───────────────────────────────────────────────────────

async def _hydrate_plan_rows(
    db: AsyncSession, study_id: UUID
) -> list[dict[str, Any]]:
    """All sites under the study + their plan row (LEFT JOIN)."""
    site_rows = (
        await db.execute(
            select(Site)
            .join(StudySite, StudySite.site_id == Site.id)
            .where(StudySite.study_id == study_id)
            .order_by(Site.name)
        )
    ).scalars().all()

    plan_rows = (
        await db.execute(
            select(SiteEnrollmentPlan).where(SiteEnrollmentPlan.study_id == study_id)
        )
    ).scalars().all()
    plan_by_site = {p.site_id: p for p in plan_rows}

    out: list[dict[str, Any]] = []
    for site in site_rows:
        plan = plan_by_site.get(site.id)
        out.append(
            {
                "id": str(plan.id) if plan else None,
                "study_id": str(study_id),
                "site_id": str(site.id),
                "site_name": site.name,
                "site_code": site.site_id,
                "country_code": plan.country_code if plan else None,
                "planned_patients": plan.planned_patients if plan else 0,
                "planned_activation_date": (
                    plan.planned_activation_date.isoformat()
                    if plan and plan.planned_activation_date
                    else None
                ),
            }
        )
    return out


@router.get("/planned-enrollment")
async def list_planned_enrollment(
    study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
) -> list[dict[str, Any]]:
    return await _hydrate_plan_rows(db, study_id)


@router.put("/planned-enrollment")
async def upsert_planned_enrollment(
    body: PlannedEnrollmentUpsert,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
) -> dict[str, Any]:
    # Confirm the (study, site) pair actually exists in study_sites — otherwise
    # we'd happily store a plan that the rollup tab can never surface.
    mapping_exists = (
        await db.execute(
            select(StudySite.id)
            .where(StudySite.study_id == body.study_id)
            .where(StudySite.site_id == body.site_id)
        )
    ).scalar_one_or_none()
    if mapping_exists is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Site is not linked to this study.",
        )

    existing = (
        await db.execute(
            select(SiteEnrollmentPlan)
            .where(SiteEnrollmentPlan.study_id == body.study_id)
            .where(SiteEnrollmentPlan.site_id == body.site_id)
        )
    ).scalar_one_or_none()

    if existing is None:
        row = SiteEnrollmentPlan(
            study_id=body.study_id,
            site_id=body.site_id,
            country_code=(body.country_code or None),
            planned_patients=body.planned_patients,
            planned_activation_date=body.planned_activation_date,
        )
        db.add(row)
    else:
        existing.country_code = body.country_code or None
        existing.planned_patients = body.planned_patients
        existing.planned_activation_date = body.planned_activation_date
        row = existing

    await db.commit()
    await db.refresh(row)
    return {
        "id": str(row.id),
        "study_id": str(row.study_id),
        "site_id": str(row.site_id),
        "country_code": row.country_code,
        "planned_patients": row.planned_patients,
        "planned_activation_date": (
            row.planned_activation_date.isoformat() if row.planned_activation_date else None
        ),
    }


@router.delete("/planned-enrollment/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_planned_enrollment(
    plan_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    row = (
        await db.execute(select(SiteEnrollmentPlan).where(SiteEnrollmentPlan.id == plan_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plan not found")
    await db.delete(row)
    await db.commit()


# ─── Rollup budget ────────────────────────────────────────────────────────────

async def _country_template_map(
    db: AsyncSession, trial_id: UUID
) -> dict[str, BudgetTemplate]:
    """country_code → COUNTRY-level BudgetTemplate row for the trial."""
    rows = (
        await db.execute(
            select(BudgetTemplate)
            .where(BudgetTemplate.trial_id == trial_id)
            .where(BudgetTemplate.template_level == "COUNTRY")
            .where(BudgetTemplate.country_code.isnot(None))
        )
    ).scalars().all()
    return {t.country_code: t for t in rows}


@router.get("/rollup-budget")
async def rollup_budget(
    study_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
) -> list[dict[str, Any]]:
    """Per-site rollup: total = (fixed + variable) × patients."""
    plans = await _hydrate_plan_rows(db, study_id)
    country_tpl = await _country_template_map(db, study_id)
    memo = RequestMemo()

    out: list[dict[str, Any]] = []
    for p in plans:
        site_id = p["site_id"]
        site_name = p["site_name"]
        country_code = p["country_code"]
        patients = int(p["planned_patients"] or 0)

        variable_per_patient = Decimal("0")
        fixed_total = Decimal("0")
        template_id_used: Optional[str] = None

        tpl = country_tpl.get(country_code) if country_code else None
        if tpl is not None:
            try:
                totals = await budget_service.compute_budget_totals(
                    db,
                    tpl.id,
                    trial_id=study_id,
                    country_code=tpl.country_code,
                    site_id=None,
                    memo=memo,
                )
                variable_per_patient = Decimal(str(totals.get("per_patient_total") or "0"))
                fixed_total = Decimal(str(totals.get("milestone_total") or "0"))
                template_id_used = str(tpl.id)
            except Exception as exc:  # noqa: BLE001
                # Don't blow up the whole rollup if one country template misbehaves.
                logger.warning(
                    "rollup-budget: compute_budget_totals failed for site=%s country=%s: %s",
                    site_id, country_code, exc,
                )

        # User formula: total = (variable_per_patient × patients) + fixed
        total_cost = (variable_per_patient * Decimal(patients)) + fixed_total

        out.append(
            {
                "site_id": site_id,
                "site_name": site_name,
                "site_code": p["site_code"],
                "country_code": country_code,
                "planned_patients": patients,
                "variable_cost": str(variable_per_patient.quantize(Decimal("0.01"))),
                "fixed_cost": str(fixed_total.quantize(Decimal("0.01"))),
                "total_cost": str(total_cost.quantize(Decimal("0.01"))),
                "template_id_used": template_id_used,
            }
        )

    return out

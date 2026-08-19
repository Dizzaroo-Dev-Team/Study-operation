"""REST API: conversion factor types and factor values (multiplicative / additive)."""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import (
    ConversionFactor,
    ConversionFactorType,
    TrialFactorConfiguration,
)
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import audit_service, budget_totals_cache
from app.modules.site_budgeting.validators.schemas import ConversionFactorCreate

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Site Budgeting"])


@router.get("/factor-types")
async def list_factor_types(
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    r = await db.execute(select(ConversionFactorType).order_by(ConversionFactorType.code))
    rows = r.scalars().all()
    return [{"id": str(x.id), "code": x.code, "name": x.name, "mode": x.mode} for x in rows]


@router.get("/factors")
async def list_factors(
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
    trial_id: Optional[UUID] = None,
):
    rows = await repo.list_conversion_factors(db, trial_id=trial_id)
    return [
        {
            "id": str(fac.id),
            "factor_type": {"id": str(ft.id), "code": ft.code, "name": ft.name, "mode": ft.mode},
            "trial_id": str(fac.trial_id) if fac.trial_id else None,
            "country_code": fac.country_code,
            "site_id": str(fac.site_id) if fac.site_id else None,
            "sequence_order": fac.sequence_order,
            "value": str(fac.value),
            "label": fac.label,
            "justification": fac.justification,
            "scope_level": fac.scope_level,
            "scope_element_id": str(fac.scope_element_id) if fac.scope_element_id else None,
            "scope_category": fac.scope_category,
        }
        for fac, ft in rows
    ]


@router.get("/factors/by-scope")
async def list_factors_by_scope(
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
    scope: str = Query(..., description="COUNTRY or SITE"),
):
    """Return conversion factors filtered by geographic scope (COUNTRY or SITE)."""
    if scope == "COUNTRY":
        stmt = (
            select(ConversionFactor, ConversionFactorType)
            .join(ConversionFactorType, ConversionFactor.factor_type_id == ConversionFactorType.id)
            .where(ConversionFactor.country_code.isnot(None))
            .order_by(ConversionFactor.country_code)
        )
    elif scope == "SITE":
        stmt = (
            select(ConversionFactor, ConversionFactorType)
            .join(ConversionFactorType, ConversionFactor.factor_type_id == ConversionFactorType.id)
            .where(ConversionFactor.site_id.isnot(None))
            .order_by(ConversionFactor.site_id)
        )
    else:
        raise HTTPException(status_code=400, detail="scope must be COUNTRY or SITE")

    rows = (await db.execute(stmt)).all()
    return [
        {
            "id": str(fac.id),
            "factor_type": {"id": str(ft.id), "code": ft.code, "name": ft.name, "mode": ft.mode},
            "country_code": fac.country_code,
            "site_id": str(fac.site_id) if fac.site_id else None,
            "value": str(fac.value),
            "label": fac.label,
        }
        for fac, ft in rows
    ]


@router.post("/factors", status_code=status.HTTP_201_CREATED)
async def create_factor(
    body: ConversionFactorCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Create a conversion factor value.

    scope_type / scope_value removed (legacy, A2). Geographic scope is expressed via
    country_code + site_id. Element-granularity scope via scope_level + scope_element_id/scope_category.
    """
    fac = ConversionFactor(
        factor_type_id=body.factor_type_id,
        trial_id=body.trial_id,
        country_code=body.country_code,
        site_id=body.site_id,
        sequence_order=body.sequence_order,
        value=body.value,
        currency_code=body.currency_code,
        label=body.label,
        justification=body.justification,
        scope_level=body.scope_level,
        scope_element_id=body.scope_element_id,
        scope_category=body.scope_category,
    )
    db.add(fac)
    await db.flush()

    # C1: When registering a factor for a trial, create/update TrialFactorConfiguration
    # referencing the factor TYPE (not this specific value) -- guide section 3.2.
    if body.register_for_trial and body.trial_id:
        ft_id = body.factor_type_id
        existing_cfg = await db.execute(
            select(TrialFactorConfiguration)
            .where(
                TrialFactorConfiguration.trial_id == body.trial_id,
                TrialFactorConfiguration.factor_type_id == ft_id,
            )
        )
        existing_cfg_row = existing_cfg.scalar_one_or_none()
        if existing_cfg_row is None:
            cfg = TrialFactorConfiguration(
                trial_id=body.trial_id,
                factor_type_id=ft_id,
                application_sequence=body.sequence_order,
                is_active=True,
            )
            db.add(cfg)

    await audit_service.write_audit(
        db,
        entity_type="conversion_factor",
        entity_id=fac.id,
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={
            "trial_id": str(body.trial_id) if body.trial_id else None,
            "factor_type_id": str(body.factor_type_id),
            "value": str(body.value),
            "country_code": body.country_code,
        },
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(fac.id)}


@router.patch("/factors/{factor_id}", status_code=200)
async def patch_factor(
    factor_id: UUID,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    row = (await db.execute(select(ConversionFactor).where(ConversionFactor.id == factor_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Factor not found")
    changed: dict[str, Any] = {}
    if "value" in body:
        row.value = Decimal(str(body["value"]))
        changed["value"] = str(row.value)
    if "sequence_order" in body:
        row.sequence_order = int(body["sequence_order"])
        changed["sequence_order"] = row.sequence_order
    if changed:
        await audit_service.write_audit(
            db, entity_type="conversion_factor", entity_id=factor_id,
            action="UPDATE", user_id=user.get("user_id"), new_value=changed,
        )
        await db.commit()
        budget_totals_cache.clear_all()
    return {"id": str(factor_id), **changed}


@router.delete("/factors/{factor_id}", status_code=204)
async def delete_factor(
    factor_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    row = (await db.execute(select(ConversionFactor).where(ConversionFactor.id == factor_id))).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Factor not found")
    await db.delete(row)
    await audit_service.write_audit(
        db, entity_type="conversion_factor", entity_id=factor_id,
        action="DELETE", user_id=user.get("user_id"), new_value=None,
    )
    await db.commit()
    budget_totals_cache.clear_all()

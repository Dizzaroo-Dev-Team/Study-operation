from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.sites.irb_catalog import is_irb_excluded_from_catalog
from app.modules.sites.site_irb_validation import (
    assert_mapping_countries_compatible,
    clear_incompatible_site_irb_mapping,
    mapping_countries_compatible,
)
from app.models import IRB, SiteIRBMapping

router = APIRouter()


class SiteIRBMappingUpsert(BaseModel):
    site_id: UUID
    irb_id: int = Field(..., ge=1)


class SiteIRBMappingResponse(BaseModel):
    success: bool = True
    data: dict


@router.get("/site-irb-mapping")
async def get_site_irb_mapping(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(SiteIRBMapping).where(SiteIRBMapping.site_id == site_id)
    )
    row: Optional[SiteIRBMapping] = res.scalar_one_or_none()
    if not row:
        return {"success": True, "data": None}

    irb_check = await db.execute(select(IRB).where(IRB.id == int(row.irb_id)))
    mapped_irb = irb_check.scalar_one_or_none()
    if not mapped_irb or is_irb_excluded_from_catalog(
        mapped_irb.name, getattr(mapped_irb, "unique_code", None)
    ):
        return {"success": True, "data": None}

    if not await mapping_countries_compatible(db, site_id, int(row.irb_id)):
        await clear_incompatible_site_irb_mapping(db, site_id)
        await db.commit()
        return {
            "success": True,
            "data": None,
            "cleared_country_mismatch": True,
            "message": (
                "A previous IRB selection did not match this site's country and was cleared. "
                "Please select an IRB again."
            ),
        }

    return {
        "success": True,
        "data": {
            "id": row.id,
            "site_id": str(row.site_id),
            "irb_id": int(row.irb_id),
        },
    }


@router.get("/site-irb-mapping/for-site")
async def get_site_irb_for_site_only(
    site_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Return the IRB id linked to this site (if any).
    Kept for backwards-compatible callers that still hit /for-site.
    """
    res = await db.execute(
        select(SiteIRBMapping.irb_id).where(SiteIRBMapping.site_id == site_id).distinct()
    )
    ids = [int(x) for x in res.scalars().all()]
    if not ids:
        return {"success": True, "data": None}
    if len(ids) > 1:
        return {
            "success": True,
            "data": {"irb_id": ids[0], "inconsistent_multiple": True},
        }
    if not await mapping_countries_compatible(db, site_id, ids[0]):
        await clear_incompatible_site_irb_mapping(db, site_id)
        await db.commit()
        return {"success": True, "data": None}
    return {"success": True, "data": {"irb_id": ids[0]}}


@router.post("/site-irb-mapping", response_model=SiteIRBMappingResponse)
async def upsert_site_irb_mapping(
    payload: SiteIRBMappingUpsert,
    db: AsyncSession = Depends(get_db),
):
    irb_res = await db.execute(select(IRB).where(IRB.id == int(payload.irb_id)))
    irb = irb_res.scalar_one_or_none()
    if not irb:
        raise HTTPException(status_code=404, detail="IRB not found")
    if is_irb_excluded_from_catalog(irb.name, getattr(irb, "unique_code", None)):
        raise HTTPException(
            status_code=400,
            detail="This ethics committee is no longer available for selection. Choose another IRB.",
        )

    await assert_mapping_countries_compatible(db, payload.site_id, int(payload.irb_id))

    try:
        res = await db.execute(
            text(
                """
                INSERT INTO site_irb_mapping (site_id, irb_id, created_at, updated_at)
                VALUES (:site_id, :irb_id, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT (site_id)
                DO UPDATE
                SET irb_id = EXCLUDED.irb_id,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING id, site_id, irb_id;
                """
            ),
            {
                "site_id": payload.site_id,
                "irb_id": int(payload.irb_id),
            },
        )
        row = res.fetchone()
        await db.commit()

        if not row:
            raise HTTPException(status_code=500, detail="Mapping save failed")

        return {
            "success": True,
            "data": {
                "id": row[0],
                "site_id": str(row[1]),
                "irb_id": int(row[2]),
            },
        }
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Mapping conflict: {str(e)}")

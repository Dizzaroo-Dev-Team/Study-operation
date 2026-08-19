from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.sites.country_normalize import countries_match, resolve_irb_country
from app.modules.sites.irb_catalog import is_irb_excluded_from_catalog
from app.models import IRB, IRBAdministrativeInfo

router = APIRouter()


@router.get("/irbs")
async def list_irbs(
    country: str | None = Query(default=None, description="Optional country filter"),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(IRB, IRBAdministrativeInfo.country, IRBAdministrativeInfo.jurisdiction)
        .outerjoin(IRBAdministrativeInfo, IRBAdministrativeInfo.irb_id == IRB.id)
        .order_by(IRB.name.asc(), IRB.id.asc())
    )
    result = await db.execute(query)
    rows = list(result.all())

    filter_by_country = bool((country or "").strip())
    data = []
    for irb, admin_country, jurisdiction in rows:
        if is_irb_excluded_from_catalog(irb.name, getattr(irb, "unique_code", None)):
            continue
        if filter_by_country and not countries_match(country, admin_country, jurisdiction):
            continue
        data.append(
            {
                "id": irb.id,
                "name": irb.name,
                "unique_code": getattr(irb, "unique_code", None),
                "country": resolve_irb_country(admin_country, jurisdiction),
            }
        )

    return {"success": True, "data": data}

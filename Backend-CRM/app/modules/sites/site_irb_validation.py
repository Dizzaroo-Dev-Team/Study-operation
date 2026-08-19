"""Validate site ↔ IRB country compatibility before persisting mappings."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.sites.country_normalize import countries_match, resolve_irb_country
from app.models import IRB, IRBAdministrativeInfo, Site, SiteIRBMapping, SiteProfile


async def resolve_site_country(db: AsyncSession, site_id: UUID) -> str | None:
    """Site profile country first, then sites.country."""
    profile_row = (
        await db.execute(
            select(SiteProfile.country).where(SiteProfile.site_id == site_id)
        )
    ).scalar_one_or_none()
    if profile_row and str(profile_row).strip():
        return str(profile_row).strip()

    site_row = (
        await db.execute(select(Site.country).where(Site.id == site_id))
    ).scalar_one_or_none()
    if site_row and str(site_row).strip():
        return str(site_row).strip()
    return None


async def resolve_irb_admin_country(
    db: AsyncSession,
    irb_id: int,
) -> tuple[str | None, str | None]:
    row = (
        await db.execute(
            select(IRBAdministrativeInfo.country, IRBAdministrativeInfo.jurisdiction).where(
                IRBAdministrativeInfo.irb_id == irb_id
            )
        )
    ).one_or_none()
    if not row:
        return None, None
    admin_country, jurisdiction = row
    return (
        str(admin_country).strip() if admin_country else None,
        str(jurisdiction).strip() if jurisdiction else None,
    )


async def mapping_countries_compatible(
    db: AsyncSession,
    site_id: UUID,
    irb_id: int,
) -> bool:
    site_country = await resolve_site_country(db, site_id)
    if not site_country:
        return True
    admin_country, jurisdiction = await resolve_irb_admin_country(db, irb_id)
    return countries_match(site_country, admin_country, jurisdiction)


async def assert_mapping_countries_compatible(
    db: AsyncSession,
    site_id: UUID,
    irb_id: int,
) -> None:
    site_country = await resolve_site_country(db, site_id)
    if not site_country:
        raise HTTPException(
            status_code=400,
            detail=(
                "Set the site country on Site Profile before selecting an IRB/IEC."
            ),
        )

    admin_country, jurisdiction = await resolve_irb_admin_country(db, irb_id)
    resolved_irb_country = resolve_irb_country(admin_country, jurisdiction)
    if countries_match(site_country, admin_country, jurisdiction):
        return

    irb_name = (
        await db.execute(select(IRB.name).where(IRB.id == irb_id))
    ).scalar_one_or_none()

    raise HTTPException(
        status_code=400,
        detail=(
            f"IRB '{irb_name or irb_id}' ({resolved_irb_country or 'unknown country'}) "
            f"cannot be linked to a site in {site_country}. "
            "Choose an ethics committee that matches the site country."
        ),
    )


async def clear_incompatible_site_irb_mapping(
    db: AsyncSession,
    site_id: UUID,
) -> bool:
    """Remove mapping when IRB country no longer matches site country. Returns True if cleared."""
    mapping = (
        await db.execute(
            select(SiteIRBMapping).where(SiteIRBMapping.site_id == site_id)
        )
    ).scalar_one_or_none()
    if not mapping:
        return False
    if await mapping_countries_compatible(db, site_id, int(mapping.irb_id)):
        return False
    await db.execute(delete(SiteIRBMapping).where(SiteIRBMapping.site_id == site_id))
    return True

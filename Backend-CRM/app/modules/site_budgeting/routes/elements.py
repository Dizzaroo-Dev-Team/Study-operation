"""REST API: element categories, cost elements, bundle composition, and FMV import."""
from __future__ import annotations

import csv
import io
import logging
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.modules.site_budgeting.db_models import (
    CostElement,
    ElementBundleComposition,
    ElementCategory,
    ElementCostVersion,
)
from app.modules.site_budgeting.dependencies import require_site_budgeting
from app.modules.site_budgeting.repositories import budgeting_repository as repo
from app.modules.site_budgeting.services import audit_service, budget_totals_cache
from app.modules.site_budgeting.validators.schemas import (
    BundleChildUpsert,
    CostElementCreate,
    CostElementUpdate,
    ElementCategoryCreate,
    ElementCategoryUpdate,
    ElementCostUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Site Budgeting"])


def _parse_description_meta(description: str | None) -> dict[str, str | None]:
    """Extract subcategory / unit / cost_variability / pass_thru from the structured
    description written by the cost master seed
    (`Subcategory: X | Unit: Y | Cost Type: FIXED|VARIABLE | Pass-Thru: Y|N`).
    Tolerant of legacy free-text descriptions — missing keys return None.
    """
    meta: dict[str, str | None] = {
        "subcategory": None,
        "unit_label": None,
        "cost_variability": None,
        "pass_thru": None,
    }
    if not description:
        return meta
    for part in description.split("|"):
        key, sep, value = part.strip().partition(":")
        if not sep:
            continue
        key = key.strip().lower()
        value = value.strip() or None
        if key == "subcategory":
            meta["subcategory"] = value
        elif key == "unit":
            meta["unit_label"] = value
        elif key == "cost type":
            meta["cost_variability"] = value
        elif key == "pass-thru":
            meta["pass_thru"] = value
    return meta


@router.get("/elements")
async def list_elements(
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    rows = await repo.list_cost_elements(db)

    out = []
    for el in rows:
        latest = await repo.get_latest_cost_version(db, el.id)
        cat_id = getattr(el, "category_id", None)
        meta = _parse_description_meta(el.description)
        out.append(
            {
                "id": str(el.id),
                "code": el.code,
                "name": el.name,
                "description": el.description,
                "unit": el.unit_of_measure,
                "category": el.category.name if el.category else None,
                "category_id": str(cat_id) if cat_id else None,
                "subcategory": meta["subcategory"],
                "unit_label": meta["unit_label"],
                "cost_variability": meta["cost_variability"],
                "pass_thru": meta["pass_thru"],
                "element_type": getattr(el, "element_type", None),
                "cost_type": getattr(el, "cost_type", None),
                "therapeutic_area": getattr(el, "therapeutic_area", None),
                "is_active": getattr(el, "is_active", True),
                "latest_version": (
                    {
                        "version_label": latest.version_label,
                        "base_unit_cost": str(latest.base_unit_cost),
                        "reference_currency": latest.reference_currency,
                    }
                    if latest
                    else None
                ),
            }
        )
    return out


@router.patch("/elements/{element_id}/cost")
async def patch_element_cost(
    element_id: UUID,
    body: ElementCostUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    el = await repo.get_cost_element(db, element_id)
    if not el:
        raise HTTPException(status_code=404, detail="Cost element not found")

    existing = await repo.get_cost_version_by_label(db, element_id, body.version_label)
    old = {"version_label": existing.version_label, "base_unit_cost": str(existing.base_unit_cost)} if existing else None

    if existing:
        existing.base_unit_cost = body.base_unit_cost
        existing.reference_currency = body.reference_currency
        row = existing
    else:
        row = ElementCostVersion(
            element_id=element_id,
            version_label=body.version_label,
            base_unit_cost=body.base_unit_cost,
            reference_currency=body.reference_currency,
        )
        db.add(row)

    await db.flush()
    await audit_service.write_audit(
        db,
        entity_type="element_cost_version",
        entity_id=row.id,
        action="UPDATE" if existing else "CREATE",
        user_id=user.get("user_id"),
        old_value=old,
        new_value={"version_label": row.version_label, "base_unit_cost": str(row.base_unit_cost)},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(row.id), "element_id": str(element_id), "version_label": row.version_label}


# --- Element Category CRUD ----------------------------------------------------

@router.get("/categories")
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """Return flat list of all element categories, ordered by sort_order."""
    r = await db.execute(select(ElementCategory).order_by(ElementCategory.sort_order, ElementCategory.name))
    rows = r.scalars().all()
    return [
        {
            "id": str(c.id),
            "name": c.name,
            "parent_id": str(c.parent_id) if c.parent_id else None,
            "sort_order": c.sort_order,
        }
        for c in rows
    ]


@router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    body: ElementCategoryCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    cat = ElementCategory(name=body.name, parent_id=body.parent_id, sort_order=body.sort_order)
    db.add(cat)
    await db.flush()
    await audit_service.write_audit(
        db, entity_type="element_category", entity_id=cat.id, action="CREATE",
        user_id=user.get("user_id"), new_value={"name": body.name},
    )
    await db.commit()
    return {"id": str(cat.id), "name": cat.name}


@router.patch("/categories/{category_id}")
async def update_category(
    category_id: UUID,
    body: ElementCategoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    r = await db.execute(select(ElementCategory).where(ElementCategory.id == category_id))
    cat = r.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    sf = body.model_fields_set
    if "name" in sf and body.name:
        cat.name = body.name
    if "parent_id" in sf:
        cat.parent_id = body.parent_id
    if "sort_order" in sf and body.sort_order is not None:
        cat.sort_order = body.sort_order
    await db.commit()
    return {"id": str(cat.id), "name": cat.name}


@router.delete("/categories/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    r = await db.execute(select(ElementCategory).where(ElementCategory.id == category_id))
    cat = r.scalar_one_or_none()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found")
    await db.delete(cat)
    await db.commit()


# --- Cost Element full CRUD ---------------------------------------------------

@router.post("/elements", status_code=status.HTTP_201_CREATED)
async def create_element(
    body: CostElementCreate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """Create a new cost element (ATOMIC or BUNDLE)."""
    existing = await db.execute(select(CostElement).where(CostElement.code == body.code))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail=f"Cost element with code '{body.code}' already exists")

    el = CostElement(
        code=body.code,
        name=body.name,
        description=body.description,
        unit_of_measure=body.unit or "unit",
        category_id=body.category_id,
        element_type=body.element_type or "ATOMIC",
        cost_type=body.cost_type,
        therapeutic_area=body.therapeutic_area,
        is_active=body.is_active,
    )
    db.add(el)
    await db.flush()
    await audit_service.write_audit(
        db, entity_type="cost_element", entity_id=el.id, action="CREATE",
        user_id=user.get("user_id"),
        new_value={"code": body.code, "name": body.name, "element_type": el.element_type},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(el.id), "code": el.code}


@router.patch("/elements/{element_id}")
async def update_element(
    element_id: UUID,
    body: CostElementUpdate,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """Update cost element metadata (name, type, category, etc.)."""
    el = await repo.get_cost_element(db, element_id)
    if not el:
        raise HTTPException(status_code=404, detail="Cost element not found")

    old = {"name": el.name, "element_type": el.element_type, "cost_type": el.cost_type, "is_active": el.is_active}
    sf = body.model_fields_set
    if "name" in sf and body.name:
        el.name = body.name
    if "description" in sf:
        el.description = body.description
    if "unit" in sf:
        el.unit_of_measure = body.unit or "unit"
    if "category_id" in sf:
        el.category_id = body.category_id
    if "element_type" in sf and body.element_type:
        el.element_type = body.element_type
    if "cost_type" in sf:
        el.cost_type = body.cost_type
    if "therapeutic_area" in sf:
        el.therapeutic_area = body.therapeutic_area
    if "is_active" in sf and body.is_active is not None:
        el.is_active = body.is_active

    await db.flush()
    await audit_service.write_audit(
        db, entity_type="cost_element", entity_id=el.id, action="UPDATE",
        user_id=user.get("user_id"), old_value=old,
        new_value={"name": el.name, "element_type": el.element_type, "is_active": el.is_active},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"id": str(el.id)}


@router.delete("/elements/{element_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_element(
    element_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """Soft-delete a cost element (sets is_active=False). Use ?hard=true to permanently delete."""
    el = await repo.get_cost_element(db, element_id)
    if not el:
        raise HTTPException(status_code=404, detail="Cost element not found")
    old_active = el.is_active
    el.is_active = False
    await db.flush()
    await audit_service.write_audit(
        db, entity_type="cost_element", entity_id=el.id, action="DELETE",
        user_id=user.get("user_id"), old_value={"is_active": old_active}, new_value={"is_active": False},
    )
    await db.commit()
    budget_totals_cache.clear_all()


# --- Bundle Composition CRUD --------------------------------------------------

@router.get("/elements/{element_id}/bundle-children")
async def get_bundle_children(
    element_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: dict[str, Any] = Depends(require_site_budgeting),
):
    """Return the atomic children of a BUNDLE element with their FMV costs."""
    el = await repo.get_cost_element(db, element_id)
    if not el:
        raise HTTPException(status_code=404, detail="Cost element not found")

    r = await db.execute(
        select(ElementBundleComposition)
        .where(ElementBundleComposition.bundle_element_id == element_id)
        .order_by(ElementBundleComposition.sort_order)
    )
    compositions = r.scalars().all()

    result = []
    for comp in compositions:
        child = await repo.get_cost_element(db, comp.child_element_id)
        latest = await repo.get_latest_cost_version(db, comp.child_element_id)
        result.append({
            "child_element_id": str(comp.child_element_id),
            "code": child.code if child else None,
            "name": child.name if child else None,
            "quantity_in_bundle": str(comp.quantity_in_bundle),
            "sort_order": comp.sort_order,
            "unit_cost": str(latest.base_unit_cost) if latest else None,
            "currency": latest.reference_currency if latest else None,
        })
    return result


@router.put("/elements/{element_id}/bundle-children")
async def upsert_bundle_children(
    element_id: UUID,
    body: list[BundleChildUpsert],
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """Replace the full bundle composition for an element. Accepts a list of children."""
    el = await repo.get_cost_element(db, element_id)
    if not el:
        raise HTTPException(status_code=404, detail="Cost element not found")
    if getattr(el, "element_type", None) != "BUNDLE":
        raise HTTPException(status_code=400, detail="Cost element is not a BUNDLE")

    # Delete existing composition
    existing = await db.execute(
        select(ElementBundleComposition).where(ElementBundleComposition.bundle_element_id == element_id)
    )
    for row in existing.scalars().all():
        await db.delete(row)

    # Insert new composition
    for item in body:
        comp = ElementBundleComposition(
            bundle_element_id=element_id,
            child_element_id=item.child_element_id,
            quantity_in_bundle=item.quantity_in_bundle,
            sort_order=item.sort_order,
        )
        db.add(comp)

    await db.flush()
    await audit_service.write_audit(
        db, entity_type="cost_element", entity_id=element_id, action="UPDATE",
        user_id=user.get("user_id"),
        new_value={"bundle_children": [str(b.child_element_id) for b in body]},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {"bundle_element_id": str(element_id), "children_count": len(body)}


# --- Bulk FMV Import ----------------------------------------------------------

@router.post("/elements/fmv-import", status_code=status.HTTP_200_OK)
async def bulk_fmv_import(
    file: UploadFile = File(...),
    version_label: str = Query(..., description="Version label to assign e.g. 'FMV 2026 Q1'"),
    currency_code: str = Query(default="USD", max_length=3),
    source: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(require_site_budgeting),
):
    """
    Bulk import FMV cost data from a CSV file.

    Expected CSV columns (header row required):
      code, base_unit_cost   (minimum required)
    Optional columns:
      version_label, currency_code, source, effective_from, is_bundle_override

    The 'code' column must match existing cost_element.code values.
    Rows with unknown codes are skipped and reported.
    Existing version with the same label is updated; otherwise a new version is inserted.
    """
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported. Upload a .csv file.")

    content = await file.read()
    try:
        text_content = content.decode("utf-8-sig")  # handle BOM
    except UnicodeDecodeError:
        text_content = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text_content))
    if reader.fieldnames is None or "code" not in reader.fieldnames or "base_unit_cost" not in reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must have at least 'code' and 'base_unit_cost' columns.")

    inserted = 0
    updated = 0
    skipped: list[str] = []

    for row_num, row in enumerate(reader, start=2):  # start=2 because row 1 is header
        code = (row.get("code") or "").strip()
        amount_raw = (row.get("base_unit_cost") or "").strip()
        if not code or not amount_raw:
            skipped.append(f"Row {row_num}: missing code or base_unit_cost")
            continue

        try:
            base_amount = Decimal(amount_raw)
        except Exception:
            skipped.append(f"Row {row_num} ({code}): invalid base_unit_cost '{amount_raw}'")
            continue

        # Look up element by code
        el_res = await db.execute(select(CostElement).where(CostElement.code == code))
        el = el_res.scalar_one_or_none()
        if not el:
            skipped.append(f"Row {row_num}: unknown element code '{code}'")
            continue

        row_label = (row.get("version_label") or "").strip() or version_label
        row_currency = (row.get("currency_code") or "").strip() or currency_code
        row_source = (row.get("source") or "").strip() or source
        row_bundle_override = (row.get("is_bundle_override") or "").strip().lower() in ("true", "1", "yes")

        # Upsert version
        ver_res = await db.execute(
            select(ElementCostVersion).where(
                ElementCostVersion.element_id == el.id,
                ElementCostVersion.version_label == row_label,
            )
        )
        ver = ver_res.scalar_one_or_none()
        if ver:
            ver.base_unit_cost = base_amount
            ver.reference_currency = row_currency
            if row_source:
                ver.source = row_source
            ver.is_bundle_override = row_bundle_override
            ver.created_by = user.get("user_id")
            updated += 1
        else:
            ver = ElementCostVersion(
                element_id=el.id,
                version_label=row_label,
                base_unit_cost=base_amount,
                reference_currency=row_currency,
                source=row_source,
                is_bundle_override=row_bundle_override,
                created_by=user.get("user_id"),
            )
            db.add(ver)
            inserted += 1

    await db.flush()
    await audit_service.write_audit(
        db, entity_type="element_cost_version", entity_id=UUID("00000000-0000-0000-0000-000000000001"),
        action="CREATE",
        user_id=user.get("user_id"),
        new_value={"version_label": version_label, "inserted": inserted, "updated": updated, "skipped_count": len(skipped)},
    )
    await db.commit()
    budget_totals_cache.clear_all()
    return {
        "version_label": version_label,
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
    }

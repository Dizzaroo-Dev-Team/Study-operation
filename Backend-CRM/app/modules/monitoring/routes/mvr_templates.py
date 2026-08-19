"""REST API: MVR (Monitoring Visit Report) templates - CRUD + draft/publish/duplicate lifecycle."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db

# NOTE: no prefix here. The parent router in app/monitor/router.py owns the
# /api/monitor prefix; sub-routers are mounted via include_router without
# additional prefix so the final URLs stay /api/monitor/mvr-templates/*.
router = APIRouter(tags=["monitor"])


# --- Pydantic body schemas --------------------------------------------------

class MvrTemplateSaveBody(BaseModel):
    name: str = "MVR Template"
    schema: Dict[str, Any] = Field(default_factory=dict)
    publish: bool = True
    organization_id: str = "default"


class MvrDraftCreateBody(BaseModel):
    name: str = "Untitled Template"
    organization_id: str = "default"


class MvrTemplatePatchBody(BaseModel):
    name: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None
    finalize: bool = Field(
        True,
        description="When true, lifecycle becomes published (Saved). When false, lifecycle becomes draft even if it was previously published.",
    )


class MvrPublishBody(BaseModel):
    """Optional final snapshot when publishing a draft."""

    name: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None


class MvrDuplicateBody(BaseModel):
    name: Optional[str] = None
    schema: Optional[Dict[str, Any]] = None
    organization_id: str = "default"


# --- Helpers (private to this module) --------------------------------------

async def _next_mvr_template_version(db: AsyncSession, organization_id: str) -> int:
    # Serialize version allocation per organization so concurrent creates
    # cannot both read the same MAX(version). Lock is released at commit.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext('mvr_tpl_ver'), hashtext(:oid))"),
        {"oid": organization_id},
    )
    ver_row = await db.execute(
        text(
            "SELECT COALESCE(MAX(version), 0) AS mv FROM monitoring_mvr_templates WHERE organization_id = :oid"
        ),
        {"oid": organization_id},
    )
    return int((ver_row.mappings().first() or {}).get("mv") or 0) + 1


async def _fetch_active_mvr_template_row(db: AsyncSession, organization_id: str) -> Optional[Dict[str, Any]]:
    row = await db.execute(
        text(
            """
            SELECT id, organization_id, name, schema, version, is_active, lifecycle_status, updated_at
            FROM monitoring_mvr_templates
            WHERE organization_id = :oid AND is_active = TRUE AND lifecycle_status = 'published'
            ORDER BY version DESC
            LIMIT 1
            """
        ),
        {"oid": organization_id},
    )
    r = row.mappings().first()
    if not r:
        return None
    d = dict(r)
    if d.get("id") is not None:
        d["id"] = str(d["id"])
    sch = d.get("schema")
    if isinstance(sch, str):
        try:
            d["schema"] = json.loads(sch)
        except Exception:
            d["schema"] = {}
    elif sch is None:
        d["schema"] = {}
    return d


async def _fetch_mvr_template_row_by_id(db: AsyncSession, template_id: str) -> Optional[Dict[str, Any]]:
    if not template_id or not str(template_id).strip():
        return None
    row = await db.execute(
        text(
            """
            SELECT id, organization_id, name, schema, version, is_active, lifecycle_status, updated_at
            FROM monitoring_mvr_templates
            WHERE id = :id
            LIMIT 1
            """
        ),
        {"id": str(template_id).strip()},
    )
    r = row.mappings().first()
    if not r:
        return None
    d = dict(r)
    if d.get("id") is not None:
        d["id"] = str(d["id"])
    sch = d.get("schema")
    if isinstance(sch, str):
        try:
            d["schema"] = json.loads(sch)
        except Exception:
            d["schema"] = {}
    elif sch is None:
        d["schema"] = {}
    return d


def _mvr_template_public(row: Dict[str, Any]) -> Dict[str, Any]:
    ua = row.get("updated_at")
    updated_iso: Optional[str] = None
    try:
        if ua is not None and hasattr(ua, "isoformat"):
            updated_iso = ua.isoformat()
    except Exception:
        updated_iso = None
    raw_ls = (row.get("lifecycle_status") or "published") or "published"
    ls = str(raw_ls).strip().lower()
    if ls not in ("draft", "published"):
        ls = "published"
    return {
        "id": row["id"],
        "organizationId": row.get("organization_id"),
        "name": row.get("name"),
        "schema": row.get("schema") or {},
        "version": int(row.get("version") or 1),
        "lifecycleStatus": ls,
        "isActive": bool(row.get("is_active")),
        "updatedAt": updated_iso,
    }


# Lazy import to avoid circular dependency with app.modules.monitoring.aggregator which
# imports this module's `router` for inclusion.
async def _ensure_tables(db: AsyncSession) -> None:
    from app.modules.monitoring.aggregator import _ensure_monitor_tables  # noqa: E402 (lazy on purpose)
    await _ensure_monitor_tables(db)


# --- Endpoints --------------------------------------------------------------

@router.get("/mvr-templates/active")
async def get_active_mvr_template_endpoint(organization_id: str = "default", db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    row = await _fetch_active_mvr_template_row(db, (organization_id or "default").strip() or "default")
    if not row:
        return {"template": None}
    return {"template": _mvr_template_public(row)}


@router.get("/mvr-templates")
async def list_mvr_templates_endpoint(organization_id: str = "default", db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    oid = (organization_id or "default").strip() or "default"
    rows = await db.execute(
        text(
            """
            SELECT id, organization_id, name, schema, version, is_active, lifecycle_status, updated_at
            FROM monitoring_mvr_templates
            WHERE organization_id = :oid
            ORDER BY updated_at DESC, version DESC
            """
        ),
        {"oid": oid},
    )
    items: List[Dict[str, Any]] = []
    for r in rows.mappings().all():
        items.append(_mvr_template_public(dict(r)))
    return {"items": items}


@router.post("/mvr-templates/drafts")
async def create_mvr_template_draft(body: MvrDraftCreateBody, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    oid = (body.organization_id or "default").strip() or "default"
    next_v = await _next_mvr_template_version(db, oid)
    tid = str(uuid4())
    empty_schema = json.dumps({"fields": []})
    nm = (body.name or "Untitled Template").strip() or "Untitled Template"
    await db.execute(
        text(
            """
            INSERT INTO monitoring_mvr_templates
                (id, organization_id, name, schema, version, is_active, lifecycle_status, created_at, updated_at)
            VALUES
                (:id, :oid, :name, CAST(:schema AS jsonb), :version, FALSE, 'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ),
        {"id": tid, "oid": oid, "name": nm, "schema": empty_schema, "version": next_v},
    )
    await db.commit()
    row = await _fetch_mvr_template_row_by_id(db, tid)
    if not row:
        raise HTTPException(status_code=500, detail="Draft create failed")
    return {"template": _mvr_template_public(row)}


@router.delete("/mvr-templates/all")
async def delete_all_mvr_templates_endpoint(organization_id: str = "default", db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    oid = (organization_id or "default").strip() or "default"
    res = await db.execute(
        text("DELETE FROM monitoring_mvr_templates WHERE organization_id = :oid"),
        {"oid": oid},
    )
    await db.commit()
    rc = getattr(res, "rowcount", None)
    try:
        deleted_count = int(rc) if rc is not None else 0
    except (TypeError, ValueError):
        deleted_count = 0
    return {"status": "deleted_all", "deleted_count": deleted_count}


@router.get("/mvr-templates/{template_id}")
async def get_mvr_template_by_id(template_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    row = await _fetch_mvr_template_row_by_id(db, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"template": _mvr_template_public(row)}


@router.delete("/mvr-templates/{template_id}")
async def delete_mvr_template_endpoint(template_id: str, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    row = await _fetch_mvr_template_row_by_id(db, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.execute(text("DELETE FROM monitoring_mvr_templates WHERE id = :id"), {"id": str(template_id).strip()})
    await db.commit()
    return {"status": "deleted"}


@router.patch("/mvr-templates/{template_id}")
async def patch_mvr_template_endpoint(template_id: str, body: MvrTemplatePatchBody, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    row = await _fetch_mvr_template_row_by_id(db, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    ls = str(row.get("lifecycle_status") or "published").strip().lower()
    if ls not in ("draft", "published"):
        raise HTTPException(status_code=409, detail="cannot_edit_template")

    sets: List[str] = []
    params: Dict[str, Any] = {"id": template_id}
    if body.name is not None:
        sets.append("name = :name")
        params["name"] = (body.name or "").strip() or "Untitled Template"
    if body.schema is not None:
        sets.append("schema = CAST(:schema AS jsonb)")
        params["schema"] = json.dumps(body.schema if isinstance(body.schema, dict) else {})

    # Saving never grabs the Live flag; that is done explicitly via /activate.
    finalize = bool(body.finalize)
    target_ls = "published" if finalize else "draft"
    if ls != target_ls:
        sets.append(f"lifecycle_status = '{target_ls}'")
    if not finalize and bool(row.get("is_active")):
        # Draft templates must not remain flagged Live for legacy active-template lookups.
        sets.append("is_active = FALSE")

    if not sets:
        return {"status": "noop", "template": _mvr_template_public(row)}

    await db.execute(
        text(
            f"""
            UPDATE monitoring_mvr_templates
            SET {", ".join(sets)}, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND lifecycle_status IN ('draft', 'published')
            """
        ),
        params,
    )
    await db.commit()
    refreshed = await _fetch_mvr_template_row_by_id(db, template_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "saved", "template": _mvr_template_public(refreshed)}


@router.post("/mvr-templates/{template_id}/activate")
async def activate_mvr_template_endpoint(template_id: str, db: AsyncSession = Depends(get_db)):
    """Mark a saved (published) template as Live for visit reports (one Live template per organization)."""
    await _ensure_tables(db)
    row = await _fetch_mvr_template_row_by_id(db, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    ls = str(row.get("lifecycle_status") or "published").strip().lower()
    if ls != "published":
        raise HTTPException(
            status_code=400,
            detail="Only saved templates can be set as Live. Open the template, then use Save (not Save draft).",
        )
    oid = str(row.get("organization_id") or "default")
    await db.execute(
        text("UPDATE monitoring_mvr_templates SET is_active = FALSE WHERE organization_id = :oid"),
        {"oid": oid},
    )
    await db.execute(
        text(
            """
            UPDATE monitoring_mvr_templates
            SET is_active = TRUE, updated_at = CURRENT_TIMESTAMP
            WHERE id = :id
            """
        ),
        {"id": str(template_id).strip()},
    )
    await db.commit()
    refreshed = await _fetch_mvr_template_row_by_id(db, template_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "activated", "template": _mvr_template_public(refreshed)}


@router.post("/mvr-templates/{template_id}/publish")
async def publish_mvr_template_endpoint(template_id: str, body: Optional[MvrPublishBody] = None, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    row = await _fetch_mvr_template_row_by_id(db, template_id)
    if not row:
        raise HTTPException(status_code=404, detail="Template not found")
    ls = str(row.get("lifecycle_status") or "published").strip().lower()
    if ls != "draft":
        raise HTTPException(status_code=400, detail="Only draft templates can be published")

    name_val = row.get("name") or "MVR Template"
    if body and body.name is not None:
        name_val = (body.name or "").strip() or name_val
    schema_val: Dict[str, Any]
    if body and body.schema is not None:
        schema_val = body.schema if isinstance(body.schema, dict) else {}
    else:
        sch = row.get("schema")
        schema_val = sch if isinstance(sch, dict) else {}

    # Publishing marks the template Saved; it only becomes Live via /activate.
    await db.execute(
        text(
            """
            UPDATE monitoring_mvr_templates
            SET
                name = :name,
                schema = CAST(:schema AS jsonb),
                lifecycle_status = 'published',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = :id AND lifecycle_status = 'draft'
            """
        ),
        {
            "id": template_id,
            "name": str(name_val).strip() or "MVR Template",
            "schema": json.dumps(schema_val),
        },
    )
    await db.commit()
    refreshed = await _fetch_mvr_template_row_by_id(db, template_id)
    if not refreshed:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"status": "published", "template": _mvr_template_public(refreshed)}


@router.post("/mvr-templates/{template_id}/duplicate")
async def duplicate_mvr_template_endpoint(
    template_id: str,
    body: Optional[MvrDuplicateBody] = None,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_tables(db)
    src = await _fetch_mvr_template_row_by_id(db, template_id)
    if not src:
        raise HTTPException(status_code=404, detail="Template not found")
    oid = (body.organization_id if body and body.organization_id else None) or str(src.get("organization_id") or "default")
    oid = (oid or "default").strip() or "default"
    next_v = await _next_mvr_template_version(db, oid)
    new_id = str(uuid4())

    base_name = str(src.get("name") or "MVR Template").strip() or "MVR Template"
    if body and body.name is not None:
        dup_name = (body.name or "").strip() or f"{base_name} (Copy)"
    else:
        dup_name = f"{base_name} (Copy)"

    if body and body.schema is not None:
        schema_use = body.schema if isinstance(body.schema, dict) else {}
    else:
        sch = src.get("schema")
        schema_use = sch if isinstance(sch, dict) else {}

    await db.execute(
        text(
            """
            INSERT INTO monitoring_mvr_templates
                (id, organization_id, name, schema, version, is_active, lifecycle_status, created_at, updated_at)
            VALUES
                (:id, :oid, :name, CAST(:schema AS jsonb), :version, FALSE, 'draft', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ),
        {
            "id": new_id,
            "oid": oid,
            "name": dup_name,
            "schema": json.dumps(schema_use),
            "version": next_v,
        },
    )
    await db.commit()
    refreshed = await _fetch_mvr_template_row_by_id(db, new_id)
    if not refreshed:
        raise HTTPException(status_code=500, detail="Duplicate failed")
    return {"status": "duplicated", "template": _mvr_template_public(refreshed)}


@router.post("/mvr-templates")
async def save_mvr_template_endpoint(body: MvrTemplateSaveBody, db: AsyncSession = Depends(get_db)):
    await _ensure_tables(db)
    oid = (body.organization_id or "default").strip() or "default"
    next_v = await _next_mvr_template_version(db, oid)
    tid = str(uuid4())
    lifecycle = "published" if body.publish else "draft"
    await db.execute(
        text(
            """
            INSERT INTO monitoring_mvr_templates
                (id, organization_id, name, schema, version, is_active, lifecycle_status, created_at, updated_at)
            VALUES
                (:id, :oid, :name, CAST(:schema AS jsonb), :version, :active, :lifecycle, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        ),
        {
            "id": tid,
            "oid": oid,
            "name": (body.name or "MVR Template").strip() or "MVR Template",
            "schema": json.dumps(body.schema if isinstance(body.schema, dict) else {}),
            "version": next_v,
            # New templates are never Live on creation; use /activate explicitly.
            "active": False,
            "lifecycle": lifecycle,
        },
    )
    await db.commit()
    row = await db.execute(
        text(
            """
            SELECT id, organization_id, name, schema, version, is_active, lifecycle_status, updated_at
            FROM monitoring_mvr_templates WHERE id = :id
            """
        ),
        {"id": tid},
    )
    rw = row.mappings().first()
    d = dict(rw) if rw else {}
    if d.get("id") is not None:
        d["id"] = str(d["id"])
    sch = d.get("schema")
    if isinstance(sch, str):
        try:
            d["schema"] = json.loads(sch)
        except Exception:
            d["schema"] = {}
    return {"status": "saved", "template": _mvr_template_public(d)}

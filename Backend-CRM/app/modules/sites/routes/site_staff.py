"""Site staff CRUD endpoints."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user_optional
from app.db import get_db

router = APIRouter()

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS site_staff (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    site_id UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    staff_id VARCHAR(50) NOT NULL,
    staff_name VARCHAR(255) NOT NULL,
    study_role VARCHAR(255) NOT NULL DEFAULT '',
    email VARCHAR(255),
    phone VARCHAR(50),
    start_date DATE,
    status VARCHAR(50) NOT NULL DEFAULT 'Active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
)
"""

_CREATE_INDEX = (
    "CREATE INDEX IF NOT EXISTS ix_site_staff_site_id ON site_staff (site_id)"
)


async def _ensure_table(db: AsyncSession) -> None:
    await db.execute(text(_CREATE_TABLE))
    await db.execute(text(_CREATE_INDEX))
    await db.commit()


# ── Pydantic schemas ────────────────────────────────────────────────────────

class StaffCreate(BaseModel):
    staff_name: str
    study_role: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    start_date: Optional[date] = None
    status: str = "Active"


class StaffUpdate(BaseModel):
    staff_id: Optional[str] = None
    staff_name: Optional[str] = None
    study_role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    start_date: Optional[date] = None
    status: Optional[str] = None


class StaffResponse(BaseModel):
    id: str
    site_id: str
    staff_id: str
    staff_name: str
    study_role: str
    email: Optional[str] = None
    phone: Optional[str] = None
    start_date: Optional[date] = None
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def _row_to_dict(row) -> dict:
    r = dict(row)
    r["id"] = str(r["id"])
    r["site_id"] = str(r["site_id"])
    return r


async def _resolve_site_uuid(db: AsyncSession, site_id: str) -> str:
    """Accept both UUID and site_id string; return the UUID."""
    try:
        uuid.UUID(site_id)
        # Already a UUID — verify it exists
        res = await db.execute(
            text("SELECT id FROM sites WHERE id = :id"),
            {"id": site_id},
        )
        row = res.first()
        if row:
            return site_id
    except ValueError:
        pass
    res = await db.execute(
        text("SELECT id FROM sites WHERE site_id = :sid"),
        {"sid": site_id},
    )
    row = res.first()
    if not row:
        raise HTTPException(status_code=404, detail="Site not found")
    return str(row[0])


# ── Routes ──────────────────────────────────────────────────────────────────

@router.get("/sites/{site_id}/staff", response_model=List[StaffResponse])
async def list_site_staff(
    site_id: str,
    db: AsyncSession = Depends(get_db),
    _: Optional[dict] = Depends(get_current_user_optional),
):
    await _ensure_table(db)
    uuid_str = await _resolve_site_uuid(db, site_id)
    rows = await db.execute(
        text(
            "SELECT * FROM site_staff WHERE site_id = :site_id ORDER BY created_at ASC"
        ),
        {"site_id": uuid_str},
    )
    return [_row_to_dict(r) for r in rows.mappings().all()]


@router.post("/sites/{site_id}/staff", response_model=StaffResponse)
async def create_site_staff(
    site_id: str,
    payload: StaffCreate,
    db: AsyncSession = Depends(get_db),
    _: Optional[dict] = Depends(get_current_user_optional),
):
    await _ensure_table(db)
    uuid_str = await _resolve_site_uuid(db, site_id)
    # Auto-generate sequential staff ID: STF-001, STF-002, …
    count_row = await db.execute(
        text("SELECT COUNT(*) FROM site_staff WHERE site_id = :site_id"),
        {"site_id": uuid_str},
    )
    current_count = count_row.scalar() or 0
    auto_staff_id = f"STF-{int(current_count) + 1:03d}"
    new_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    await db.execute(
        text(
            """
            INSERT INTO site_staff
                (id, site_id, staff_id, staff_name, study_role, email, phone, start_date, status, created_at, updated_at)
            VALUES
                (:id, :site_id, :staff_id, :staff_name, :study_role, :email, :phone, :start_date, :status, :created_at, :updated_at)
            """
        ),
        {
            "id": new_id,
            "site_id": uuid_str,
            "staff_id": auto_staff_id,
            "staff_name": payload.staff_name.strip(),
            "study_role": payload.study_role.strip(),
            "email": (payload.email or "").strip() or None,
            "phone": (payload.phone or "").strip() or None,
            "start_date": payload.start_date,
            "status": payload.status or "Active",
            "created_at": now,
            "updated_at": now,
        },
    )
    await db.commit()
    row = await db.execute(
        text("SELECT * FROM site_staff WHERE id = :id"), {"id": new_id}
    )
    return _row_to_dict(row.mappings().first())


@router.patch("/sites/{site_id}/staff/{staff_row_id}", response_model=StaffResponse)
async def update_site_staff(
    site_id: str,
    staff_row_id: str,
    payload: StaffUpdate,
    db: AsyncSession = Depends(get_db),
    _: Optional[dict] = Depends(get_current_user_optional),
):
    await _ensure_table(db)
    uuid_str = await _resolve_site_uuid(db, site_id)
    updates: dict = {}
    for field in ("staff_id", "staff_name", "study_role", "email", "phone", "status"):
        val = getattr(payload, field)
        if val is not None:
            updates[field] = val.strip() if isinstance(val, str) else val
    if payload.start_date is not None:
        updates["start_date"] = payload.start_date
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    updates["updated_at"] = datetime.now(timezone.utc)
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    await db.execute(
        text(
            f"UPDATE site_staff SET {set_clause} WHERE id = :row_id AND site_id = :site_id"
        ),
        {**updates, "row_id": staff_row_id, "site_id": uuid_str},
    )
    await db.commit()
    row = await db.execute(
        text("SELECT * FROM site_staff WHERE id = :id"), {"id": staff_row_id}
    )
    result = row.mappings().first()
    if not result:
        raise HTTPException(status_code=404, detail="Staff member not found")
    return _row_to_dict(result)


@router.delete("/sites/{site_id}/staff/{staff_row_id}")
async def delete_site_staff(
    site_id: str,
    staff_row_id: str,
    db: AsyncSession = Depends(get_db),
    _: Optional[dict] = Depends(get_current_user_optional),
):
    await _ensure_table(db)
    uuid_str = await _resolve_site_uuid(db, site_id)
    await db.execute(
        text("DELETE FROM site_staff WHERE id = :id AND site_id = :site_id"),
        {"id": staff_row_id, "site_id": uuid_str},
    )
    await db.commit()
    return {"status": "deleted"}

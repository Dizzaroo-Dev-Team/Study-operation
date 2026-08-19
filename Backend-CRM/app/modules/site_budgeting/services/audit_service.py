"""Persist CREATE/UPDATE/DELETE audit rows for site budgeting entities."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.site_budgeting.db_models import SiteBudgetingAuditLog


async def write_audit(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: UUID,
    action: str,
    user_id: Optional[str],
    old_value: Optional[dict[str, Any]] = None,
    new_value: Optional[dict[str, Any]] = None,
    cascade_level: Optional[str] = None,
    field_name: Optional[str] = None,
    justification: Optional[str] = None,
    session_id: Optional[UUID] = None,
) -> None:
    row = SiteBudgetingAuditLog(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        old_value=old_value,
        new_value=new_value,
        cascade_level=cascade_level,
        field_name=field_name,
        justification=justification,
        session_id=session_id,
        user_id=user_id,
    )
    db.add(row)

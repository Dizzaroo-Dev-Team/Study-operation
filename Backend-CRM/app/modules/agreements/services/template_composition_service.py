"""Template composition service.

Manages the ordered list of clauses inside a CLAUSE_COMPOSED StudyTemplate.
The critical surface here is validate_locked_clauses(), which is the SERVER-SIDE
enforcement layer for lock integrity.  The frontend LockedMark / ClauseBlock lock
is purely cosmetic — this function is the real gate.

All writes flush but never commit; route handlers commit.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clause import Clause, ClauseVersion, TemplateClause

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

async def get_template_clauses(
    db: AsyncSession, template_id: UUID
) -> List[TemplateClause]:
    """Return all TemplateClause rows for a template, sorted by sort_order."""
    result = await db.execute(
        select(TemplateClause)
        .where(TemplateClause.template_id == template_id)
        .order_by(TemplateClause.sort_order)
    )
    return list(result.scalars().all())


async def _get_tc(db: AsyncSession, tc_id: UUID) -> TemplateClause:
    result = await db.execute(
        select(TemplateClause).where(TemplateClause.id == tc_id)
    )
    tc = result.scalar_one_or_none()
    if tc is None:
        raise ValueError(f"TemplateClause {tc_id} not found")
    return tc


# ---------------------------------------------------------------------------
# Composition mutations
# ---------------------------------------------------------------------------

async def insert_clause_into_template(
    db: AsyncSession,
    *,
    template_id: UUID,
    clause_id: UUID,
    sort_order: Optional[int] = None,
) -> TemplateClause:
    """Add a clause to a template.

    If sort_order is None, appends after the current last clause.
    Pins current_version_id at insertion time so future clause edits don't
    silently change this template.
    """
    # Resolve the clause and pin its current version
    clause_result = await db.execute(select(Clause).where(Clause.id == clause_id))
    clause = clause_result.scalar_one_or_none()
    if clause is None:
        raise ValueError(f"Clause {clause_id} not found")

    if clause.current_version_id is None:
        raise ValueError(
            f"Clause {clause_id} has no published version yet; "
            "publish a version before inserting into a template"
        )

    # Auto sort_order: max existing + 1
    if sort_order is None:
        existing = await get_template_clauses(db, template_id)
        sort_order = (max((tc.sort_order for tc in existing), default=-1) + 1)

    # Derive initial lock/editable from the clause's own lock_policy
    from app.models.clause import LockPolicy
    is_locked  = clause.lock_policy != LockPolicy.EDITABLE
    is_editable = clause.lock_policy == LockPolicy.EDITABLE

    tc = TemplateClause(
        template_id=template_id,
        clause_id=clause_id,
        pinned_clause_version_id=clause.current_version_id,
        sort_order=sort_order,
        is_locked="true" if is_locked else "false",
        is_editable="true" if is_editable else "false",
    )
    db.add(tc)
    await db.flush()
    return tc


async def remove_clause_from_template(
    db: AsyncSession, tc_id: UUID
) -> None:
    tc = await _get_tc(db, tc_id)
    await db.delete(tc)
    await db.flush()


async def reorder_template_clauses(
    db: AsyncSession,
    template_id: UUID,
    ordered_ids: List[UUID],
) -> None:
    """Set sort_order from the supplied ordered list of TemplateClause IDs.

    All IDs must belong to the same template_id.  Gaps are fine — the list
    becomes the canonical order.
    """
    for idx, tc_id in enumerate(ordered_ids):
        await db.execute(
            update(TemplateClause)
            .where(TemplateClause.id == tc_id, TemplateClause.template_id == template_id)
            .values(sort_order=idx)
        )
    await db.flush()


async def update_clause_lock(
    db: AsyncSession,
    tc_id: UUID,
    *,
    is_locked: bool,
    is_editable: bool,
) -> TemplateClause:
    """Override the per-template lock/editable flags for one clause slot."""
    tc = await _get_tc(db, tc_id)
    tc.is_locked   = "true" if is_locked   else "false"
    tc.is_editable = "true" if is_editable else "false"
    await db.flush()
    return tc


async def save_clause_override(
    db: AsyncSession,
    tc_id: UUID,
    *,
    override_content_json: Dict[str, Any],
) -> TemplateClause:
    """Persist a per-template edit for an EDITABLE clause slot.

    Does NOT create a new ClauseVersion — the override lives only in this
    template and is not shared with other templates.
    """
    tc = await _get_tc(db, tc_id)
    if tc.is_editable != "true":
        raise ValueError(
            f"TemplateClause {tc_id} is not editable; "
            "call update_clause_lock() first to allow editing"
        )
    tc.override_content_json = override_content_json
    await db.flush()
    return tc


async def pin_clause_version(
    db: AsyncSession,
    tc_id: UUID,
    *,
    clause_version_id: UUID,
) -> TemplateClause:
    """Change which version this template slot is pinned to.

    Clears any existing override (the new version's content supersedes it).
    """
    tc = await _get_tc(db, tc_id)
    # Verify the version belongs to the right clause
    cv_result = await db.execute(
        select(ClauseVersion).where(ClauseVersion.id == clause_version_id)
    )
    cv = cv_result.scalar_one_or_none()
    if cv is None:
        raise ValueError(f"ClauseVersion {clause_version_id} not found")
    if cv.clause_id != tc.clause_id:
        raise ValueError(
            f"ClauseVersion {clause_version_id} does not belong to clause {tc.clause_id}"
        )
    tc.pinned_clause_version_id = clause_version_id
    tc.override_content_json = None  # clear stale override
    await db.flush()
    return tc


# ---------------------------------------------------------------------------
# SERVER-SIDE LOCK VALIDATION  (the real security gate)
# ---------------------------------------------------------------------------

def _extract_clause_blocks(doc: Dict[str, Any]) -> Dict[str, Any]:
    """Walk a Tiptap JSON doc and return {clauseId: content_array} for every
    clauseBlock node found in the top-level content."""
    out: Dict[str, Any] = {}
    for node in doc.get("content", []):
        if node.get("type") == "clauseBlock":
            attrs = node.get("attrs", {})
            cid = attrs.get("clauseId")
            if cid:
                out[str(cid)] = node.get("content", [])
    return out


def _content_hash(content: Any) -> str:
    """Stable hash of Tiptap JSON content for equality comparison."""
    return json.dumps(content, sort_keys=True, ensure_ascii=False)


async def validate_locked_clauses(
    db: AsyncSession,
    template_id: UUID,
    incoming_doc: Dict[str, Any],
) -> List[str]:
    """Compare locked clause content in the incoming doc against pinned versions.

    Returns a list of violation strings (empty = all locked clauses intact).
    The route handler should reject the save with HTTP 422 if this is non-empty.

    Algorithm:
      1. Load all TemplateClause rows for this template.
      2. For each locked clause (is_locked == 'true'):
         a. Resolve the pinned ClauseVersion content.
         b. Extract the matching clauseBlock from the incoming doc.
         c. Compare the inner content arrays as stable JSON.
         d. If different → violation.
    """
    template_clauses = await get_template_clauses(db, template_id)
    locked_tcs = [tc for tc in template_clauses if tc.is_locked == "true"]

    if not locked_tcs:
        return []

    incoming_blocks = _extract_clause_blocks(incoming_doc)
    violations: List[str] = []

    for tc in locked_tcs:
        clause_id_str = str(tc.clause_id)

        # Resolve the authoritative content
        version_id = tc.pinned_clause_version_id
        if version_id is None:
            # Fall back to the clause's current version
            cl_result = await db.execute(
                select(Clause).where(Clause.id == tc.clause_id)
            )
            clause = cl_result.scalar_one_or_none()
            if clause is None or clause.current_version_id is None:
                continue  # Can't validate; skip gracefully
            version_id = clause.current_version_id

        cv_result = await db.execute(
            select(ClauseVersion).where(ClauseVersion.id == version_id)
        )
        cv = cv_result.scalar_one_or_none()
        if cv is None:
            continue

        authoritative_content = cv.content_json.get("content", [])

        if clause_id_str not in incoming_blocks:
            violations.append(
                f"Locked clause '{clause_id_str}' is missing from the submitted document"
            )
            continue

        incoming_content = incoming_blocks[clause_id_str]

        if _content_hash(authoritative_content) != _content_hash(incoming_content):
            violations.append(
                f"Locked clause '{clause_id_str}' content has been altered. "
                "Locked clauses cannot be modified."
            )

    return violations

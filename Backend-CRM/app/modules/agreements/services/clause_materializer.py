"""Clause materializer.

Converts a CLAUSE_COMPOSED StudyTemplate into one flat Tiptap JSON document
by:
  1. Loading template_clauses sorted by sort_order
  2. Resolving each clause's content (override → pinned version → current version)
  3. Wrapping each in a clauseBlock Tiptap node carrying identity metadata
  4. Concatenating into a single {type: "doc", content: [...]} structure
  5. Optionally resolving {{placeholder}} tokens against an Agreement context

The output shape is intentionally identical to AgreementDocument.document_content
so the rest of the agreement pipeline (signing, hashing, DOCX export) sees no
difference.
"""
from __future__ import annotations

import copy
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.clause import Clause, ClauseVersion, TemplateClause
from app.models.agreement import StudyTemplate, CompositionMode

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _resolve_version_content(
    db: AsyncSession,
    tc: TemplateClause,
) -> Optional[Dict[str, Any]]:
    """Return the Tiptap JSON content for one TemplateClause slot.

    Priority: override_content_json > pinned version > clause current version.
    Returns None if no content can be resolved (caller skips this slot).
    """
    # 1. Per-template override (EDITABLE clause edited in this template)
    if tc.override_content_json:
        return tc.override_content_json

    # 2. Pinned ClauseVersion
    version_id = tc.pinned_clause_version_id
    if version_id is None:
        # 3. Fall back to clause.current_version_id
        cl_result = await db.execute(
            select(Clause).where(Clause.id == tc.clause_id)
        )
        clause = cl_result.scalar_one_or_none()
        if clause is None or clause.current_version_id is None:
            logger.warning(
                "materialize: clause %s has no version; skipping", tc.clause_id
            )
            return None
        version_id = clause.current_version_id

    cv_result = await db.execute(
        select(ClauseVersion).where(ClauseVersion.id == version_id)
    )
    cv = cv_result.scalar_one_or_none()
    if cv is None:
        logger.warning(
            "materialize: ClauseVersion %s not found; skipping", version_id
        )
        return None

    return cv.content_json  # {"type": "doc", "content": [...]}


def _build_clause_block_node(
    tc: TemplateClause,
    clause: Clause,
    version_id: Optional[UUID],
    inner_content: List[Any],
) -> Dict[str, Any]:
    """Wrap clause content blocks in a clauseBlock Tiptap node.

    The attrs are stored in the document JSON so the frontend ClauseBlock
    extension can render the correct visual state (lock badge, etc.) without
    an additional API call.
    """
    return {
        "type": "clauseBlock",
        "attrs": {
            "clauseId":    str(tc.clause_id),
            "versionId":   str(version_id) if version_id else None,
            "lockPolicy":  clause.lock_policy.value if clause.lock_policy else "STANDARD_LOCKED",
            "isLocked":    tc.is_locked == "true",
            "isEditable":  tc.is_editable == "true",
            "clauseTitle": clause.title,
            "category":    clause.category,
        },
        "content": copy.deepcopy(inner_content),
    }


def _resolve_placeholders_in_json(
    node: Any,
    resolved_values: Dict[str, str],
) -> Any:
    """Walk a Tiptap JSON node tree and replace {{TOKEN}} in text nodes.

    resolved_values keys must be UPPER-CASE.  Operates on a deep copy so the
    original pinned content is never mutated.
    """
    if isinstance(node, str):
        import re
        def _replace(m: re.Match) -> str:
            token = m.group(1).strip().upper()
            return resolved_values.get(token, m.group(0))  # leave unfilled if unknown
        # Possessive [^{}]++ (Py3.11+): linear scan, no backtracking. The old
        # \s*(...+?)\s* flanks were ambiguous (super-linear); the .strip()
        # above already handles surrounding whitespace in the token.
        return re.sub(r"\{\{([^{}]++)\}\}", _replace, node)

    if isinstance(node, list):
        return [_resolve_placeholders_in_json(item, resolved_values) for item in node]

    if isinstance(node, dict):
        return {k: _resolve_placeholders_in_json(v, resolved_values) for k, v in node.items()}

    return node


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def materialize_template(
    db: AsyncSession,
    template_id: UUID,
    *,
    agreement: Optional[Any] = None,
) -> Dict[str, Any]:
    """Convert a CLAUSE_COMPOSED template to one Tiptap JSON document.

    Args:
        db:          Async DB session.
        template_id: The StudyTemplate to materialise.
        agreement:   Optional Agreement ORM object.  When provided, placeholder
                     tokens ({{site_name}} etc.) are resolved against it using
                     the existing resolve_field_mapping_values() machinery.

    Returns:
        A dict shaped like AgreementDocument.document_content:
        {"type": "doc", "content": [<clauseBlock>, ...]}

    Raises:
        ValueError: if the template is not CLAUSE_COMPOSED or doesn't exist.
    """
    # --- Load template -------------------------------------------------------
    tmpl_result = await db.execute(
        select(StudyTemplate).where(StudyTemplate.id == template_id)
    )
    template = tmpl_result.scalar_one_or_none()
    if template is None:
        raise ValueError(f"StudyTemplate {template_id} not found")
    if template.composition_mode != CompositionMode.CLAUSE_COMPOSED:
        raise ValueError(
            f"StudyTemplate {template_id} is in {template.composition_mode.value} mode; "
            "only CLAUSE_COMPOSED templates can be materialised"
        )

    # --- Load template_clauses in order --------------------------------------
    tc_result = await db.execute(
        select(TemplateClause)
        .where(TemplateClause.template_id == template_id)
        .order_by(TemplateClause.sort_order)
    )
    template_clauses: List[TemplateClause] = list(tc_result.scalars().all())

    if not template_clauses:
        logger.warning("materialize_template: template %s has no clauses", template_id)
        return {"type": "doc", "content": []}

    # --- Resolve placeholder values once (expensive — only if agreement given)
    resolved_values: Dict[str, str] = {}
    if agreement is not None:
        try:
            from app.modules.agreements.services.placeholder_fill import (
                resolve_field_mapping_values,
            )
            field_mappings = getattr(template, "field_mappings", None)
            resolved_values = await resolve_field_mapping_values(field_mappings, agreement, db)
        except Exception as exc:
            logger.warning("materialize_template: placeholder resolution failed: %s", exc)

    # --- Build output nodes --------------------------------------------------
    output_nodes: List[Dict[str, Any]] = []

    for tc in template_clauses:
        # Load clause identity (for title, lock_policy, category)
        cl_result = await db.execute(select(Clause).where(Clause.id == tc.clause_id))
        clause = cl_result.scalar_one_or_none()
        if clause is None:
            logger.warning("materialize_template: clause %s missing; skipping", tc.clause_id)
            continue

        # Resolve the content JSON for this slot
        content_doc = await _resolve_version_content(db, tc)
        if content_doc is None:
            continue

        # Extract the inner block array from the stored doc
        # Stored shape: {"type": "doc", "content": [...block nodes...]}
        inner_content: List[Any] = content_doc.get("content", [])
        if not inner_content:
            continue

        # Resolve which version_id we actually used (for the node attrs)
        resolved_version_id = tc.pinned_clause_version_id or clause.current_version_id

        # Apply placeholders if we have resolution context
        if resolved_values:
            inner_content = _resolve_placeholders_in_json(inner_content, resolved_values)

        block = _build_clause_block_node(tc, clause, resolved_version_id, inner_content)
        output_nodes.append(block)

    result_doc = {"type": "doc", "content": output_nodes}
    logger.info(
        "materialize_template: template %s → %d clause blocks",
        template_id, len(output_nodes),
    )
    return result_doc


async def materialize_and_create_document(
    db: AsyncSession,
    template_id: UUID,
    agreement_id: UUID,
    *,
    created_by: Optional[str] = None,
) -> Any:
    """Materialize a CLAUSE_COMPOSED template and persist the result as a new
    AgreementDocument.  Pins the materialised snapshot (version_number auto).

    Returns the AgreementDocument ORM object (caller must commit).
    """
    from app.models.agreement import Agreement, AgreementDocument
    from sqlalchemy import func

    # Load agreement for placeholder fill
    ag_result = await db.execute(select(Agreement).where(Agreement.id == agreement_id))
    agreement = ag_result.scalar_one_or_none()
    if agreement is None:
        raise ValueError(f"Agreement {agreement_id} not found")

    materialized = await materialize_template(db, template_id, agreement=agreement)

    # Next version number
    max_result = await db.execute(
        select(func.max(AgreementDocument.version_number)).where(
            AgreementDocument.agreement_id == agreement_id
        )
    )
    current_max = max_result.scalar_one_or_none()
    next_version = (current_max or 0) + 1

    doc = AgreementDocument(
        agreement_id=agreement_id,
        version_number=next_version,
        document_content=materialized,
        created_from_template_id=template_id,
        created_by=created_by,
    )
    db.add(doc)
    await db.flush()
    return doc

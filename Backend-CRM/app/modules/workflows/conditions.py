"""
conditions.py
=============

Evaluates a structured Condition against an instance's context dictionary.

There is deliberately NO use of eval/exec. Conditions are data: a tree of AND/OR
groups whose leaves are simple comparisons. This keeps the platform safe even
though non-programmers build the rules through the drag-and-drop UI.

PURE LOGIC — touches no DB, stays synchronous.
"""

from __future__ import annotations

from typing import Any

from .schemas import Clause, Condition, ConditionOperator


def _missing(context: dict[str, Any], field: str) -> bool:
    return field not in context or context[field] is None


# Operators that test PRESENCE/ABSENCE of a field. A decision branch built on
# these is meaningful precisely when the field is unset, so such fields must NOT
# make a decision "pending an answer" (see engine._decision_fields).
_PRESENCE_OPS = {ConditionOperator.EXISTS, ConditionOperator.NOT_EXISTS}


def referenced_fields(
    condition: "Condition | Clause | dict | None",
    *, exclude_presence_ops: bool = False,
) -> set[str]:
    """Collect every context field name a condition reads. Walks the AND/OR tree.

    GENERAL — used by the engine to discover a decision step's variable(s) from its
    own transitions, with no per-workflow knowledge. When ``exclude_presence_ops`` is
    set, clauses using EXISTS / NOT_EXISTS are skipped (those branch on absence, so
    they should not force the decision to wait for a value)."""
    if condition is None:
        return set()
    if isinstance(condition, Clause):
        if exclude_presence_ops and condition.op in _PRESENCE_OPS:
            return set()
        return {condition.field}
    if isinstance(condition, dict):
        if "field" in condition:
            return referenced_fields(Clause(**condition), exclude_presence_ops=exclude_presence_ops)
        return referenced_fields(Condition(**condition), exclude_presence_ops=exclude_presence_ops)
    # Condition group: union over its nodes.
    out: set[str] = set()
    for node in (condition.all or []) + (condition.any or []):
        out |= referenced_fields(node, exclude_presence_ops=exclude_presence_ops)
    return out


def evaluate_clause(clause: Clause, context: dict[str, Any]) -> bool:
    op = clause.op
    actual = context.get(clause.field)

    if op == ConditionOperator.EXISTS:
        return not _missing(context, clause.field)
    if op == ConditionOperator.NOT_EXISTS:
        return _missing(context, clause.field)
    if op == ConditionOperator.IS_TRUE:
        return bool(actual) is True
    if op == ConditionOperator.IS_FALSE:
        return bool(actual) is False

    # Operators below need a present value; a missing value is simply False.
    if _missing(context, clause.field):
        return False

    expected = clause.value
    try:
        if op == ConditionOperator.EQ:
            return actual == expected
        if op == ConditionOperator.NEQ:
            return actual != expected
        if op == ConditionOperator.GT:
            return actual > expected
        if op == ConditionOperator.GTE:
            return actual >= expected
        if op == ConditionOperator.LT:
            return actual < expected
        if op == ConditionOperator.LTE:
            return actual <= expected
        if op == ConditionOperator.IN:
            return actual in (expected or [])
        if op == ConditionOperator.NOT_IN:
            return actual not in (expected or [])
    except TypeError:
        # e.g. comparing a number to a string — treat as not-matching rather than crash
        return False

    raise ValueError(f"Unsupported operator: {op}")


def evaluate_condition(condition: Condition | None, context: dict[str, Any]) -> bool:
    """A None condition always passes (unconditional transition)."""
    if condition is None:
        return True

    if condition.all is not None:
        return all(_evaluate_node(node, context) for node in condition.all)
    if condition.any is not None:
        return any(_evaluate_node(node, context) for node in condition.any)
    # Empty condition object => pass.
    return True


def _evaluate_node(node, context: dict[str, Any]) -> bool:
    if isinstance(node, Clause):
        return evaluate_clause(node, context)
    if isinstance(node, Condition):
        return evaluate_condition(node, context)
    # Pydantic may hand us dicts when nested; normalise.
    if isinstance(node, dict):
        if "field" in node:
            return evaluate_clause(Clause(**node), context)
        return evaluate_condition(Condition(**node), context)
    raise TypeError(f"Unknown condition node: {node!r}")

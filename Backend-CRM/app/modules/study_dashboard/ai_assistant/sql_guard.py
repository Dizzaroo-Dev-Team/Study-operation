"""
Defense-in-depth SQL validator for the AI-generated query path.

This is NOT a full SQL parser. Its job is to catch obvious mistakes and
malicious output from the LLM before we hand the query to Postgres. The
backstop is the executor in service.py which always wraps the query in
SET TRANSACTION READ ONLY + statement_timeout, so even a bypass here cannot
mutate data.

Rules enforced:
  - Strip line comments (-- ...) and block comments (/* ... */).
  - Must start with SELECT or WITH (case-insensitive).
  - No multi-statement: any ';' before the final character is rejected.
  - Reject DDL/DML/transactional keywords as standalone tokens.
  - Every table reference after FROM/JOIN must be in ALLOWED_TABLES (or be
    a CTE name introduced earlier in a WITH clause).
  - Append ' LIMIT 1000' if no LIMIT clause is present at the top level.
"""
from __future__ import annotations

import re
from typing import Iterable


class SqlGuardError(ValueError):
    """Raised when the LLM-generated SQL fails validation."""


_FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE", "CREATE",
    "GRANT", "REVOKE", "COPY", "MERGE", "CALL", "DO", "VACUUM", "ANALYZE",
    "REINDEX", "CLUSTER", "LOCK", "NOTIFY", "LISTEN", "BEGIN", "COMMIT",
    "ROLLBACK", "SAVEPOINT", "SET", "RESET", "INTO",
}

# Match "EXPLAIN ANALYZE" as a phrase (ANALYZE alone is also forbidden above)
_EXPLAIN_ANALYZE_RE = re.compile(r"\bEXPLAIN\s+ANALYZE\b", re.IGNORECASE)

_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_LINE_COMMENT_RE = re.compile(r"--[^\n]*")

_TABLE_REF_RE = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_][A-Za-z0-9_]*)", re.IGNORECASE)

_CTE_NAME_RE = re.compile(
    r"\bWITH\s+(?:RECURSIVE\s+)?([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(", re.IGNORECASE
)
# Additional CTE names after the first one ("WITH a AS (...), b AS (...)")
_ADDITIONAL_CTE_RE = re.compile(r"\)\s*,\s*([A-Za-z_][A-Za-z0-9_]*)\s+AS\s*\(", re.IGNORECASE)

_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)


def _strip_comments(sql: str) -> str:
    sql = _BLOCK_COMMENT_RE.sub(" ", sql)
    sql = _LINE_COMMENT_RE.sub(" ", sql)
    return sql


def _extract_cte_names(sql: str) -> set[str]:
    names: set[str] = set()
    m = _CTE_NAME_RE.search(sql)
    if m:
        names.add(m.group(1).lower())
    for m2 in _ADDITIONAL_CTE_RE.finditer(sql):
        names.add(m2.group(1).lower())
    return names


def _tokenize_keywords(sql: str) -> set[str]:
    return {tok.upper() for tok in re.findall(r"\b[A-Za-z_]+\b", sql)}


def validate_and_normalize_sql(sql: str, allowed_tables: Iterable[str]) -> str:
    if not isinstance(sql, str):
        raise SqlGuardError("SQL must be a string")
    cleaned = _strip_comments(sql).strip()
    if not cleaned:
        raise SqlGuardError("Empty SQL")

    # Trailing semicolon is allowed; anything before the end isn't.
    if cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if ";" in cleaned:
        raise SqlGuardError("Multiple statements are not allowed")

    head = cleaned.split(None, 1)[0].upper()
    if head not in {"SELECT", "WITH"}:
        raise SqlGuardError(f"Only SELECT / WITH queries are allowed (got '{head}')")

    if _EXPLAIN_ANALYZE_RE.search(cleaned):
        raise SqlGuardError("EXPLAIN ANALYZE is not allowed (it executes the query)")

    tokens = _tokenize_keywords(cleaned)
    forbidden_hits = tokens & _FORBIDDEN_KEYWORDS
    if forbidden_hits:
        raise SqlGuardError(
            f"Forbidden keyword(s) in SQL: {', '.join(sorted(forbidden_hits))}"
        )

    cte_names = _extract_cte_names(cleaned)
    allowed = {t.lower() for t in allowed_tables} | cte_names

    referenced = {m.group(1).lower() for m in _TABLE_REF_RE.finditer(cleaned)}
    unknown = referenced - allowed
    if unknown:
        raise SqlGuardError(
            f"Reference to non-allowlisted table(s): {', '.join(sorted(unknown))}"
        )

    if not _LIMIT_RE.search(cleaned):
        cleaned = f"{cleaned} LIMIT 1000"

    return cleaned

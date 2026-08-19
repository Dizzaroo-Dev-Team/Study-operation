"""Shared monitoring backend helpers (Phase 8 deduplication)."""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


def effective_visit_status(
    status: Any,
    closed_at: Any = None,
    *,
    default: str = "Scheduled",
) -> str:
    """Normalize visit status for API responses."""
    text = str(status or "").strip()
    if text.lower() == "archived":
        return "Archived"
    if closed_at is not None:
        return "Closed"
    return text or default


def relative_time_label(dt: Any, now: Optional[datetime] = None) -> str:
    """Human-readable relative timestamp for notifications and activity feeds."""
    ref = now or datetime.now(timezone.utc)
    try:
        if dt is None:
            return "Just now"
        if getattr(dt, "tzinfo", None) is None:
            dt = dt.replace(tzinfo=timezone.utc)
        delta_seconds = max(0, int((ref - dt).total_seconds()))
        if delta_seconds < 60:
            return "Just now"
        if delta_seconds < 3600:
            mins = max(1, delta_seconds // 60)
            return f"{mins} minute{'s' if mins != 1 else ''} ago"
        if delta_seconds < 86400:
            hrs = delta_seconds // 3600
            return f"{hrs} hour{'s' if hrs != 1 else ''} ago"
        days = delta_seconds // 86400
        if days <= 7:
            return f"{days} day{'s' if days != 1 else ''} ago"
        return dt.strftime("%b %d, %Y")
    except Exception:
        return "Just now"


def site_profile_join_sql(*, sites_alias: str = "s", profiles_alias: str = "sp") -> str:
    """Standard LEFT JOIN from sites to site_profiles."""
    return (
        f"LEFT JOIN site_profiles {profiles_alias} "
        f"ON {profiles_alias}.site_id = {sites_alias}.id"
    )


async def resolve_monitor_study_id(
    db: AsyncSession,
    *,
    study_name: str = "",
    study_pg_id: str = "",
) -> Optional[str]:
    """Resolve the study key stored on monitoring_visits.

    Prefer the Postgres id sent from the top-bar selector. When falling back to
    name lookup, deprioritize placeholder study_id values like 'New study' when
    duplicate study names exist.
    """
    pg = (study_pg_id or "").strip()
    if pg:
        row = await db.execute(
            text(
                """
                SELECT COALESCE(NULLIF(TRIM(study_id), ''), CAST(id AS TEXT)) AS sid
                FROM studies
                WHERE CAST(id AS TEXT) = :pg OR study_id = :pg
                LIMIT 1
                """
            ),
            {"pg": pg},
        )
        matched = row.mappings().first()
        if matched and matched.get("sid"):
            return str(matched["sid"])

    name = (study_name or "").strip()
    if not name:
        return None

    row = await db.execute(
        text(
            """
            SELECT COALESCE(NULLIF(TRIM(study_id), ''), CAST(id AS TEXT)) AS sid
            FROM studies
            WHERE name = :name OR study_id = :name
            ORDER BY
                CASE WHEN lower(trim(coalesce(study_id, ''))) = 'new study' THEN 1 ELSE 0 END,
                study_id NULLS LAST
            LIMIT 1
            """
        ),
        {"name": name},
    )
    matched = row.mappings().first()
    return str(matched["sid"]) if matched and matched.get("sid") else name


async def resolve_monitor_site_id(
    db: AsyncSession,
    *,
    site_name: str = "",
    site_pg_id: str = "",
) -> Optional[str]:
    """Resolve the site key stored on monitoring_visits."""
    pg = (site_pg_id or "").strip()
    if pg:
        row = await db.execute(
            text(
                """
                SELECT COALESCE(NULLIF(TRIM(site_id), ''), CAST(id AS TEXT)) AS sid
                FROM sites
                WHERE CAST(id AS TEXT) = :pg OR site_id = :pg
                LIMIT 1
                """
            ),
            {"pg": pg},
        )
        matched = row.mappings().first()
        if matched and matched.get("sid"):
            return str(matched["sid"])

    name = (site_name or "").strip()
    if not name:
        return None

    row = await db.execute(
        text(
            """
            SELECT COALESCE(NULLIF(TRIM(site_id), ''), CAST(id AS TEXT)) AS sid
            FROM sites
            WHERE name = :name OR site_id = :name
            LIMIT 1
            """
        ),
        {"name": name},
    )
    matched = row.mappings().first()
    return str(matched["sid"]) if matched and matched.get("sid") else name


def dashboard_study_filter_sql() -> str:
    """Match visits for a study filter, including duplicate study name rows."""
    return """
        (
            v.study_id = :study_id OR CAST(v.study_id AS TEXT) = :study_id
            OR EXISTS (
                SELECT 1 FROM studies st_filter
                WHERE (
                    st_filter.study_id = :study_id
                    OR CAST(st_filter.id AS TEXT) = :study_id
                    OR st_filter.name = :study_id
                )
                AND EXISTS (
                    SELECT 1 FROM studies st_v
                    WHERE st_v.name = st_filter.name
                      AND (
                          v.study_id = st_v.study_id
                          OR CAST(v.study_id AS TEXT) = CAST(st_v.id AS TEXT)
                          OR v.study_id = st_v.name
                      )
                )
            )
        )
    """


def dashboard_site_filter_sql() -> str:
    """Match visits for a site filter across id / site_id / name aliases."""
    return """
        (
            v.site_id = :site_id OR CAST(v.site_id AS TEXT) = :site_id
            OR EXISTS (
                SELECT 1 FROM sites s
                WHERE (s.site_id = :site_id OR CAST(s.id AS TEXT) = :site_id)
                  AND (
                      v.site_id = s.site_id
                      OR CAST(v.site_id AS TEXT) = CAST(s.id AS TEXT)
                      OR v.site_id = s.name
                  )
            )
        )
    """


def _inline_markdown_to_html(text: str) -> str:
    """Bold/italic for a single line — escapes HTML first, then applies inline markdown."""
    out: list[str] = []
    pos = 0
    for match in re.finditer(r"\*\*(.+?)\*\*|\*(.+?)\*", text):
        out.append(html.escape(text[pos : match.start()]))
        if match.group(1) is not None:
            out.append(f"<strong>{html.escape(match.group(1))}</strong>")
        else:
            out.append(f"<em>{html.escape(match.group(2) or '')}</em>")
        pos = match.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def markdown_summary_to_html(text: str) -> str:
    """Convert common markdown (headings, bullets, bold) to email-safe HTML."""
    if not text:
        return ""
    lines = text.splitlines()
    parts: list[str] = []
    in_ul = False

    def close_ul() -> None:
        nonlocal in_ul
        if in_ul:
            parts.append("</ul>")
            in_ul = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            close_ul()
            parts.append("<br/>")
            continue

        heading = re.match(r"^(#{1,3})\s++(.*)$", stripped)
        if heading:
            close_ul()
            level = len(heading.group(1))
            inner = _inline_markdown_to_html(heading.group(2))
            if level == 1:
                parts.append(
                    f'<h2 style="margin:14px 0 8px;font-size:17px;font-weight:700;color:#1e293b">{inner}</h2>'
                )
            elif level == 2:
                parts.append(
                    f'<h3 style="margin:12px 0 6px;font-size:15px;font-weight:600;color:#1e293b">{inner}</h3>'
                )
            else:
                parts.append(
                    f'<h4 style="margin:10px 0 4px;font-size:14px;font-weight:600;color:#334155">{inner}</h4>'
                )
            continue

        bullet = re.match(r"^[-*]\s++(.*)$", stripped)
        if bullet:
            if not in_ul:
                parts.append('<ul style="margin:8px 0 12px;padding-left:22px">')
                in_ul = True
            parts.append(f'<li style="margin:5px 0;line-height:1.5">{_inline_markdown_to_html(bullet.group(1))}</li>')
            continue

        close_ul()
        parts.append(f'<p style="margin:8px 0;line-height:1.55">{_inline_markdown_to_html(stripped)}</p>')

    close_ul()
    return "".join(parts)


def markdown_summary_to_plain(text: str) -> str:
    """Strip markdown markers for plain-text email fallbacks."""
    if not text:
        return ""
    plain = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    plain = re.sub(r"(?<!\*)\*([^*]+?)\*(?!\*)", r"\1", plain)
    plain = re.sub(r"^#{1,6}\s+", "", plain, flags=re.MULTILINE)
    return plain

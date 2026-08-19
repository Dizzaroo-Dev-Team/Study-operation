"""Unit tests for monitoring shared helpers (dashboard + notification utilities)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.modules.monitoring.utils import (
    dashboard_site_filter_sql,
    dashboard_study_filter_sql,
    effective_visit_status,
    markdown_summary_to_html,
    markdown_summary_to_plain,
    relative_time_label,
)


def test_effective_visit_status_archived():
    assert effective_visit_status("archived") == "Archived"
    assert effective_visit_status("Archived", closed_at=datetime.now(timezone.utc)) == "Archived"


def test_effective_visit_status_closed_when_closed_at_set():
    assert effective_visit_status("Scheduled", closed_at=datetime.now(timezone.utc)) == "Closed"


def test_effective_visit_status_defaults_to_scheduled():
    assert effective_visit_status(None) == "Scheduled"
    assert effective_visit_status("") == "Scheduled"


def test_relative_time_label_just_now():
    now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    assert relative_time_label(now - timedelta(seconds=30), now=now) == "Just now"


def test_relative_time_label_minutes_and_hours():
    now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    assert relative_time_label(now - timedelta(minutes=5), now=now) == "5 minutes ago"
    assert relative_time_label(now - timedelta(hours=2), now=now) == "2 hours ago"


def test_relative_time_label_days_and_absolute_date():
    now = datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)
    assert relative_time_label(now - timedelta(days=3), now=now) == "3 days ago"
    old = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)
    assert relative_time_label(old, now=now) == "Jan 15, 2026"


def test_dashboard_filter_sql_references_study_and_site_params():
    study_sql = dashboard_study_filter_sql()
    site_sql = dashboard_site_filter_sql()
    assert ":study_id" in study_sql
    assert "studies" in study_sql
    assert ":site_id" in site_sql
    assert "sites" in site_sql


def test_markdown_summary_to_html_headings_and_bullets():
    md = "# Title\n\n- First **bold** item\n- Second item"
    html = markdown_summary_to_html(md)
    assert "<h2" in html
    assert "<ul" in html
    assert "<strong>bold</strong>" in html


def test_markdown_summary_to_plain_strips_markers():
    md = "## Heading\n\n**Important** note"
    plain = markdown_summary_to_plain(md)
    assert "**" not in plain
    assert "Important" in plain
    assert plain.startswith("Heading")

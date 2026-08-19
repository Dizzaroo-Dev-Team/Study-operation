"""Unit tests for monitoring findings ID + severity helpers."""
from __future__ import annotations

from app.modules.monitoring.routes.findings import (
    _due_color_for_severity,
    _finding_display_code,
    _next_per_visit_finding_id,
    _scoped_finding_id_prefix,
)


def test_scoped_finding_id_prefix():
    assert _scoped_finding_id_prefix("MON-123") == "MON-123__F-"


def test_next_per_visit_finding_id_sequential():
    visit_id = "MON-ABC"
    assert _next_per_visit_finding_id(visit_id, []) == "MON-ABC__F-01"
    assert _next_per_visit_finding_id(visit_id, ["MON-ABC__F-01", "MON-ABC__F-02"]) == "MON-ABC__F-03"


def test_next_per_visit_finding_id_ignores_other_visits():
    visit_id = "MON-XYZ"
    existing = ["MON-OTHER__F-99", "MON-XYZ__F-04"]
    assert _next_per_visit_finding_id(visit_id, existing) == "MON-XYZ__F-05"


def test_due_color_for_severity():
    assert _due_color_for_severity("critical") == "red"
    assert _due_color_for_severity("major") == "orange"
    assert _due_color_for_severity("minor") == "muted"


def test_finding_display_code():
    assert _finding_display_code("MON-1__F-07") == "F-07"

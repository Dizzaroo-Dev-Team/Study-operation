"""Unit tests for /api/monitor session auth and public magic-link routes."""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.modules.monitoring.auth import _is_monitor_public_route, require_monitor_auth


@pytest.mark.parametrize(
    "path,method,expected",
    [
        ("/api/monitor/visits/MON-1/reschedule", "GET", True),
        ("/api/monitor/visits/MON-1/reschedule", "POST", True),
        ("/api/monitor/visits/MON-1/visit-report/review", "GET", True),
        ("/api/monitor/visits/MON-1/visit-report/review/approve", "POST", True),
        ("/api/monitor/visits/MON-1/confirmation-letter/confirm-data", "GET", True),
        ("/api/monitor/visits/MON-1/confirmation-letter/confirm", "GET", True),
        ("/api/monitor/visits/MON-1/pre-visit/acknowledge", "POST", True),
        ("/api/monitor/visits/MON-1/acknowledge", "POST", True),
        ("/api/monitor/dashboard", "GET", False),
        ("/api/monitor/visits/MON-1/overview", "GET", False),
        ("/api/monitor/visits/MON-1/visit-report", "PUT", False),
    ],
)
def test_is_monitor_public_route(path: str, method: str, expected: bool):
    assert _is_monitor_public_route(path, method) is expected


@pytest.mark.asyncio
async def test_require_monitor_auth_allows_public_route_without_user():
    class _Req:
        url = type("U", (), {"path": "/api/monitor/visits/MON-1/visit-report/review"})()
        method = "GET"

    result = await require_monitor_auth(_Req(), user=None)
    assert result is None


@pytest.mark.asyncio
async def test_require_monitor_auth_blocks_protected_route_without_user():
    class _Req:
        url = type("U", (), {"path": "/api/monitor/dashboard"})()
        method = "GET"

    with pytest.raises(HTTPException) as exc:
        await require_monitor_auth(_Req(), user=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_require_monitor_auth_allows_protected_route_with_user():
    class _Req:
        url = type("U", (), {"path": "/api/monitor/dashboard"})()
        method = "GET"

    user = {"email": "cra@test.com"}
    result = await require_monitor_auth(_Req(), user=user)
    assert result is user

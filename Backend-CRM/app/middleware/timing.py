"""Request-duration timing middleware.

Records per-request latency for every HTTP request. Latency is:
  * always logged at INFO when over the slow-threshold (default 500ms),
  * always exported as a Prometheus Histogram when `prometheus_client` is
    installed (graceful no-op otherwise so the app still boots in dev),
  * always added to the response as `X-Response-Time-ms` to aid manual debugging.

Route label uses the matched Starlette route template (e.g. /api/conversations/{id})
to keep cardinality bounded — using the raw path would explode the histogram on
endpoints that include UUIDs.

Usage (in app/main.py):

    from app.middleware.timing import install_timing_middleware
    install_timing_middleware(app)

If you also want a /metrics endpoint:

    from app.middleware.timing import mount_metrics_endpoint
    mount_metrics_endpoint(app)
"""

from __future__ import annotations

import logging
import time
from typing import Optional

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.timing")

# ---------------------------------------------------------------------------
# Optional Prometheus integration. Soft-import so the app still boots without
# the dependency installed (e.g. on a fresh dev machine).
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import-time switch
    from prometheus_client import (
        CONTENT_TYPE_LATEST,
        CollectorRegistry,
        Counter,
        Histogram,
        generate_latest,
    )

    _PROM_AVAILABLE = True
except Exception:  # pragma: no cover
    _PROM_AVAILABLE = False
    CONTENT_TYPE_LATEST = "text/plain; version=0.0.4"  # type: ignore[assignment]


# A dedicated registry so we don't pollute the default one (which uvicorn
# reload would otherwise re-register and crash).
_registry = None
_request_duration = None
_request_count = None

if _PROM_AVAILABLE:
    _registry = CollectorRegistry()
    _request_duration = Histogram(
        "http_request_duration_seconds",
        "HTTP request latency in seconds, labeled by method/route/status.",
        labelnames=("method", "route", "status"),
        # Buckets tuned for an API: <50ms healthy, 50-500ms acceptable,
        # >500ms slow, >2s painful.
        buckets=(0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
        registry=_registry,
    )
    _request_count = Counter(
        "http_requests_total",
        "Total number of HTTP requests handled.",
        labelnames=("method", "route", "status"),
        registry=_registry,
    )


# Threshold above which we log every slow request, even when prometheus is
# scraping. Pulled from env at import to allow per-environment tuning without
# code changes (e.g. SLOW_REQUEST_MS=200 in prod).
import os

_SLOW_REQUEST_MS = int(os.getenv("SLOW_REQUEST_MS", "500"))


def _route_template(request: Request) -> str:
    """Return the matched route template, or the raw path if unmatched.

    Without this, every request to /api/conversations/<uuid>/messages produces
    a new histogram series — unbounded label cardinality kills Prometheus.
    """
    route = request.scope.get("route")
    path = getattr(route, "path", None)
    if path:
        return path
    return request.url.path


class TimingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        status = "500"
        response: Optional[Response] = None
        try:
            response = await call_next(request)
            status = str(response.status_code)
            return response
        finally:
            duration = time.perf_counter() - start
            route = _route_template(request)
            method = request.method

            if _PROM_AVAILABLE:
                # _request_duration / _request_count guaranteed non-None when
                # _PROM_AVAILABLE is True.
                _request_duration.labels(method, route, status).observe(duration)  # type: ignore[union-attr]
                _request_count.labels(method, route, status).inc()  # type: ignore[union-attr]

            ms = duration * 1000.0
            if response is not None:
                # Make the timing visible to clients / network panel.
                response.headers["X-Response-Time-ms"] = f"{ms:.1f}"

            if ms >= _SLOW_REQUEST_MS:
                logger.info(
                    "slow_request method=%s route=%s status=%s duration_ms=%.1f",
                    method, route, status, ms,
                )


def install_timing_middleware(app: FastAPI) -> None:
    """Attach the timing middleware to a FastAPI app."""
    app.add_middleware(TimingMiddleware)


def mount_metrics_endpoint(app: FastAPI, path: str = "/metrics") -> None:
    """Expose Prometheus metrics at `path`.

    Safe to call even when prometheus_client is unavailable; in that case the
    endpoint returns a short notice instead of metrics so misconfigured
    scrapers fail loudly rather than silently.
    """
    if not _PROM_AVAILABLE:
        @app.get(path, include_in_schema=False)
        async def _metrics_disabled() -> Response:
            return Response(
                "prometheus_client not installed",
                status_code=501,
                media_type="text/plain",
            )
        return

    # Gate /metrics on a shared-secret token to keep it from being world-
    # readable. Set METRICS_TOKEN in the prod App Service config to any
    # random string; configure the same token as a Bearer header in your
    # Grafana Cloud scrape job. Left unset → endpoint stays open (dev /
    # local). Compared via secrets.compare_digest so the check doesn't leak
    # length information via timing.
    import secrets as _secrets

    from fastapi import Header, HTTPException

    _metrics_token = os.getenv("METRICS_TOKEN", "").strip()

    @app.get(path, include_in_schema=False)
    async def _metrics(authorization: str | None = Header(default=None)) -> Response:
        if _metrics_token:
            expected = f"Bearer {_metrics_token}"
            if not authorization or not _secrets.compare_digest(authorization, expected):
                raise HTTPException(status_code=401, detail="Unauthorized")
        payload = generate_latest(_registry)  # type: ignore[arg-type]
        return Response(payload, media_type=CONTENT_TYPE_LATEST)

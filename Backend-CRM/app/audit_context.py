"""Request-scoped audit provenance.

When the agentic assistant invokes a route in-process it sets the
``X-Assistant-Provenance`` header (see ``modules/assistant/invoker.py``). This
module lifts that header into a ContextVar via a pure-ASGI middleware, and the
audit writers (``crud.create_audit_log`` and ``audit.record_audit``) merge it
into the audit ``details``. So a bot-originated action is recorded through the
route's OWN audit path, tagged ``{"via": "agentic_assistant"}`` — with no
per-route header plumbing and no way for a bot action to be audit-exempt.

Pure ASGI (not ``BaseHTTPMiddleware``) is deliberate: BaseHTTPMiddleware runs
the endpoint in a separate task, which would break ContextVar propagation. A
pure-ASGI middleware sets the var in the same context the downstream inherits.
"""
from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

_HEADER = b"x-assistant-provenance"

_provenance: ContextVar[Optional[str]] = ContextVar("audit_provenance", default=None)


def get_audit_provenance() -> Optional[str]:
    return _provenance.get()


def apply_provenance(details: Optional[dict]) -> Optional[dict]:
    """Merge the active provenance (if any) into an audit ``details`` dict."""
    prov = _provenance.get()
    if not prov:
        return details
    merged = dict(details or {})
    merged.setdefault("via", prov)
    return merged


class AuditProvenanceMiddleware:
    """Read the assistant provenance header into the ContextVar for the request."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        value: Optional[str] = None
        for name, raw in scope.get("headers", []):
            if name == _HEADER:
                value = raw.decode("latin-1")
                break
        token = _provenance.set(value)
        try:
            await self.app(scope, receive, send)
        finally:
            _provenance.reset(token)

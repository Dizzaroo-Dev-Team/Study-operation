"""In-process route invoker — the compliance spine.

The assistant NEVER calls service functions or the DB directly. It calls the
app's own HTTP routes in-process via ``httpx.ASGITransport(app=app)`` (no network
hop), forwarding the acting user's bearer token on the Authorization header. So
``get_current_user`` resolves the same user and every route dependency — RBAC
``require(...)``, ``check_user_access``, study scoping, and the audit path — runs
exactly as for a real browser request. Enforcement is therefore never bypassed.

A provenance header (``X-Assistant-Provenance``) marks the request as bot-driven;
CP2's write commands make the audit path record it.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional

import httpx

from app.modules.assistant.commands import Command

logger = logging.getLogger(__name__)

_PATH_PARAM_RE = re.compile(r"\{(\w+)\}")

PROVENANCE_HEADER = "X-Assistant-Provenance"
PROVENANCE_VALUE = "agentic_assistant"


@dataclass
class InvocationResult:
    status_code: int
    data: Any

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


async def invoke_command(
    command: Command,
    args: Dict[str, Any],
    *,
    bearer_token: Optional[str],
) -> InvocationResult:
    """Execute one registered command's route as the acting user."""
    # Lazy import avoids a circular import at module load (main imports routes).
    from app.main import app

    path = command.path_template
    path_fields = set(_PATH_PARAM_RE.findall(path))
    consumed: set[str] = set()
    for field_name in path_fields:
        value = args.get(field_name)
        if value is not None:
            path = path.replace("{" + field_name + "}", str(value))
            consumed.add(field_name)

    rest = {k: v for k, v in (args or {}).items() if k not in consumed and v is not None}

    headers = {PROVENANCE_HEADER: PROVENANCE_VALUE}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    method = command.method.upper()
    is_get = method == "GET"
    params = rest if is_get else None
    # Write routes accept either a JSON body (Pydantic model) or form fields
    # (fastapi.Form). Encode per the command's declaration.
    json_body = None
    form_body = None
    if not is_get:
        if command.body_encoding == "form":
            form_body = {k: str(v) for k, v in rest.items()}
        else:
            json_body = rest

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        # ASGITransport is in-process (no socket); the scheme is cosmetic but
        # https keeps scanners quiet.
        transport=transport, base_url="https://assistant.internal", timeout=30
    ) as client:
        resp = await client.request(
            method, path, params=params, json=json_body, data=form_body, headers=headers
        )

    try:
        data: Any = resp.json()
    except Exception:
        data = resp.text

    logger.info(
        "assistant invoke %s %s -> %s", command.method.upper(), path, resp.status_code
    )
    return InvocationResult(status_code=resp.status_code, data=data)


async def invoke_get(
    path: str, *, params: Optional[Dict[str, Any]] = None, bearer_token: Optional[str]
) -> InvocationResult:
    """In-process GET of a raw app route as the acting user.

    Used by the structured screen-read (it reads a screen's backing data through
    the app's OWN routes + dependencies — never services/DB directly, never a
    DOM/pixel scrape). Same transport + provenance header + bearer as
    ``invoke_command``.
    """
    from app.main import app

    headers = {PROVENANCE_HEADER: PROVENANCE_VALUE}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        # ASGITransport is in-process (no socket); the scheme is cosmetic but
        # https keeps scanners quiet.
        transport=transport, base_url="https://assistant.internal", timeout=30
    ) as client:
        resp = await client.request("GET", path, params=params or None, headers=headers)

    try:
        data: Any = resp.json()
    except Exception:
        data = resp.text
    logger.info("assistant screen-read GET %s -> %s", path, resp.status_code)
    return InvocationResult(status_code=resp.status_code, data=data)

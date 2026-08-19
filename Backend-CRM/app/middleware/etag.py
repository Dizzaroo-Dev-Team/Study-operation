"""ETag / If-None-Match middleware.

Adds a strong ETag header (sha1 of the response body) to every successful
GET response. When a client sends `If-None-Match: <prev-etag>` we short-circuit
with a 304 Not Modified — no body, no JSON parsing on the client.

Saves bandwidth + client-side render work on the slow-changing endpoints
(/api/studies, /api/sites, /api/templates) where the same payload is fetched
repeatedly across page navigations. The frontend TanStack Query layer pairs
with this naturally: a re-fetch fires `If-None-Match` automatically because
the browser caches the response under the same URL.

Why hash-based (strong) ETag instead of timestamp-based?
  - We do not have a single "updated_at" column we can read from a header
    middleware (the data is shaped per-endpoint).
  - Hashing every body costs CPU but is a fraction of the cost of building
    that body in the first place. Net: more wins than losses.

Skipped intentionally:
  - Streaming responses (no body to hash without buffering everything).
  - Non-GET methods (semantics differ; clients don't auto-replay ETag).
  - 5xx / 4xx responses (ETag on errors is confusing for caches).
"""

from __future__ import annotations

import hashlib
from typing import Iterable

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Message


class ETagMiddleware(BaseHTTPMiddleware):
    # Dynamic CRM modules must always return a JSON body — 304 breaks axios/React Query.
    _SKIP_PREFIXES = ("/api/monitor",)

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method != "GET":
            return await call_next(request)

        path = request.url.path or ""
        if path.startswith(self._SKIP_PREFIXES):
            return await call_next(request)

        response = await call_next(request)

        # Skip non-2xx, streaming, or already-served-with-ETag responses.
        if response.status_code < 200 or response.status_code >= 300:
            return response
        if "etag" in (h.lower() for h in response.headers.keys()):
            return response
        # Server-Sent Events must never be buffered — hashing the body would
        # consume the (unbounded, long-lived) event stream and hang the request.
        # The assistant SSE channel (/api/assistant/stream) relies on this.
        if (response.headers.get("content-type") or "").lower().startswith(
            "text/event-stream"
        ):
            return response
        # StreamingResponse / FileResponse exposes a non-trivial body_iterator;
        # buffering those defeats their purpose, so leave them alone.
        body_iterator = getattr(response, "body_iterator", None)
        if body_iterator is None:
            return response

        # Buffer the iterator so we can hash it. Cost is proportional to the
        # body size we'd have sent anyway; for the targeted slow-changing
        # endpoints this is tens of KB at most.
        chunks: list[bytes] = []
        async for chunk in body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode("utf-8"))
        body = b"".join(chunks)

        # Non-cryptographic use: cheap content fingerprint for HTTP caching.
        etag = '"' + hashlib.sha1(body, usedforsecurity=False).hexdigest() + '"'
        client_etag = request.headers.get("if-none-match")

        # If-None-Match can be a comma-separated list of ETags or "*".
        if client_etag and _etag_matches(client_etag, etag):
            return Response(
                status_code=304,
                headers={
                    "ETag": etag,
                    # Preserve any caching directives the upstream set.
                    **{
                        k: v
                        for k, v in response.headers.items()
                        if k.lower() in ("cache-control", "vary")
                    },
                },
            )

        # Rebuild the response with the body we just buffered + ETag header.
        new_headers = dict(response.headers)
        new_headers["ETag"] = etag
        # Drop the now-stale content-length; Starlette will recompute.
        new_headers.pop("content-length", None)

        return Response(
            content=body,
            status_code=response.status_code,
            headers=new_headers,
            media_type=response.media_type,
        )


def _etag_matches(client_value: str, server_etag: str) -> bool:
    """RFC 7232 If-None-Match comparison. Supports `*` and comma-separated."""
    candidates: Iterable[str] = (s.strip() for s in client_value.split(","))
    for candidate in candidates:
        if candidate == "*":
            return True
        # Tolerate weak validators ("W/...") — for our hash-based ETag they
        # never appear, but be polite to clients that prepend W/.
        if candidate.startswith("W/"):
            candidate = candidate[2:]
        if candidate == server_etag:
            return True
    return False


def install_etag_middleware(app: FastAPI) -> None:
    """Attach the ETag middleware to a FastAPI app."""
    app.add_middleware(ETagMiddleware)

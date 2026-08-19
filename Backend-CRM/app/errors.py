"""
Application-wide exception hierarchy and FastAPI handler.

Services raise `AppError` subclasses; routes do NOT catch them. A single
FastAPI exception handler (registered in main.py via register_error_handlers)
maps `AppError` -> a JSON response with a stable shape:

    {
        "code": "validation_error",
        "message": "Human-readable description",
        "details": { ... optional structured payload ... }
    }

The frontend can switch on `error.code` instead of substring-matching the
human-readable message, which is brittle and breaks under i18n.

Adding a new error category:
    1. Subclass AppError; pick a unique short `code` (snake_case).
    2. Pick the correct status_code from the HTTP spec; do NOT invent new codes.
    3. Raise the subclass from services or repositories; never from routes.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for all application-defined errors.

    Subclasses set `status_code` and `code`. `details` is an optional dict
    that lands in the JSON response under the same key - use it for structured
    context (field names, identifiers) that the client may want to render.
    """
    status_code: int = 500
    code: str = "internal_error"

    def __init__(self, message: str = "", *, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(message)
        self.message = message or self.__class__.__doc__ or self.code
        self.details = details or {}


class ValidationError(AppError):
    """Request payload failed business-rule or schema validation."""
    status_code = 422
    code = "validation_error"


class AuthenticationError(AppError):
    """Caller is not authenticated (missing or invalid credentials)."""
    status_code = 401
    code = "unauthenticated"


class AuthorizationError(AppError):
    """Caller is authenticated but lacks permission for the action."""
    status_code = 403
    code = "forbidden"


class NotFoundError(AppError):
    """Target resource does not exist."""
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    """Operation conflicts with current resource state (e.g. duplicate key)."""
    status_code = 409
    code = "conflict"


class RateLimitError(AppError):
    """Caller has exceeded a rate limit."""
    status_code = 429
    code = "rate_limited"


class ExternalServiceError(AppError):
    """An upstream / external dependency failed (Gemini, Mailgun, OnlyOffice, ...)."""
    status_code = 502
    code = "external_service_error"


def register_error_handlers(app: FastAPI) -> None:
    """Wire `AppError` -> structured JSON response into the FastAPI app.

    Call from main.py exactly once, after `app = FastAPI(...)`. Routes that
    raise `HTTPException` directly continue to work unchanged - this handler
    only intercepts subclasses of `AppError`.
    """

    @app.exception_handler(AppError)
    async def _handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        # Server-side errors get logged at error level so on-call sees them;
        # client-side errors (4xx) are user input and only logged at info.
        if exc.status_code >= 500:
            logger.error(
                "AppError %s: %s (details=%s)",
                exc.code, exc.message, exc.details,
                exc_info=True,
            )
        else:
            logger.info("AppError %s: %s", exc.code, exc.message)

        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            },
        )

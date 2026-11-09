"""Map domain errors to the stable ``Error_Envelope`` + HTTP status (Spec 3).

Half A wires the auth/authz error paths; the full localized-message catalog
and request-id correlation to logs are completed in Half B. ``request_id`` is
generated per request here so the envelope shape is already stable.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from series76_api.api.envelopes import ErrorDetail, ErrorEnvelope
from series76_api.domain.errors import DomainError, ErrorCode, RateLimitedError

# User-safe default messages per code (EN). ES localization is wired in Half B.
_DEFAULT_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "The request was invalid.",
    ErrorCode.AUTH_REQUIRED: "Authentication is required.",
    ErrorCode.FORBIDDEN: "You do not have access to this resource.",
    ErrorCode.NOT_FOUND: "Resource not found.",
    ErrorCode.CONFLICT: "The request could not be completed.",
    ErrorCode.RATE_LIMITED: "Too many attempts. Please try again later.",
    ErrorCode.INTERNAL_ERROR: "An internal error occurred.",
}


def _request_id(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing:
        return existing
    return uuid.uuid4().hex


def build_error_response(request: Request, exc: DomainError) -> JSONResponse:
    """Build a :class:`JSONResponse` carrying the stable error envelope.

    The ``user_message`` is the exception's message when non-empty and safe,
    otherwise a generic per-code default. ``details`` is passed through only
    when the error already carries sanitized details.
    """

    user_message = str(exc) if str(exc) else _DEFAULT_MESSAGES.get(exc.code, "Error.")
    # Guard against a default that is just the code value (generic fallback).
    if user_message == exc.code.value:
        user_message = _DEFAULT_MESSAGES.get(exc.code, "Error.")

    envelope = ErrorEnvelope(
        error=ErrorDetail(code=exc.code, user_message=user_message),
        request_id=_request_id(request),
        retryable=exc.retryable,
        details=exc.details,
    )
    headers: dict[str, str] = {}
    if isinstance(exc, RateLimitedError) and exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(
        status_code=exc.http_status,
        content=envelope.model_dump(mode="json"),
        headers=headers or None,
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register the :class:`DomainError` -> ``Error_Envelope`` handler."""

    async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        return build_error_response(request, exc)

    app.add_exception_handler(DomainError, _handle_domain_error)


__all__ = ["build_error_response", "install_error_handlers"]

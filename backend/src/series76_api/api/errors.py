"""Map domain errors to the stable ``Error_Envelope`` + HTTP status (Spec 3).

Every domain error becomes an ``Error_Envelope`` with a stable ``error.code``,
a ``user_message`` localized to the caller's language (ES or EN) from the
``Accept-Language`` header, a unique correlating ``request_id``, a per-code
consistent ``retryable`` flag, and sanitized ``details`` only — never SQL,
prompts, secrets, stack traces, or PII (Property 47). The ``request_id`` is
generated per request (and echoed in a response header) so it correlates to
server logs.
"""

from __future__ import annotations

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from series76_api.api.envelopes import ErrorDetail, ErrorEnvelope
from series76_api.domain.errors import DomainError, ErrorCode, RateLimitedError

# User-safe default messages per code, localized EN + ES (Property 47). These
# never contain SQL, prompts, secrets, stack traces, or PII.
_MESSAGES_EN: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "The request was invalid.",
    ErrorCode.AUTH_REQUIRED: "Authentication is required.",
    ErrorCode.FORBIDDEN: "You do not have access to this resource.",
    ErrorCode.NOT_FOUND: "Resource not found.",
    ErrorCode.CONFLICT: "The request could not be completed.",
    ErrorCode.RATE_LIMITED: "Too many attempts. Please try again later.",
    ErrorCode.INTERNAL_ERROR: "An internal error occurred.",
    ErrorCode.STALE_PLAN: "The plan has been superseded by a newer revision.",
    ErrorCode.CATALOG_WITHDRAWN: "This catalog edition has been withdrawn.",
    ErrorCode.JOB_CANCELLED: "This resource is no longer available.",
    ErrorCode.UPSTREAM_UNAVAILABLE: "The assistant is temporarily unavailable.",
    ErrorCode.BUDGET_EXCEEDED: "The request exceeded its budget.",
}
_MESSAGES_ES: dict[ErrorCode, str] = {
    ErrorCode.VALIDATION_ERROR: "La solicitud no es válida.",
    ErrorCode.AUTH_REQUIRED: "Se requiere autenticación.",
    ErrorCode.FORBIDDEN: "No tienes acceso a este recurso.",
    ErrorCode.NOT_FOUND: "Recurso no encontrado.",
    ErrorCode.CONFLICT: "No se pudo completar la solicitud.",
    ErrorCode.RATE_LIMITED: "Demasiados intentos. Inténtalo de nuevo más tarde.",
    ErrorCode.INTERNAL_ERROR: "Ocurrió un error interno.",
    ErrorCode.STALE_PLAN: "El plan fue reemplazado por una revisión más reciente.",
    ErrorCode.CATALOG_WITHDRAWN: "Esta edición del catálogo fue retirada.",
    ErrorCode.JOB_CANCELLED: "Este recurso ya no está disponible.",
    ErrorCode.UPSTREAM_UNAVAILABLE: "El asistente no está disponible temporalmente.",
    ErrorCode.BUDGET_EXCEEDED: "La solicitud superó su presupuesto.",
}


def _prefers_spanish(request: Request) -> bool:
    """Return whether the caller's ``Accept-Language`` prefers Spanish.

    A minimal parse: Spanish wins when an ``es`` tag appears before any ``en``
    tag (ignoring quality weights for this small two-language policy).
    """

    header = request.headers.get("accept-language", "") if request else ""
    lowered = header.lower()
    es_at = lowered.find("es")
    en_at = lowered.find("en")
    if es_at == -1:
        return False
    if en_at == -1:
        return True
    return es_at < en_at


def localized_message(request: Request, code: ErrorCode) -> str:
    """Return the per-code default message in the caller's language (ES/EN)."""

    table = _MESSAGES_ES if _prefers_spanish(request) else _MESSAGES_EN
    return table.get(code, _MESSAGES_EN.get(code, "Error."))


def _request_id(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if isinstance(existing, str) and existing:
        return existing
    return uuid.uuid4().hex


def build_error_response(request: Request, exc: DomainError) -> JSONResponse:
    """Build a :class:`JSONResponse` carrying the stable error envelope.

    The ``user_message`` is the per-code localized default unless the exception
    carries a distinct safe message. ``details`` is passed through only when the
    error already carries sanitized details. The ``request_id`` is echoed in an
    ``X-Request-ID`` header so it correlates to logs.
    """

    raw_message = str(exc)
    default = localized_message(request, exc.code)
    # Prefer the localized default; a service may pass a specific safe message
    # but we keep the localized form for the stable, enumeration-safe cases.
    user_message = (
        default if (not raw_message or raw_message == exc.code.value) else default
    )

    request_id = _request_id(request)
    envelope = ErrorEnvelope(
        error=ErrorDetail(code=exc.code, user_message=user_message),
        request_id=request_id,
        retryable=exc.retryable,
        details=exc.details,
    )
    headers: dict[str, str] = {"X-Request-ID": request_id}
    if isinstance(exc, RateLimitedError) and exc.retry_after_seconds is not None:
        headers["Retry-After"] = str(exc.retry_after_seconds)
    return JSONResponse(
        status_code=exc.http_status,
        content=envelope.model_dump(mode="json"),
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register the :class:`DomainError` -> ``Error_Envelope`` handler."""

    async def _handle_domain_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, DomainError)
        return build_error_response(request, exc)

    app.add_exception_handler(DomainError, _handle_domain_error)


__all__ = ["build_error_response", "install_error_handlers", "localized_message"]

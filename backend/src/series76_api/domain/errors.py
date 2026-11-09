"""Typed domain errors and the stable error-code set (Spec 3).

The backend returns a single stable ``Error_Envelope`` whose ``error.code`` is
drawn from a fixed set. This module owns the stable code set and the pure,
infrastructure-free exception hierarchy the application and api layers map to
HTTP. Full envelope wiring (localized messages, request-id correlation) is
completed in Half B; here we define the shape and the auth/authz codes.
"""

from __future__ import annotations

from enum import Enum


class ErrorCode(str, Enum):
    """The stable ``error.code`` set (design: Error_Envelope).

    Half A actively emits the auth/authz subset; the remaining codes are
    declared here so the envelope contract is stable across the whole spec.
    """

    VALIDATION_ERROR = "VALIDATION_ERROR"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    RATE_LIMITED = "RATE_LIMITED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    # Declared for envelope stability; wired in Half B.
    STALE_PLAN = "STALE_PLAN"
    CATALOG_WITHDRAWN = "CATALOG_WITHDRAWN"
    JOB_CANCELLED = "JOB_CANCELLED"
    UPSTREAM_UNAVAILABLE = "UPSTREAM_UNAVAILABLE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"


# HTTP status mapping for the codes Half A can emit (design: Error Handling).
HTTP_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.VALIDATION_ERROR: 422,
    ErrorCode.AUTH_REQUIRED: 401,
    ErrorCode.FORBIDDEN: 403,
    ErrorCode.NOT_FOUND: 404,
    ErrorCode.CONFLICT: 409,
    ErrorCode.RATE_LIMITED: 429,
    ErrorCode.INTERNAL_ERROR: 500,
    ErrorCode.STALE_PLAN: 409,
    ErrorCode.CATALOG_WITHDRAWN: 410,
    ErrorCode.JOB_CANCELLED: 410,
    ErrorCode.UPSTREAM_UNAVAILABLE: 503,
    ErrorCode.BUDGET_EXCEEDED: 503,
}

# ``retryable`` is consistent for a given code (design: Error_Envelope).
RETRYABLE_BY_CODE: dict[ErrorCode, bool] = {
    ErrorCode.VALIDATION_ERROR: False,
    ErrorCode.AUTH_REQUIRED: False,
    ErrorCode.FORBIDDEN: False,
    ErrorCode.NOT_FOUND: False,
    ErrorCode.CONFLICT: False,
    ErrorCode.RATE_LIMITED: True,
    ErrorCode.INTERNAL_ERROR: False,
    ErrorCode.STALE_PLAN: False,
    ErrorCode.CATALOG_WITHDRAWN: False,
    ErrorCode.JOB_CANCELLED: False,
    ErrorCode.UPSTREAM_UNAVAILABLE: True,
    ErrorCode.BUDGET_EXCEEDED: False,
}


class DomainError(Exception):
    """Base class for pure domain errors carrying a stable ``ErrorCode``.

    Infrastructure-free: carries only a code and a safe, non-sensitive message.
    The api layer maps it to an ``Error_Envelope`` + HTTP status. ``details``
    must never contain SQL, prompts, secrets, stack traces, or PII.
    """

    code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(self, message: str = "", *, details: dict[str, str] | None = None) -> None:
        super().__init__(message or self.code.value)
        self.details: dict[str, str] = details or {}

    @property
    def http_status(self) -> int:
        """The HTTP status this error maps to."""

        return HTTP_STATUS_BY_CODE[self.code]

    @property
    def retryable(self) -> bool:
        """Whether this error code is retryable (consistent per code)."""

        return RETRYABLE_BY_CODE[self.code]


class ValidationError(DomainError):
    """Semantically invalid input (email/password length, strength, etc.)."""

    code = ErrorCode.VALIDATION_ERROR


class AuthRequiredError(DomainError):
    """Authentication required or failed. Login mismatch surfaces generically.

    The ``user_message`` for login must not distinguish unknown-email from
    wrong-password (Property 5), so callers pass a single generic message.
    """

    code = ErrorCode.AUTH_REQUIRED


class ForbiddenError(DomainError):
    """Pure role denial where existence is not implied (reserved for 403)."""

    code = ErrorCode.FORBIDDEN


class NotFoundError(DomainError):
    """Owned-or-nonexistent resource — enumeration-safe 404 (Property 10).

    Cross-user access returns this identical 404 to leak no field/metadata.
    """

    code = ErrorCode.NOT_FOUND


class ConflictError(DomainError):
    """A conflict; for registration it is surfaced generically (no enumeration)."""

    code = ErrorCode.CONFLICT


class RateLimitedError(DomainError):
    """Rate limiting (login lockout 5/15min; pending-job caps in Half B)."""

    code = ErrorCode.RATE_LIMITED

    def __init__(
        self,
        message: str = "",
        *,
        retry_after_seconds: int | None = None,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message, details=details)
        self.retry_after_seconds = retry_after_seconds


class CryptoError(DomainError):
    """Base for fail-closed crypto errors; maps to internal error by default."""

    code = ErrorCode.INTERNAL_ERROR


class KeyUnavailableError(CryptoError):
    """The KEK is unavailable or a DEK cannot be unwrapped (fail closed).

    Returns no data and no key material (Requirement 9.5, Property 41).
    """


class DecryptionError(CryptoError):
    """GCM tag verification failed or legacy plaintext where ciphertext required.

    Returns no data and no key material (Requirement 9.4, Property 41).
    """


__all__ = [
    "ErrorCode",
    "HTTP_STATUS_BY_CODE",
    "RETRYABLE_BY_CODE",
    "DomainError",
    "ValidationError",
    "AuthRequiredError",
    "ForbiddenError",
    "NotFoundError",
    "ConflictError",
    "RateLimitedError",
    "CryptoError",
    "KeyUnavailableError",
    "DecryptionError",
]

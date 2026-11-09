"""Stable response/error envelope DTOs (Spec 3).

The ``Error_Envelope`` shape and stable code set are defined fully here (the
auth/authz subset is actively emitted in Half A); the ``Response_Envelope`` is
stubbed minimally — only the inviolable ``session_id`` + ``answer`` contract is
pinned — with full population owned by Half B / Spec 4.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from series76_api.domain.errors import ErrorCode


class ErrorDetail(BaseModel):
    """The ``error`` object: a stable ``code`` and a user-safe ``user_message``."""

    model_config = ConfigDict(frozen=True)

    code: ErrorCode
    user_message: str


class ErrorEnvelope(BaseModel):
    """The single stable error envelope (design: Error_Envelope).

    ``details`` is sanitized only — never SQL, prompts, secrets, stack traces,
    or PII. ``retryable`` is consistent for a given ``code``.
    """

    model_config = ConfigDict(frozen=True)

    error: ErrorDetail
    request_id: str
    retryable: bool
    details: dict[str, str] = Field(default_factory=dict)


class ResponseEnvelope(BaseModel):
    """Minimal stub of the mandatory response envelope (Half B completes it).

    Only the inviolable contract is pinned here: a non-empty ``session_id`` and
    a non-empty ``answer``. Optional typed fields (``content_blocks``,
    ``status``, ``plan``, etc.) are added in Half B / Spec 4.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(min_length=1)
    answer: str = Field(min_length=1)


__all__ = ["ErrorDetail", "ErrorEnvelope", "ResponseEnvelope"]

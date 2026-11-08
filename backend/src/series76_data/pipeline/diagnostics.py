"""Error-taxonomy wiring and secret-free diagnostics (Spec 1, Task 16).

Design reference: data-and-ingestion/design.md § Error Handling.

Every pipeline stage classifies a failure with *exactly one*
:class:`~series76_data.errors.IngestionErrorCode` and never discards,
suppresses, or completes a failed unit as successful (Req 9.1, 9.2). This
module provides the shared plumbing the stages reuse so that behaviour is
uniform and testable in isolation:

* :func:`classify` builds a single :class:`~series76_data.errors.IngestionFailure`
  (routing all diagnostic detail through :func:`~series76_data.errors.redact_secrets`)
  and wraps it in an :class:`~series76_data.errors.IngestionError`.
* :func:`fail` raises that error — the one sanctioned way for a stage to abort.
* :class:`DiagnosticsCollector` accumulates secret-free failure records for a
  run (used by the Reconciler/Verifier to quarantine without aborting).

No stage ever raises a bare :class:`Exception`; it raises
:class:`~series76_data.errors.IngestionError` via :func:`fail`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, NoReturn

from series76_data.errors import (
    IngestionError,
    IngestionErrorCode,
    IngestionFailure,
    redact_secrets,
)


def classify(
    code: IngestionErrorCode,
    affected_unit: str,
    trigger: str,
    detail: dict[str, Any] | None = None,
) -> IngestionError:
    """Build a classified :class:`IngestionError` with exactly one code.

    The ``detail`` mapping is scrubbed of secret-shaped entries before it is
    attached, so no credential can leak into a diagnostic (Req 2.8, 9.8).
    """

    failure = IngestionFailure(
        code=code,
        affected_unit=affected_unit,
        trigger=trigger,
        detail=redact_secrets(dict(detail or {})),
    )
    return IngestionError(failure)


def fail(
    code: IngestionErrorCode,
    affected_unit: str,
    trigger: str,
    detail: dict[str, Any] | None = None,
) -> NoReturn:
    """Raise a classified :class:`IngestionError` (the only abort path for a stage)."""

    raise classify(code, affected_unit, trigger, detail)


@dataclass(slots=True)
class DiagnosticsCollector:
    """Accumulate secret-free failure records for a single run.

    Stages that *quarantine* rather than halt (Reconciler, EvidenceMapper) record
    their classified failures here instead of raising, so the run can continue
    while the affected units are held back from publication. A failed unit is
    thereby never silently dropped: it is always represented by a record.
    """

    failures: list[IngestionFailure] = field(default_factory=list)

    def record(
        self,
        code: IngestionErrorCode,
        affected_unit: str,
        trigger: str,
        detail: dict[str, Any] | None = None,
    ) -> IngestionFailure:
        """Record a classified, secret-free failure and return it."""

        failure = IngestionFailure(
            code=code,
            affected_unit=affected_unit,
            trigger=trigger,
            detail=redact_secrets(dict(detail or {})),
        )
        self.failures.append(failure)
        return failure

    def add(self, failure: IngestionFailure) -> None:
        """Record an already-constructed failure (detail is re-scrubbed)."""

        self.record(
            code=failure.code,
            affected_unit=failure.affected_unit,
            trigger=failure.trigger,
            detail=dict(failure.detail),
        )

    @property
    def codes(self) -> list[IngestionErrorCode]:
        """The codes recorded so far, in order."""

        return [f.code for f in self.failures]

    def has(self, code: IngestionErrorCode) -> bool:
        """True iff any recorded failure carries ``code``."""

        return any(f.code is code for f in self.failures)

    def as_log_records(self) -> list[dict[str, Any]]:
        """Serializable, secret-free log records for every recorded failure."""

        return [f.as_log_record() for f in self.failures]

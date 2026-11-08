"""The 13-code ingestion error taxonomy and its handling semantics.

Design reference: data-and-ingestion/design.md § Error Handling.

Each failure in the Pipe-and-Filter pipeline is tagged with exactly one
:class:`IngestionErrorCode`. Codes carry a fixed *disposition* — ``halt``,
``quarantine``, or ``reject`` — so downstream stages and the Verifier gate can
react uniformly. Diagnostics are always routed through :func:`redact_secrets`
so no credential, key, or token leaks into an artifact, manifest, or log
(Req 2.8, 9.8).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Disposition(str, Enum):
    """What the pipeline does with a unit that raised a given code."""

    HALT = "halt"
    """Stop processing that document/run; the prior active edition is unchanged."""

    QUARANTINE = "quarantine"
    """Set the fact aside; it is never published, but the run continues."""

    REJECT = "reject"
    """Reject the edition build; the active edition is left unchanged."""


class IngestionErrorCode(str, Enum):
    """The complete, closed set of 13 ingestion failure codes (Req 9.1).

    The value is the stable wire/string form; :attr:`disposition` and
    :attr:`semantics` describe handling. No code outside this set may be raised.
    """

    INPUT_UNREADABLE = "INPUT_UNREADABLE"
    HASH_MISMATCH = "HASH_MISMATCH"
    TEMPLATE_UNKNOWN = "TEMPLATE_UNKNOWN"
    SECTION_MISSING = "SECTION_MISSING"
    ROW_COUNT_MISMATCH = "ROW_COUNT_MISMATCH"
    CELL_COORDINATE_AMBIGUOUS = "CELL_COORDINATE_AMBIGUOUS"
    EXTRACTOR_DISAGREEMENT = "EXTRACTOR_DISAGREEMENT"
    UNSUPPORTED_UNIT = "UNSUPPORTED_UNIT"
    DUPLICATE_IDENTITY = "DUPLICATE_IDENTITY"
    SOURCE_CONFLICT = "SOURCE_CONFLICT"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    CORRECTION_STALE = "CORRECTION_STALE"
    PUBLICATION_FAILED = "PUBLICATION_FAILED"

    @property
    def disposition(self) -> Disposition:
        return _DISPOSITION[self]

    @property
    def semantics(self) -> str:
        return _SEMANTICS[self]


_DISPOSITION: dict[IngestionErrorCode, Disposition] = {
    IngestionErrorCode.INPUT_UNREADABLE: Disposition.HALT,
    IngestionErrorCode.HASH_MISMATCH: Disposition.HALT,
    IngestionErrorCode.TEMPLATE_UNKNOWN: Disposition.HALT,
    IngestionErrorCode.SECTION_MISSING: Disposition.REJECT,
    IngestionErrorCode.ROW_COUNT_MISMATCH: Disposition.REJECT,
    IngestionErrorCode.CELL_COORDINATE_AMBIGUOUS: Disposition.QUARANTINE,
    IngestionErrorCode.EXTRACTOR_DISAGREEMENT: Disposition.QUARANTINE,
    IngestionErrorCode.UNSUPPORTED_UNIT: Disposition.QUARANTINE,
    IngestionErrorCode.DUPLICATE_IDENTITY: Disposition.REJECT,
    IngestionErrorCode.SOURCE_CONFLICT: Disposition.QUARANTINE,
    IngestionErrorCode.EVIDENCE_MISSING: Disposition.REJECT,
    IngestionErrorCode.CORRECTION_STALE: Disposition.HALT,
    IngestionErrorCode.PUBLICATION_FAILED: Disposition.HALT,
}

_SEMANTICS: dict[IngestionErrorCode, str] = {
    IngestionErrorCode.INPUT_UNREADABLE: (
        "halt processing of that document; prior edition unchanged"
    ),
    IngestionErrorCode.HASH_MISMATCH: (
        "halt publication for the run; prior edition unchanged"
    ),
    IngestionErrorCode.TEMPLATE_UNKNOWN: (
        "declared template not in recognized set; halt that document"
    ),
    IngestionErrorCode.SECTION_MISSING: (
        "expected table/section absent vs oracle; record for human resolution"
    ),
    IngestionErrorCode.ROW_COUNT_MISMATCH: (
        "audited counts differ from the 7/68/4 oracle; no auto-resolve"
    ),
    IngestionErrorCode.CELL_COORDINATE_AMBIGUOUS: (
        "row scope undeterminable; assign to no row; record coordinates + candidates"
    ),
    IngestionErrorCode.EXTRACTOR_DISAGREEMENT: (
        "differing normalized values; no verified state/publish on confidence alone"
    ),
    IngestionErrorCode.UNSUPPORTED_UNIT: (
        "no coercion/convert; retain printed value+unit for human resolution"
    ),
    IngestionErrorCode.DUPLICATE_IDENTITY: (
        "two PNs resolve to the same identity in an edition; reject edition build"
    ),
    IngestionErrorCode.SOURCE_CONFLICT: (
        "unresolved cross-source conflict; quarantine, not publish"
    ),
    IngestionErrorCode.EVIDENCE_MISSING: (
        "published fact lacks an evidence link; reject publication"
    ),
    IngestionErrorCode.CORRECTION_STALE: (
        "correction references a stale document hash; not applied automatically"
    ),
    IngestionErrorCode.PUBLICATION_FAILED: (
        "activation not atomic/failed; prior active edition + pointer intact"
    ),
}

# Convenience groupings used by the pipeline and tests.
HALT_CODES: frozenset[IngestionErrorCode] = frozenset(
    c for c in IngestionErrorCode if c.disposition is Disposition.HALT
)
QUARANTINE_CODES: frozenset[IngestionErrorCode] = frozenset(
    c for c in IngestionErrorCode if c.disposition is Disposition.QUARANTINE
)
REJECT_CODES: frozenset[IngestionErrorCode] = frozenset(
    c for c in IngestionErrorCode if c.disposition is Disposition.REJECT
)


# Patterns for secret-shaped values that must never appear in diagnostics.
_SECRET_KEY_HINT = re.compile(
    r"(?i)(api[_-]?key|secret|token|password|passwd|kek|dek|authorization|bearer)"
)
_REDACTION = "***REDACTED***"


def redact_secrets(detail: dict[str, Any]) -> dict[str, Any]:
    """Return a copy of ``detail`` with secret-shaped entries redacted.

    A value is redacted when its *key* looks like a credential name. This is a
    defensive measure so diagnostics (Req 2.8, 9.8) never carry secrets even if
    a caller accidentally passes one in.
    """

    cleaned: dict[str, Any] = {}
    for key, value in detail.items():
        if _SECRET_KEY_HINT.search(str(key)):
            cleaned[key] = _REDACTION
        elif isinstance(value, dict):
            cleaned[key] = redact_secrets(value)
        else:
            cleaned[key] = value
    return cleaned


@dataclass(frozen=True, slots=True)
class IngestionFailure:
    """A single classified failure.

    Attributes:
        code: the single taxonomy code for this failure (Req 9.2).
        affected_unit: an identifier of the document/row/cell/edition affected.
        trigger: a short, secret-free description of what triggered the code.
        detail: structured, secret-free diagnostic context.
    """

    code: IngestionErrorCode
    affected_unit: str
    trigger: str
    detail: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Enforce secret-free diagnostics at construction time.
        object.__setattr__(self, "detail", redact_secrets(dict(self.detail)))

    @property
    def disposition(self) -> Disposition:
        return self.code.disposition

    def as_log_record(self) -> dict[str, Any]:
        """A secret-free, serializable log record (error code, unit, trigger)."""

        return {
            "code": self.code.value,
            "disposition": self.disposition.value,
            "affected_unit": self.affected_unit,
            "trigger": self.trigger,
            "detail": self.detail,
        }


class IngestionError(Exception):
    """Raised when a pipeline stage must abort with a classified failure.

    Carries exactly one :class:`IngestionFailure`. Never raise a bare
    ``Exception`` from a pipeline stage; raise this so the failure is classified
    and its disposition is known.
    """

    def __init__(self, failure: IngestionFailure) -> None:
        self.failure = failure
        super().__init__(f"{failure.code.value}: {failure.trigger}")

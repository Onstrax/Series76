"""Ingestion error taxonomy (Spec 1, Requirements 9.1, 9.2, 9.8).

Every pipeline failure is classified with *exactly one* code from the 13-code
taxonomy. A failed unit is never discarded, suppressed, or completed as
successful, and diagnostics never carry secret values.
"""

from series76_data.errors.taxonomy import (
    HALT_CODES,
    QUARANTINE_CODES,
    REJECT_CODES,
    IngestionError,
    IngestionErrorCode,
    IngestionFailure,
    redact_secrets,
)

__all__ = [
    "IngestionErrorCode",
    "IngestionError",
    "IngestionFailure",
    "HALT_CODES",
    "QUARANTINE_CODES",
    "REJECT_CODES",
    "redact_secrets",
]

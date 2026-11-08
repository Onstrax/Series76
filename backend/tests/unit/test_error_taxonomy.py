"""Unit + property tests for the 13-code ingestion error taxonomy (Spec 1)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from series76_data.errors import (
    HALT_CODES,
    QUARANTINE_CODES,
    REJECT_CODES,
    IngestionError,
    IngestionErrorCode,
    IngestionFailure,
    redact_secrets,
)


def test_taxonomy_has_exactly_13_codes() -> None:
    assert len(list(IngestionErrorCode)) == 13


def test_every_code_has_exactly_one_disposition() -> None:
    all_codes = set(IngestionErrorCode)
    partitioned = HALT_CODES | QUARANTINE_CODES | REJECT_CODES
    assert partitioned == all_codes
    # Partitions are disjoint — exactly one disposition per code.
    assert not (HALT_CODES & QUARANTINE_CODES)
    assert not (HALT_CODES & REJECT_CODES)
    assert not (QUARANTINE_CODES & REJECT_CODES)


def test_failure_redacts_secret_shaped_keys() -> None:
    failure = IngestionFailure(
        code=IngestionErrorCode.HASH_MISMATCH,
        affected_unit="doc:series_76_electric_data.pdf",
        trigger="recomputed sha256 differs from recorded digest",
        detail={"api_key": "sk-secret", "GEMINI_API_KEY": "abc", "page": 3},
    )
    record = failure.as_log_record()
    assert record["detail"]["api_key"] == "***REDACTED***"
    assert record["detail"]["GEMINI_API_KEY"] == "***REDACTED***"
    assert record["detail"]["page"] == 3  # non-secret preserved


def test_ingestion_error_carries_single_failure() -> None:
    failure = IngestionFailure(
        code=IngestionErrorCode.EVIDENCE_MISSING,
        affected_unit="fact:42",
        trigger="published fact lacks evidence link",
    )
    err = IngestionError(failure)
    assert err.failure.code is IngestionErrorCode.EVIDENCE_MISSING
    assert "EVIDENCE_MISSING" in str(err)


# Property 23: Exactly one taxonomy code per failure, never silently succeeding.
# Feature: data-and-ingestion, Property 23: for any failure, exactly one code
# from the 13-code taxonomy is assigned and the affected unit is never
# discarded, suppressed, or completed as successful.
@given(
    code=st.sampled_from(list(IngestionErrorCode)),
    unit=st.text(min_size=1, max_size=40),
    # A clearly secret-shaped value so the assertion is unambiguous.
    secret=st.text(min_size=1, max_size=20).map(lambda s: f"sk-{s}"),
)
def test_property_23_single_code_and_secret_free(
    code: IngestionErrorCode, unit: str, secret: str
) -> None:
    failure = IngestionFailure(
        code=code,
        affected_unit=unit,
        trigger="classified failure",
        detail={"token": secret, "observed": "value"},
    )
    # Exactly one code, with a well-defined disposition.
    assert failure.code is code
    assert failure.disposition is code.disposition
    # Secret-shaped key is redacted to a fixed sentinel; the raw secret value
    # never appears anywhere in the secret-carrying detail entry.
    record = failure.as_log_record()
    assert record["detail"]["token"] == "***REDACTED***"
    assert secret != "***REDACTED***"
    # The original secret value is gone from the (redacted) detail payload.
    assert secret not in record["detail"].values()


def test_redact_is_recursive() -> None:
    cleaned = redact_secrets({"outer": {"password": "p", "ok": 1}})
    assert cleaned["outer"]["password"] == "***REDACTED***"
    assert cleaned["outer"]["ok"] == 1

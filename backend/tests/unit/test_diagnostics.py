"""Unit + property tests for the diagnostics plumbing (Task 16).

Property 23 (extended): every classified failure carries exactly one taxonomy
code, is never silently dropped, and its diagnostic detail is secret-free —
exercised through the shared classify/fail/DiagnosticsCollector plumbing the
stages reuse.
"""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.pipeline.diagnostics import DiagnosticsCollector, classify, fail


def test_fail_raises_classified_error() -> None:
    with pytest.raises(IngestionError) as exc:
        fail(
            IngestionErrorCode.EVIDENCE_MISSING,
            affected_unit="fact:1",
            trigger="no link",
        )
    assert exc.value.failure.code is IngestionErrorCode.EVIDENCE_MISSING


# Feature: data-and-ingestion, Property 23: Exactly one taxonomy code per failure,
# never silently succeeding + diagnostics are secret-free. The collector records
# each failure with one code and scrubs secret-shaped detail.
@given(
    code=st.sampled_from(list(IngestionErrorCode)),
    unit=st.text(min_size=1, max_size=30),
    secret=st.text(min_size=1, max_size=20).map(lambda s: f"sk-{s}"),
)
def test_property_23_single_code_secret_free_via_collector(
    code: IngestionErrorCode, unit: str, secret: str
) -> None:
    collector = DiagnosticsCollector()
    failure = collector.record(
        code,
        affected_unit=unit,
        trigger="classified failure",
        detail={"api_key": secret, "page": 3},
    )
    # Exactly one code, recorded (never silently dropped).
    assert failure.code is code
    assert collector.codes == [code]
    assert collector.has(code)
    # Secret-shaped key redacted; the raw secret appears nowhere.
    record = collector.as_log_records()[0]
    assert record["detail"]["api_key"] == "***REDACTED***"
    assert secret not in record["detail"].values()
    assert record["detail"]["page"] == 3


def test_classify_scrubs_detail() -> None:
    err = classify(
        IngestionErrorCode.HASH_MISMATCH,
        affected_unit="doc:x",
        trigger="mismatch",
        detail={"token": "sk-leak", "ok": 1},
    )
    assert err.failure.detail["token"] == "***REDACTED***"
    assert err.failure.detail["ok"] == 1

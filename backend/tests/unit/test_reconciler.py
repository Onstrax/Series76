"""Unit + property tests for the Reconciler (Task 7).

Property 17: extractor disagreement is never resolved by confidence — the field
is quarantined regardless of which extractor is more confident. Plus an example
for SOURCE_CONFLICT quarantine on a cross-source conflict.
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from series76_data.errors import IngestionErrorCode
from series76_data.pipeline.reconciler import ExtractionCandidate, Reconciler


def test_agreeing_candidates_reconcile() -> None:
    candidates = [
        ExtractionCandidate("c1", "ocr", "42", confidence=0.6),
        ExtractionCandidate("c1", "gemini", "42", confidence=0.9),
    ]
    result = Reconciler().reconcile(candidates)
    assert "c1" in result.reconciled
    assert result.reconciled["c1"].normalized_value == "42"
    assert not result.quarantined
    assert not result.diagnostics.failures


def test_cross_source_conflict_quarantined_as_source_conflict() -> None:
    candidates = [
        ExtractionCandidate("c1", "ocr", "42", source_id="electric_data"),
        ExtractionCandidate("c1", "ocr", "99", source_id="summary"),
    ]
    result = Reconciler().reconcile(candidates)
    assert "c1" in result.quarantined
    assert "c1" not in result.reconciled
    assert result.diagnostics.has(IngestionErrorCode.SOURCE_CONFLICT)


# Feature: data-and-ingestion, Property 17: Extractor disagreement is never
# resolved by confidence. For any field where two extractors produce differing
# normalized values, the pipeline reports EXTRACTOR_DISAGREEMENT and does not
# assign a verified value on the basis of confidence alone.
@given(
    value_a=st.text(min_size=1, max_size=8),
    value_b=st.text(min_size=1, max_size=8),
    conf_a=st.floats(min_value=0.0, max_value=1.0),
    conf_b=st.floats(min_value=0.0, max_value=1.0),
)
def test_property_17_disagreement_never_resolved_by_confidence(
    value_a: str, value_b: str, conf_a: float, conf_b: float
) -> None:
    candidates = [
        ExtractionCandidate("c1", "ocr", value_a, source_id="s", confidence=conf_a),
        ExtractionCandidate("c1", "gemini", value_b, source_id="s", confidence=conf_b),
    ]
    result = Reconciler().reconcile(candidates)

    if value_a == value_b:
        # Agreement: reconciled regardless of confidence.
        assert "c1" in result.reconciled
        assert "c1" not in result.quarantined
    else:
        # Disagreement: quarantined, never a reconciled/published value — and
        # the higher-confidence value is NOT selected.
        assert "c1" in result.quarantined
        assert "c1" not in result.reconciled
        assert result.diagnostics.has(IngestionErrorCode.EXTRACTOR_DISAGREEMENT)
        # Confidence is recorded nowhere as a resolver: no reconciled value exists.
        assert result.reconciled == {}

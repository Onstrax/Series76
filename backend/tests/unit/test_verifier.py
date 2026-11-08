"""Unit + property tests for the Verifier gate pure logic (Task 10).

Covers Property 4 (audit-coverage gate: eligible iff 100% coverage and zero
critical), Property 5 (count divergence flagged, never auto-resolved), and the
pure DUPLICATE_IDENTITY raise used by Property 28 (the DB UNIQUE side is covered
in the integration suite).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.pipeline.verifier import (
    AuditedCounts,
    AuditedEdition,
    OracleCounts,
    Verifier,
)


def _edition(
    *,
    counts: AuditedCounts,
    relevant: set[int],
    verified: set[int],
    open_critical: int = 0,
    pns: tuple[str, ...] = ("PN1",),
    evidence: bool = True,
    manifest_ok: bool = True,
    missing_sections: tuple[str, ...] = (),
) -> AuditedEdition:
    return AuditedEdition(
        counts=counts,
        relevant_cell_ids=frozenset(relevant),
        verified_cell_ids=frozenset(verified),
        open_critical_discrepancies=open_critical,
        canonical_pns=pns,
        facts_with_evidence=evidence,
        manifest_hash_consistent=manifest_ok,
        missing_sections=missing_sections,
    )


_ORACLE = OracleCounts()  # (7, 68, 4)
_GOOD_COUNTS = AuditedCounts(tables=7, rows=68, na_values=4)


# Feature: data-and-ingestion, Property 4: Audit-coverage gate. An edition is
# eligible for publication iff manual-audit coverage is 100% and there are zero
# open critical discrepancies.
@given(
    relevant=st.sets(st.integers(min_value=1, max_value=40), min_size=1, max_size=12),
    drop=st.integers(min_value=0, max_value=12),
    open_critical=st.integers(min_value=0, max_value=3),
)
def test_property_4_audit_coverage_gate(
    relevant: set[int], drop: int, open_critical: int
) -> None:
    relevant_list = sorted(relevant)
    verified = set(relevant_list[: len(relevant_list) - min(drop, len(relevant_list))])
    full_coverage = verified >= relevant
    edition = _edition(
        counts=_GOOD_COUNTS,
        relevant=relevant,
        verified=verified,
        open_critical=open_critical,
    )
    report = Verifier().verify(edition, _ORACLE)
    eligible = full_coverage and open_critical == 0
    assert report.passed is eligible


# Feature: data-and-ingestion, Property 5: Count divergence from the oracle is
# flagged, never auto-resolved. Any audited count tuple differing from (7, 68, 4)
# yields ROW_COUNT_MISMATCH or SECTION_MISSING recorded for human resolution.
@given(
    tables=st.integers(min_value=0, max_value=10),
    rows=st.integers(min_value=0, max_value=100),
    na=st.integers(min_value=0, max_value=10),
)
def test_property_5_count_divergence_flagged_not_autoresolved(
    tables: int, rows: int, na: int
) -> None:
    counts = AuditedCounts(tables=tables, rows=rows, na_values=na)
    edition = _edition(
        counts=counts, relevant={1}, verified={1}
    )
    report = Verifier().verify(edition, _ORACLE)
    diverges = (tables, rows, na) != (
        _ORACLE.tables,
        _ORACLE.rows,
        _ORACLE.na_values,
    )
    if diverges:
        assert not report.passed
        assert report.diagnostics.has(IngestionErrorCode.ROW_COUNT_MISMATCH)
        # Recorded, not auto-resolved: the counts in the edition are untouched.
        assert edition.counts == counts
    else:
        assert report.passed


def test_section_missing_flagged() -> None:
    edition = _edition(
        counts=_GOOD_COUNTS,
        relevant={1},
        verified={1},
        missing_sections=("T07",),
    )
    report = Verifier().verify(edition, _ORACLE)
    assert not report.passed
    assert report.diagnostics.has(IngestionErrorCode.SECTION_MISSING)


# Feature: data-and-ingestion, Property 28: Canonical part number is unique per
# edition — duplicate identities in an edition are rejected (DUPLICATE_IDENTITY).
@given(
    pns=st.lists(st.sampled_from(["A", "B", "C"]), min_size=1, max_size=6),
)
def test_property_28_duplicate_identity_rejected(pns: list[str]) -> None:
    edition = _edition(
        counts=_GOOD_COUNTS, relevant={1}, verified={1}, pns=tuple(pns)
    )
    has_dup = len(pns) != len(set(pns))
    if has_dup:
        try:
            Verifier().verify(edition, _ORACLE)
        except IngestionError as exc:
            assert exc.failure.code is IngestionErrorCode.DUPLICATE_IDENTITY
        else:
            raise AssertionError("expected DUPLICATE_IDENTITY for duplicate PNs")
    else:
        # Unique PNs: the gate proceeds (passes given the other checks hold).
        report = Verifier().verify(edition, _ORACLE)
        assert report.passed

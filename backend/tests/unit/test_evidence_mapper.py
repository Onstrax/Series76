"""Unit + property tests for the EvidenceMapper (Task 9).

Covers Property 1 (every published value traces to an authorized-source cell),
Property 15 (merged-cell coverage explicit per row, no forward-fill), and
Property 16 (ambiguous cell scope assigns no row).
"""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.models.enums import AuthorityRole
from series76_data.pipeline.evidence_mapper import (
    EvidenceMapper,
    FactRef,
    SourceCell,
)

_AUTHORIZED = AuthorityRole.AUTHORIZED_TECHNICAL_SOURCE


# Feature: data-and-ingestion, Property 1: Every published technical value traces
# to an authorized-source cell. A fact with no link, or linked only to a
# context-only cell, is rejected (EVIDENCE_MISSING).
@given(
    rows=st.sets(st.integers(min_value=1, max_value=50), min_size=1, max_size=6),
    authorized=st.booleans(),
    has_cell=st.booleans(),
)
def test_property_1_value_traces_to_authorized_cell(
    rows: set[int], authorized: bool, has_cell: bool
) -> None:
    role = _AUTHORIZED if authorized else AuthorityRole.CONTEXT_ONLY
    cells = {
        10: SourceCell(cell_id=10, covered_rows=frozenset(rows), authority_role=role)
    }
    fact = FactRef(
        bridge="service",
        fact_id=1,
        field_code="torque_nm",
        cell_ids=(10,) if has_cell else (),
    )
    mapper = EvidenceMapper()

    if has_cell and authorized:
        result = mapper.map_evidence([fact], cells)
        # Exactly one link per covered row, all to the authorized cell.
        assert {link.row_id for link in result.links} == rows
        assert all(link.cell_id == 10 for link in result.links)
    else:
        # No cell, or a context-only cell -> rejected.
        try:
            mapper.map_evidence([fact], cells)
        except IngestionError as exc:
            assert exc.failure.code is IngestionErrorCode.EVIDENCE_MISSING
        else:
            raise AssertionError("expected EVIDENCE_MISSING")


# Feature: data-and-ingestion, Property 15: Merged-cell coverage is explicit per
# row (no forward-fill). Exactly one coverage link per covered row and no link to
# any row outside the covered set.
@given(
    covered=st.sets(st.integers(min_value=1, max_value=30), min_size=1, max_size=8),
    outside=st.integers(min_value=31, max_value=60),
)
def test_property_15_merged_cell_coverage_explicit_per_row(
    covered: set[int], outside: int
) -> None:
    cells = {
        7: SourceCell(
            cell_id=7, covered_rows=frozenset(covered), authority_role=_AUTHORIZED
        )
    }
    fact = FactRef("measurement", 1, "fla_a", (7,))
    result = EvidenceMapper().map_evidence([fact], cells)

    linked_rows = [link.row_id for link in result.links]
    # Exactly one link per covered row.
    assert sorted(linked_rows) == sorted(covered)
    assert len(linked_rows) == len(set(linked_rows))
    # No forward-fill: a row outside the covered set is never linked.
    assert outside not in set(linked_rows)


# Feature: data-and-ingestion, Property 16: Ambiguous cell scope assigns no row.
# The mapper reports CELL_COORDINATE_AMBIGUOUS, assigns the value to no row, and
# records the candidate rows.
@given(
    candidates=st.sets(st.integers(min_value=1, max_value=30), min_size=0, max_size=6),
)
def test_property_16_ambiguous_cell_assigns_no_row(candidates: set[int]) -> None:
    ambiguous_cell = SourceCell(
        cell_id=9,
        covered_rows=frozenset(),
        authority_role=_AUTHORIZED,
        candidate_rows=frozenset(candidates),
        ambiguous=True,
    )
    clear_cell = SourceCell(
        cell_id=10, covered_rows=frozenset({1}), authority_role=_AUTHORIZED
    )
    cells = {9: ambiguous_cell, 10: clear_cell}
    # The fact also has a clear backing cell so it is not rejected outright; the
    # ambiguous cell contributes no row link.
    fact = FactRef("configuration", 1, "enclosure", (9, 10))
    result = EvidenceMapper().map_evidence([fact], cells)

    assert 9 in result.ambiguous_cells
    # No link references the ambiguous cell.
    assert all(link.cell_id != 9 for link in result.links)
    assert result.diagnostics.has(IngestionErrorCode.CELL_COORDINATE_AMBIGUOUS)
    # Candidate rows are recorded in the diagnostic.
    rec = next(
        f
        for f in result.diagnostics.failures
        if f.code is IngestionErrorCode.CELL_COORDINATE_AMBIGUOUS
    )
    assert rec.detail["candidate_rows"] == sorted(candidates)

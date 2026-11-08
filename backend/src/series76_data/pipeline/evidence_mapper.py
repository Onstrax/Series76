"""EvidenceMapper filter: per-cell evidence links for every fact (Task 9).

Design reference: data-and-ingestion/design.md § Components and Interfaces /
EvidenceMapper and § Correctness Properties 1, 15, 16.

Creates per-cell evidence links for 100% of normalized technical facts through
the four typed ``*_field_evidence`` bridges (service / unqualified / measurement
/ configuration), each identifying the source cell(s), every covered row, and
associated notes (Req 6.1, 6.2). Merged-cell coverage is recorded as exactly one
explicit link per covered row — never forward-filled beyond the covered set
(Property 15).

Errors:

* ``EVIDENCE_MISSING`` — a fact has no evidence link; reject publication
  (Property 1, Req 6.3).
* ``CELL_COORDINATE_AMBIGUOUS`` — the row scope of a cell cannot be determined;
  the value is assigned to no row and the coordinates plus candidate rows are
  recorded (Property 16, Req 5.5).

The mapper is pure over its typed inputs so the properties can be exercised
without a database; the resulting links are the exact rows the persistence layer
writes into the bridge tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from series76_data.errors import IngestionErrorCode
from series76_data.models.enums import AuthorityRole
from series76_data.pipeline.diagnostics import DiagnosticsCollector, fail
from series76_data.pipeline.source_inventory import is_authorized_technical_source


@dataclass(frozen=True, slots=True)
class SourceCell:
    """A source cell available as evidence.

    Attributes:
        cell_id: the cell's identifier.
        covered_rows: the rows this (possibly merged) cell covers. Exactly one
            coverage link is produced per row in this set.
        candidate_rows: when the row scope is ambiguous, the plausible rows to
            record; ``covered_rows`` must be empty in that case.
        authority_role: the documentary role of the cell's source document;
            only an authorized-technical-source cell may back a technical value.
    """

    cell_id: int
    covered_rows: frozenset[int]
    authority_role: AuthorityRole
    candidate_rows: frozenset[int] = frozenset()
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class FactRef:
    """Identifies a normalized fact needing evidence.

    Attributes:
        bridge: which typed bridge the link belongs in — one of
            ``"service"``, ``"unqualified"``, ``"measurement"``, ``"configuration"``.
        fact_id: the fact's id within its table.
        field_code: the typed field within the fact (e.g. ``"torque_nm"``).
        cell_ids: the source cells that back this field.
    """

    bridge: str
    fact_id: int
    field_code: str
    cell_ids: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class EvidenceLink:
    """One explicit fact-field -> cell -> row evidence link."""

    bridge: str
    fact_id: int
    field_code: str
    cell_id: int
    row_id: int


@dataclass(slots=True)
class EvidenceMappingResult:
    """Outcome of mapping evidence for a batch of facts.

    Attributes:
        links: the explicit per-row evidence links to persist.
        ambiguous_cells: cell ids assigned to no row (recorded, not linked).
        diagnostics: secret-free EVIDENCE_MISSING / CELL_COORDINATE_AMBIGUOUS
            records.
    """

    links: list[EvidenceLink] = field(default_factory=list)
    ambiguous_cells: set[int] = field(default_factory=set)
    diagnostics: DiagnosticsCollector = field(default_factory=DiagnosticsCollector)


BRIDGES: frozenset[str] = frozenset(
    {"service", "unqualified", "measurement", "configuration"}
)


class EvidenceMapper:
    """Map normalized facts to per-cell, per-row evidence links."""

    def map_evidence(
        self, facts: list[FactRef], cells: dict[int, SourceCell]
    ) -> EvidenceMappingResult:
        """Produce one explicit link per covered row for every fact-field.

        A fact-field with no backing cell is recorded as ``EVIDENCE_MISSING``
        (reject). A backing cell whose row scope is ambiguous is assigned to no
        row and recorded as ``CELL_COORDINATE_AMBIGUOUS`` (quarantine); its
        coordinates and candidate rows are captured.

        Raises:
            IngestionError: ``EVIDENCE_MISSING`` is *raised* (reject disposition)
                for a fact that has no evidence link at all, so an unlinked fact
                can never be published.
        """

        result = EvidenceMappingResult()
        for fact in sorted(facts, key=lambda f: (f.bridge, f.fact_id, f.field_code)):
            self._map_fact(fact, cells, result)
        return result

    @staticmethod
    def _map_fact(
        fact: FactRef, cells: dict[int, SourceCell], result: EvidenceMappingResult
    ) -> None:
        if fact.bridge not in BRIDGES:
            raise ValueError(f"unknown bridge {fact.bridge!r}")

        if not fact.cell_ids:
            # No backing cell at all -> reject publication of this fact.
            fail(
                IngestionErrorCode.EVIDENCE_MISSING,
                affected_unit=f"{fact.bridge}:{fact.fact_id}:{fact.field_code}",
                trigger="normalized fact has no evidence link",
                detail={
                    "bridge": fact.bridge,
                    "fact_id": fact.fact_id,
                    "field_code": fact.field_code,
                },
            )

        produced_any = False
        for cell_id in fact.cell_ids:
            cell = cells.get(cell_id)
            if cell is None:
                fail(
                    IngestionErrorCode.EVIDENCE_MISSING,
                    affected_unit=f"{fact.bridge}:{fact.fact_id}:{fact.field_code}",
                    trigger="evidence references an unknown cell",
                    detail={
                        "bridge": fact.bridge,
                        "fact_id": fact.fact_id,
                        "cell_id": cell_id,
                    },
                )
            if not is_authorized_technical_source(cell.authority_role):
                # A technical value must trace to an authorized-technical-source
                # cell; a context-only cell cannot back it (Property 1).
                fail(
                    IngestionErrorCode.EVIDENCE_MISSING,
                    affected_unit=f"{fact.bridge}:{fact.fact_id}:{fact.field_code}",
                    trigger="evidence cell is not an authorized technical source",
                    detail={
                        "bridge": fact.bridge,
                        "fact_id": fact.fact_id,
                        "cell_id": cell_id,
                        "authority_role": cell.authority_role.value,
                    },
                )

            if cell.ambiguous or not cell.covered_rows:
                # Ambiguous row scope -> assign to no row; record coordinates +
                # candidate rows. The value is quarantined, not published.
                result.ambiguous_cells.add(cell_id)
                result.diagnostics.record(
                    IngestionErrorCode.CELL_COORDINATE_AMBIGUOUS,
                    affected_unit=f"cell:{cell_id}",
                    trigger="cell row scope is undeterminable; assigned to no row",
                    detail={
                        "cell_id": cell_id,
                        "candidate_rows": sorted(cell.candidate_rows),
                    },
                )
                continue

            # One explicit link per covered row — no forward-fill (Property 15).
            for row_id in sorted(cell.covered_rows):
                result.links.append(
                    EvidenceLink(
                        bridge=fact.bridge,
                        fact_id=fact.fact_id,
                        field_code=fact.field_code,
                        cell_id=cell_id,
                        row_id=row_id,
                    )
                )
                produced_any = True

        if not produced_any:
            # Every backing cell was ambiguous: the fact ends up with no link at
            # all, which must reject publication (Property 1 / Req 6.3).
            fail(
                IngestionErrorCode.EVIDENCE_MISSING,
                affected_unit=f"{fact.bridge}:{fact.fact_id}:{fact.field_code}",
                trigger="fact has no usable evidence link after mapping",
                detail={
                    "bridge": fact.bridge,
                    "fact_id": fact.fact_id,
                    "field_code": fact.field_code,
                },
            )

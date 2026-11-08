"""Reconciler filter: merge extraction candidates, quarantine conflicts (Task 7).

Design reference: data-and-ingestion/design.md § Components and Interfaces /
Reconciler.

Merges per cell/field the candidate hypotheses produced by the extractors
(fresh_extraction). Agreeing candidates are merged into a single reconciled
value. Disagreement is **never** resolved by extractor confidence alone
(Req 6.4): differing normalized values raise/record ``EXTRACTOR_DISAGREEMENT``
and the field is quarantined (held back, never published). An unresolved
cross-source conflict raises/records ``SOURCE_CONFLICT`` and is likewise
quarantined (Req 9.6).

Both error codes carry the ``quarantine`` disposition, so the Reconciler records
them on a :class:`~series76_data.pipeline.diagnostics.DiagnosticsCollector` and
keeps processing the run rather than aborting — but the affected field never
reaches the published set.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from series76_data.errors import IngestionErrorCode
from series76_data.pipeline.diagnostics import DiagnosticsCollector


@dataclass(frozen=True, slots=True)
class ExtractionCandidate:
    """One extractor's hypothesis for a single cell/field.

    Attributes:
        cell_key: identifies the cell/field this candidate is about.
        extractor: the extractor id (e.g. ``"ocr"`` or ``"gemini"``).
        normalized_value: the comparison form of the candidate value. Two
            candidates *agree* iff their ``normalized_value`` are equal.
        source_id: the source document the candidate derives from; used to
            detect cross-source conflicts.
        confidence: the extractor's self-reported confidence. Recorded for
            diagnostics only — it is **never** used to resolve a disagreement.
    """

    cell_key: str
    extractor: str
    normalized_value: str
    source_id: str = "primary"
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ReconciledValue:
    """A single agreed value for a cell/field after reconciliation."""

    cell_key: str
    normalized_value: str
    source_id: str
    contributing_extractors: tuple[str, ...]


@dataclass(slots=True)
class ReconciliationResult:
    """Outcome of reconciling a batch of candidates.

    Attributes:
        reconciled: the cell/field values where all candidates agreed.
        quarantined: cell keys held back (disagreement or conflict), never
            published; each has a matching recorded failure in ``diagnostics``.
        diagnostics: the secret-free failure records (EXTRACTOR_DISAGREEMENT /
            SOURCE_CONFLICT) for the quarantined cells.
    """

    reconciled: dict[str, ReconciledValue] = field(default_factory=dict)
    quarantined: set[str] = field(default_factory=set)
    diagnostics: DiagnosticsCollector = field(default_factory=DiagnosticsCollector)


class Reconciler:
    """Merge candidates per cell/field; quarantine disagreements and conflicts."""

    def reconcile(
        self, candidates: list[ExtractionCandidate]
    ) -> ReconciliationResult:
        """Group candidates by cell and reconcile each group.

        A cell is *reconciled* only when every candidate for it shares one
        normalized value (and, implicitly, no cross-source conflict). Otherwise
        it is quarantined with the appropriate code. Confidence is ignored for
        resolution.
        """

        result = ReconciliationResult()
        by_cell: dict[str, list[ExtractionCandidate]] = defaultdict(list)
        for candidate in candidates:
            by_cell[candidate.cell_key].append(candidate)

        for cell_key in sorted(by_cell):
            group = by_cell[cell_key]
            self._reconcile_cell(cell_key, group, result)
        return result

    @staticmethod
    def _reconcile_cell(
        cell_key: str,
        group: list[ExtractionCandidate],
        result: ReconciliationResult,
    ) -> None:
        distinct_values = {c.normalized_value for c in group}
        distinct_sources = {c.source_id for c in group}

        if len(distinct_values) > 1:
            # Differing normalized values. If the disagreement spans more than
            # one source, it is a cross-source conflict (SOURCE_CONFLICT);
            # otherwise it is an extractor disagreement. Either way: quarantine,
            # never resolved by confidence.
            if len(distinct_sources) > 1:
                result.diagnostics.record(
                    IngestionErrorCode.SOURCE_CONFLICT,
                    affected_unit=f"cell:{cell_key}",
                    trigger="unresolved cross-source conflict",
                    detail={
                        "cell_key": cell_key,
                        "values": sorted(distinct_values),
                        "sources": sorted(distinct_sources),
                    },
                )
            else:
                result.diagnostics.record(
                    IngestionErrorCode.EXTRACTOR_DISAGREEMENT,
                    affected_unit=f"cell:{cell_key}",
                    trigger="extractors produced differing normalized values",
                    detail={
                        "cell_key": cell_key,
                        "values": sorted(distinct_values),
                        "extractors": sorted(c.extractor for c in group),
                    },
                )
            result.quarantined.add(cell_key)
            return

        # All candidates agree on the normalized value.
        agreed = next(iter(distinct_values))
        result.reconciled[cell_key] = ReconciledValue(
            cell_key=cell_key,
            normalized_value=agreed,
            source_id=sorted(distinct_sources)[0],
            contributing_extractors=tuple(sorted(c.extractor for c in group)),
        )

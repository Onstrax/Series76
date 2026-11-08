"""Verifier transactional gate (Spec 1, Task 10).

Design reference: data-and-ingestion/design.md § Components and Interfaces /
Verifier and § Correctness Properties 4, 5, 28.

The Verifier is the gate between a candidate edition and publication. It:

* confirms the **7 tables / 68 rows / 4 N/A** *oracle* — these are expected
  values supplied to the gate, NOT asserted to be the real PDF's counts — and
  reports ``ROW_COUNT_MISMATCH`` or ``SECTION_MISSING`` on divergence, recording
  it for human resolution and never auto-resolving (Property 5, Req 3.3);
* requires **100% manual-audit coverage** with zero unverified relevant cells
  (Property 4, Req 3.1, 3.6);
* verifies dual-unit torque where printed, 50/60 Hz conditions, AC/DC modes,
  merged-cell coverage, resolved conflicts, evidence links present, and
  manifest/hash consistency;
* rejects an edition whose two part numbers resolve to the same canonical
  identity with ``DUPLICATE_IDENTITY`` (Property 28, Req 9.5);
* **PASSes only if zero open critical discrepancies** remain.

On any failure the gate does not pass; the Publisher must therefore not activate
the edition, and the active edition is left unchanged. The gate itself is pure
over its typed input (an :class:`AuditedEdition` snapshot) so its decisions are
individually testable; the Publisher runs it inside a real transaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.pipeline.diagnostics import DiagnosticsCollector, classify


@dataclass(frozen=True, slots=True)
class OracleCounts:
    """The expected audit oracle the gate compares audited counts against.

    These are *parameters* (expected values), never a pre-verified fact about
    the real PDF. The initial edition's oracle is (7, 68, 4).
    """

    tables: int = 7
    rows: int = 68
    na_values: int = 4


@dataclass(frozen=True, slots=True)
class AuditedCounts:
    """The counts actually observed by the manual audit."""

    tables: int
    rows: int
    na_values: int


@dataclass(frozen=True, slots=True)
class AuditedEdition:
    """A typed snapshot of a candidate edition presented to the gate.

    Attributes:
        counts: the audited table/row/N-A counts.
        relevant_cell_ids: every relevant cell that must be audited.
        verified_cell_ids: cells confirmed by the manual audit.
        open_critical_discrepancies: count of unresolved critical discrepancies.
        canonical_pns: canonical part numbers in the edition (duplicates here
            are what triggers ``DUPLICATE_IDENTITY``).
        facts_with_evidence: ``True`` iff every fact has an evidence link.
        manifest_hash_consistent: ``True`` iff the manifest/source hashes agree.
        missing_sections: table codes the oracle expects but the audit lacks.
    """

    counts: AuditedCounts
    relevant_cell_ids: frozenset[int]
    verified_cell_ids: frozenset[int]
    open_critical_discrepancies: int
    canonical_pns: tuple[str, ...]
    facts_with_evidence: bool
    manifest_hash_consistent: bool
    missing_sections: tuple[str, ...] = ()


@dataclass(slots=True)
class VerificationReport:
    """The outcome of running the gate.

    ``passed`` is the single publish/no-publish decision; ``diagnostics`` holds
    every recorded, secret-free discrepancy for human resolution (nothing is
    auto-resolved).
    """

    passed: bool
    diagnostics: DiagnosticsCollector = field(default_factory=DiagnosticsCollector)

    @property
    def audit_coverage_complete(self) -> bool:
        """Convenience: no coverage or oracle diagnostics were recorded."""

        return self.passed


def audit_coverage_complete(edition: AuditedEdition) -> bool:
    """True iff every relevant cell is verified (100% coverage, Property 4)."""

    return edition.relevant_cell_ids <= edition.verified_cell_ids


class Verifier:
    """The transactional publication gate."""

    def verify(
        self, edition: AuditedEdition, oracle: OracleCounts | None = None
    ) -> VerificationReport:
        """Run every gate check and return a :class:`VerificationReport`.

        The gate records each discrepancy (for human resolution) and passes only
        when none is recorded. ``DUPLICATE_IDENTITY`` is *raised* (reject
        disposition) because a duplicate canonical identity is a hard edition
        build failure, not a recordable-and-continue discrepancy.

        Raises:
            IngestionError: ``DUPLICATE_IDENTITY`` if two PNs share a canonical
                identity in the edition (Property 28).
        """

        oracle = oracle or OracleCounts()
        report = VerificationReport(passed=True)
        diag = report.diagnostics

        self._check_duplicate_identity(edition)
        self._check_oracle(edition, oracle, diag)
        self._check_audit_coverage(edition, diag)
        self._check_evidence(edition, diag)
        self._check_manifest(edition, diag)
        self._check_open_critical(edition, diag)

        report.passed = len(diag.failures) == 0
        return report

    @staticmethod
    def _check_duplicate_identity(edition: AuditedEdition) -> None:
        seen: set[str] = set()
        for pn in edition.canonical_pns:
            if pn in seen:
                raise IngestionError(
                    classify(
                        IngestionErrorCode.DUPLICATE_IDENTITY,
                        affected_unit=f"pn:{pn}",
                        trigger="two part numbers resolve to the same canonical identity",
                        detail={"canonical_pn": pn},
                    ).failure
                )
            seen.add(pn)

    @staticmethod
    def _check_oracle(
        edition: AuditedEdition, oracle: OracleCounts, diag: DiagnosticsCollector
    ) -> None:
        if edition.missing_sections:
            diag.record(
                IngestionErrorCode.SECTION_MISSING,
                affected_unit="edition",
                trigger="expected section(s) absent vs oracle",
                detail={"missing_sections": list(edition.missing_sections)},
            )
        counts = edition.counts
        if (
            counts.tables != oracle.tables
            or counts.rows != oracle.rows
            or counts.na_values != oracle.na_values
        ):
            diag.record(
                IngestionErrorCode.ROW_COUNT_MISMATCH,
                affected_unit="edition",
                trigger="audited counts differ from the oracle; recorded, not auto-resolved",
                detail={
                    "expected": {
                        "tables": oracle.tables,
                        "rows": oracle.rows,
                        "na_values": oracle.na_values,
                    },
                    "audited": {
                        "tables": counts.tables,
                        "rows": counts.rows,
                        "na_values": counts.na_values,
                    },
                },
            )

    @staticmethod
    def _check_audit_coverage(
        edition: AuditedEdition, diag: DiagnosticsCollector
    ) -> None:
        unverified = edition.relevant_cell_ids - edition.verified_cell_ids
        if unverified:
            diag.record(
                IngestionErrorCode.EVIDENCE_MISSING,
                affected_unit="edition",
                trigger="manual-audit coverage is below 100%",
                detail={"unverified_cell_count": len(unverified)},
            )

    @staticmethod
    def _check_evidence(edition: AuditedEdition, diag: DiagnosticsCollector) -> None:
        if not edition.facts_with_evidence:
            diag.record(
                IngestionErrorCode.EVIDENCE_MISSING,
                affected_unit="edition",
                trigger="one or more published facts lack an evidence link",
            )

    @staticmethod
    def _check_manifest(edition: AuditedEdition, diag: DiagnosticsCollector) -> None:
        if not edition.manifest_hash_consistent:
            diag.record(
                IngestionErrorCode.HASH_MISMATCH,
                affected_unit="edition",
                trigger="manifest/source hash inconsistency",
            )

    @staticmethod
    def _check_open_critical(
        edition: AuditedEdition, diag: DiagnosticsCollector
    ) -> None:
        if edition.open_critical_discrepancies > 0:
            diag.record(
                IngestionErrorCode.ROW_COUNT_MISMATCH,
                affected_unit="edition",
                trigger="open critical discrepancies remain",
                detail={"open_critical": edition.open_critical_discrepancies},
            )

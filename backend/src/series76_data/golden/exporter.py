"""GoldenDatasetExporter and round-trip verification (Spec 1, Task 14).

Design reference: data-and-ingestion/design.md § Components and Interfaces /
GoldenDatasetExporter and § Correctness Properties 24, 25, 26.

Produces exactly one versioned ``Golden_Dataset_Artifact`` per published edition
(Property 24), with a monotonically increasing version unique within the edition
(Req 10.1). For 100% of published values it records four NON-NULL attributes:
printed value, unit, source row reference, and source cell reference (Req 10.2).
N/A and absence are stored as two DISTINCT explicit markers — never zero/empty
(Property 14 re-exercised). Each artifact is bound to exactly one ``edition_id``
and that edition's ``manifest_digest`` (Property 25, Req 10.4).

Round-trip verification (Property 26): a verified_replay reconstruction yields a
value set EQUAL to the golden set (count + printed value + unit + row ref + cell
ref); any difference is rejected with a round-trip mismatch report and leaves the
existing artifact unchanged (Req 10.5, 10.6).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from series76_data.errors import IngestionErrorCode
from series76_data.models.enums import AvailabilityStatus
from series76_data.models.value_status import Measured
from series76_data.pipeline.diagnostics import fail

# The two distinct explicit absence markers — never zero and never empty, so
# they are each distinguishable from a documented value and from one another.
NA_MARKER = "__N/A__"
ABSENT_MARKER = "__ABSENT__"


def printed_value_marker(measured: Measured) -> str:
    """Return the golden printed-value marker for a :class:`Measured`.

    * A documented value (including zero) -> its exact string form.
    * N/A -> :data:`NA_MARKER`.
    * Absence -> :data:`ABSENT_MARKER`.

    The two absence states therefore remain distinct explicit markers
    (Property 14); a documented zero is ``"0"`` and never collapses to either.
    """

    status = measured.metric.status
    if status is AvailabilityStatus.AVAILABLE:
        assert measured.metric.value is not None  # invariant of MetricValue
        return format(measured.metric.value, "f")
    if status is AvailabilityStatus.NOT_APPLICABLE:
        return NA_MARKER
    if status is AvailabilityStatus.NOT_DOCUMENTED:
        return ABSENT_MARKER
    # NOT_VERIFIED must never reach the golden set (published values only).
    fail(
        IngestionErrorCode.EVIDENCE_MISSING,
        affected_unit="golden-value",
        trigger="unverified value cannot enter the golden dataset",
        detail={"status": status.value},
    )


@dataclass(frozen=True, slots=True)
class GoldenValue:
    """One published value with its four mandatory non-null attributes.

    ``printed_value`` carries either an exact numeric string or one of the two
    absence markers; ``unit`` is the printed unit marker; ``row_ref`` and
    ``cell_ref`` are the source references. All four are non-null (Req 10.2).
    """

    printed_value: str
    unit: str
    row_ref: str
    cell_ref: str

    def key(self) -> tuple[str, str, str, str]:
        """A hashable identity used for set equivalence in round-trip checks."""

        return (self.printed_value, self.unit, self.row_ref, self.cell_ref)


# A printed value with no printed unit still needs a non-null unit attribute; we
# use an explicit marker so "no unit" is distinct from a real unit string.
NO_UNIT_MARKER = "__NO_UNIT__"


def golden_value_from_measured(
    measured: Measured, row_ref: str, cell_ref: str
) -> GoldenValue:
    """Build a :class:`GoldenValue` from a measured value and its references.

    All four attributes are guaranteed non-null: the printed value uses an
    explicit marker for N/A/absence, and a missing unit uses :data:`NO_UNIT_MARKER`.
    """

    if not row_ref:
        fail(
            IngestionErrorCode.EVIDENCE_MISSING,
            affected_unit="golden-value",
            trigger="golden value missing source row reference",
        )
    if not cell_ref:
        fail(
            IngestionErrorCode.EVIDENCE_MISSING,
            affected_unit="golden-value",
            trigger="golden value missing source cell reference",
        )
    return GoldenValue(
        printed_value=printed_value_marker(measured),
        unit=measured.unit if measured.unit else NO_UNIT_MARKER,
        row_ref=row_ref,
        cell_ref=cell_ref,
    )


@dataclass(frozen=True, slots=True)
class GoldenArtifact:
    """A versioned golden dataset artifact bound to exactly one edition.

    Attributes:
        edition_id: the single edition this artifact belongs to (Property 25).
        manifest_digest: that edition's canonical digest (Property 25).
        version: monotonically increasing, unique within the edition (Req 10.1).
        values: the published value set (Req 10.2).
    """

    edition_id: str
    manifest_digest: str
    version: int
    values: tuple[GoldenValue, ...]

    def value_key_set(self) -> frozenset[tuple[str, str, str, str]]:
        """The set of value keys for round-trip equivalence comparison."""

        return frozenset(v.key() for v in self.values)


@dataclass(slots=True)
class RoundTripReport:
    """The result of a round-trip comparison (Property 26)."""

    equivalent: bool
    missing_from_reconstruction: tuple[tuple[str, str, str, str], ...] = ()
    unexpected_in_reconstruction: tuple[tuple[str, str, str, str], ...] = ()


class GoldenDatasetExporter:
    """Export one versioned golden artifact per edition and verify round-trips."""

    def export(
        self,
        edition_id: str,
        manifest_digest: str,
        values: list[GoldenValue],
        existing_versions: frozenset[int] = frozenset(),
    ) -> GoldenArtifact:
        """Produce one artifact with a monotonically increasing unique version.

        Args:
            existing_versions: versions already assigned within this edition; the
                new version is ``max(existing)+1`` (or ``1``) and is guaranteed
                unique and increasing (Property 24).
        """

        version = (max(existing_versions) + 1) if existing_versions else 1
        self._require_complete_attributes(values)
        return GoldenArtifact(
            edition_id=edition_id,
            manifest_digest=manifest_digest,
            version=version,
            values=tuple(values),
        )

    @staticmethod
    def _require_complete_attributes(values: list[GoldenValue]) -> None:
        for value in values:
            if not (value.printed_value and value.unit and value.row_ref and value.cell_ref):
                fail(
                    IngestionErrorCode.EVIDENCE_MISSING,
                    affected_unit="golden-artifact",
                    trigger="golden value has a null/empty mandatory attribute",
                )

    def verify_round_trip(
        self,
        artifact: GoldenArtifact,
        reconstructed_values: list[GoldenValue],
    ) -> RoundTripReport:
        """Compare a reconstruction against the golden set (Property 26).

        Equivalence requires identical value count and, for every value,
        identical printed value, unit, row ref, and cell ref. Any difference
        produces a non-equivalent report naming the differing values; the
        existing artifact is never altered by this method.
        """

        golden_keys = artifact.value_key_set()
        recon_keys = frozenset(v.key() for v in reconstructed_values)

        missing = tuple(sorted(golden_keys - recon_keys))
        unexpected = tuple(sorted(recon_keys - golden_keys))
        # A set comparison also catches count differences introduced by
        # duplicates vs. the distinct golden set; guard count explicitly too.
        equivalent = (
            not missing
            and not unexpected
            and len(reconstructed_values) == len(artifact.values)
        )
        return RoundTripReport(
            equivalent=equivalent,
            missing_from_reconstruction=missing,
            unexpected_in_reconstruction=unexpected,
        )


@dataclass(slots=True)
class _VersionLedger:
    """Internal helper tracking assigned versions per edition (used by callers)."""

    assigned: dict[str, set[int]] = field(default_factory=dict)

    def next_version(self, edition_id: str) -> int:
        used = self.assigned.setdefault(edition_id, set())
        version = (max(used) + 1) if used else 1
        used.add(version)
        return version

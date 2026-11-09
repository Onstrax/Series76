"""Pure in-memory domain types and the ``Part`` aggregate (design § Data Models).

These types carry no persistence or transport concerns. Each fact carries a
:class:`~series76_domain.model.enums.DataStatus` (via its
:class:`~series76_domain.model.metric_value.MetricValue`s) and an
:class:`~series76_domain.model.evidence.EvidenceReference`. The design
invariants are enforced at construction:

* ``T04`` (On/Off 24V AC/DC) and ``T05`` (Modulating 24V DC) are **distinct**
  :class:`Configuration`s — never merged.
* exactly one :class:`ServicePerformance` per distinct printed service type;
  its dual torque (in-lbs / Nm) figures are independent.
* a ``T03`` :class:`UnqualifiedPerformance` carries **no** service type and is
  never split by On/Off vs Modulating.
* an :class:`OperatingCondition` has a positive ``frequency_hz`` **iff** its
  ``frequency_state`` is ``EXPLICIT``.
* an :class:`ElectricalMeasurement` is bound to exactly one operating
  condition; its values never cross-bind 50 Hz and 60 Hz contexts.
* a :class:`Note` keeps literal text and covers exactly its source rows.
* every fact in a :class:`Part` belongs to one pinned edition.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from series76_data.models.enums import FrequencyState, SupplyMode
from series76_domain.model.enums import DataStatus
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.metric_value import MetricValue


class DomainInvariantError(ValueError):
    """Raised when a pure domain type violates a design invariant."""


@dataclass(frozen=True, slots=True)
class PartNumber:
    """A canonical part number, unique per edition.

    The ``printed_pn`` is kept verbatim and never decoded for meaning; the
    ``canonical_pn`` is the normalized identity used for lookup.
    """

    canonical_pn: str
    printed_pn: str
    edition_id: uuid.UUID
    part_id: int

    @property
    def base_pn(self) -> str:
        """The Base Part Number used for the ranking tiebreak (ascending)."""
        return self.canonical_pn


@dataclass(frozen=True, slots=True)
class SupplyProfile:
    """A nominal supply profile (voltage, phase, admitted AC/DC mode set)."""

    voltage_v: MetricValue
    phase_state: str | None
    phase_count: int | None
    modes: frozenset[SupplyMode]


@dataclass(frozen=True, slots=True)
class Configuration:
    """A PN × documented configuration (T04 and T05 stay distinct).

    ``configuration_id`` is the per-edition identity; two configurations with
    different ids are never merged even if they look similar.
    """

    configuration_id: int
    edition_id: uuid.UUID
    enclosure: str | None
    supply_profile: SupplyProfile | None
    motor_power: MetricValue
    availability: DataStatus
    evidence: EvidenceReference


@dataclass(frozen=True, slots=True)
class ServicePerformance:
    """Performance attributed to one printed service type.

    The two torque figures (``torque_inlbs`` and ``torque_nm``) are independent
    documented values — one being N/A or absent does not affect the other.
    """

    configuration_id: int
    service_type: str
    torque_inlbs: MetricValue
    torque_nm: MetricValue
    duty_s4: MetricValue
    cycles_per_hour: MetricValue
    starts_per_hour: MetricValue
    evidence: EvidenceReference


@dataclass(frozen=True, slots=True)
class UnqualifiedPerformance:
    """A T03 performance row with NO service attribution (never split)."""

    configuration_id: int
    torque_inlbs: MetricValue
    torque_nm: MetricValue
    duty_s4: MetricValue
    cycles_per_hour: MetricValue
    starts_per_hour: MetricValue
    evidence: EvidenceReference


@dataclass(frozen=True, slots=True)
class OperatingCondition:
    """A frequency context for a configuration.

    Invariant: ``frequency_hz`` is present and positive **iff**
    ``frequency_state`` is ``EXPLICIT`` (Property 3 / design).
    """

    condition_id: int
    configuration_id: int
    frequency_state: FrequencyState
    frequency_hz: MetricValue

    def __post_init__(self) -> None:
        explicit = self.frequency_state is FrequencyState.EXPLICIT
        has_hz = self.frequency_hz.is_available
        if explicit != has_hz:
            raise DomainInvariantError(
                "frequency_hz must be present iff frequency_state is EXPLICIT"
            )
        if explicit and self.frequency_hz.value is not None and self.frequency_hz.value <= 0:
            raise DomainInvariantError("EXPLICIT frequency_hz must be positive")


@dataclass(frozen=True, slots=True)
class ElectricalMeasurement:
    """One measurement block bound to exactly one operating condition.

    Values are never cross-bound across 50/60 Hz: a measurement references a
    single ``condition_id`` and that condition carries the one frequency
    context. ``frequency_hz`` is a convenience copy of the bound condition's
    frequency for labeling.
    """

    measurement_id: int
    condition_id: int
    frequency_state: FrequencyState
    frequency_hz: MetricValue
    operating_speed: MetricValue
    fla: MetricValue
    lra: MetricValue
    evidence: EvidenceReference


@dataclass(frozen=True, slots=True)
class Note:
    """A literal source note with its exact covered-row scope.

    ``printed_text`` is the literal text, never summarized. ``covered_rows`` is
    exactly the set of source rows the note covers — no forward-fill or
    extension (Property 26).
    """

    note_id: int
    marker: str | None
    note_type: str | None
    printed_text: str
    covered_rows: tuple[int, ...]
    data_status: DataStatus
    evidence: EvidenceReference


@dataclass(frozen=True, slots=True)
class Part:
    """The aggregate of every documented fact for one PN in one edition.

    Invariant: every child fact belongs to the same ``edition_id`` as the
    :class:`PartNumber`; constructing a ``Part`` whose facts span editions is
    rejected. Exactly one :class:`ServicePerformance` per printed service type.
    """

    part_number: PartNumber
    configurations: tuple[Configuration, ...] = ()
    service_performance: tuple[ServicePerformance, ...] = ()
    unqualified_performance: tuple[UnqualifiedPerformance, ...] = ()
    operating_conditions: tuple[OperatingCondition, ...] = ()
    measurements: tuple[ElectricalMeasurement, ...] = ()
    notes: tuple[Note, ...] = field(default=())

    def __post_init__(self) -> None:
        edition = self.part_number.edition_id
        for cfg in self.configurations:
            if cfg.edition_id != edition:
                raise DomainInvariantError(
                    "all Part facts must belong to the same pinned edition"
                )
        # One ServicePerformance per (configuration, printed service type).
        seen: set[tuple[int, str]] = set()
        for sp in self.service_performance:
            key = (sp.configuration_id, sp.service_type)
            if key in seen:
                raise DomainInvariantError(
                    f"duplicate ServicePerformance for service type {sp.service_type!r}"
                )
            seen.add(key)

    @property
    def edition_id(self) -> uuid.UUID:
        """The single pinned edition every fact of this part belongs to."""
        return self.part_number.edition_id

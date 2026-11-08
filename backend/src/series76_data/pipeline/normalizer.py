"""Normalizer filter: produce typed facts with faithful technical semantics.

Design reference: data-and-ingestion/design.md § Components and Interfaces /
Normalizer and § Correctness Properties 7-14.

This is the crux of the assessment. The Normalizer converts printed source
observations into typed facts while honoring, *exactly*, the Series 76 technical
semantics:

* **Dual torque** (Property 7): ``torque_inlbs`` and ``torque_nm`` are two
  independent :class:`~series76_data.models.value_status.MetricValue`s. One is
  NEVER derived from, converted into, rounded from, or overwritten by the other.
* **service_performance** (Property 8): exactly one record per *distinct printed
  service type*.
* **T03 unqualified_performance** (Property 9): NO service attribution;
  ``cycles_per_hour`` and ``starts_per_hour`` are two separate fields; no service
  is fabricated and no split by On/Off or Modulating is performed.
* **Frequency binding** (Property 10): speed/FLA/LRA bind to exactly one
  :class:`OperatingConditionFact` per printed frequency; a 50 Hz value is never
  bound to 60 Hz or vice versa; not-specified / not-applicable frequency never
  invents an Hz number (``frequency_hz`` stays ``None`` unless the state is
  EXPLICIT, in which case it is present and positive).
* **T04 vs T05** (Property 11): On/Off 24V AC/DC (T04) and Modulating 24V DC
  (T05) are DISTINCT configurations, never merged or deduplicated.
* **N/A vs absence** (Property 14): a printed "N/A" maps to
  ``NOT_APPLICABLE``; no printed value maps to ``NOT_DOCUMENTED``.
* **Notes / asterisks** (Property 12): printed text preserved verbatim, scoped
  to exactly the covered rows, with no forward-fill.
* **Unsupported units** (Property 13): a unit outside the recognized set raises
  ``UNSUPPORTED_UNIT``; the printed value and unit are retained unchanged, never
  coerced or converted.

Numbers are parsed into :class:`~decimal.Decimal` — never ``float`` — so no
silent rounding occurs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from series76_data.errors import IngestionErrorCode
from series76_data.models.enums import AvailabilityStatus, FrequencyState
from series76_data.models.value_status import Measured, MetricValue
from series76_data.pipeline.diagnostics import fail

# Printed tokens that mean "not applicable" rather than "absent" or a number.
_NA_TOKENS: frozenset[str] = frozenset({"n/a", "na", "n.a.", "not applicable"})

# Recognized units per metric family. A unit outside its family's set is
# UNSUPPORTED_UNIT (Req 4.8) — the value is retained, never coerced.
RECOGNIZED_UNITS: dict[str, frozenset[str]] = {
    "torque_inlbs": frozenset({"in-lbs", "in·lbs", "inlbs", "in lb", "lb-in"}),
    "torque_nm": frozenset({"nm", "n·m", "n-m", "n m"}),
    "duty_s4_pct": frozenset({"%", "percent", "pct"}),
    "cycles_per_hour": frozenset({"cycles/h", "cph", "cycles per hour", "c/h"}),
    "starts_per_hour": frozenset({"starts/h", "sph", "starts per hour", "s/h"}),
    "operating_speed_sec": frozenset({"s", "sec", "seconds"}),
    "fla_a": frozenset({"a", "amp", "amps", "ampere", "amperes"}),
    "lra_a": frozenset({"a", "amp", "amps", "ampere", "amperes"}),
    "motor_power_w": frozenset({"w", "watt", "watts"}),
    "frequency_hz": frozenset({"hz", "hertz"}),
}


@dataclass(frozen=True, slots=True)
class PrintedCell:
    """A single printed observation before normalization.

    Attributes:
        text: the printed text, verbatim (may be a number, "N/A", or empty).
        unit: the printed unit text, or ``None`` if none was printed.
    """

    text: str | None
    unit: str | None = None


def normalize_metric(field_code: str, cell: PrintedCell | None) -> Measured:
    """Normalize one printed cell into a :class:`Measured` for ``field_code``.

    Rules:
        * ``cell is None`` or empty text -> ``NOT_DOCUMENTED`` (absence).
        * printed "N/A" -> ``NOT_APPLICABLE`` (distinct from absence/zero).
        * a parseable number -> ``AVAILABLE`` with the exact :class:`Decimal`;
          its unit must be recognized for ``field_code`` or ``UNSUPPORTED_UNIT``
          is raised with the printed value+unit retained unchanged.

    Raises:
        IngestionError: ``UNSUPPORTED_UNIT`` when the unit is unrecognized.
    """

    if cell is None or cell.text is None or cell.text.strip() == "":
        return Measured(MetricValue.not_documented(), None)

    token = cell.text.strip()
    if token.lower() in _NA_TOKENS:
        return Measured(MetricValue.not_applicable(), None)

    # A documented numeric value: parse exactly, never via float.
    try:
        value = Decimal(token.replace(",", ""))
    except InvalidOperation:
        # Non-numeric, non-N/A text is not a measurable metric. Treat the unit
        # check first so an unrecognized unit is still surfaced, then reject the
        # value as unsupported (it carries a unit the pipeline cannot place).
        _require_recognized_unit(field_code, token, cell.unit)
        return Measured(MetricValue.not_documented(), cell.unit)

    _require_recognized_unit(field_code, token, cell.unit)
    return Measured(MetricValue.available(value), cell.unit)


def _require_recognized_unit(field_code: str, printed_value: str, unit: str | None) -> None:
    """Raise ``UNSUPPORTED_UNIT`` if ``unit`` is not recognized for ``field_code``.

    A ``None`` unit is permitted (dimensionless / unit implied by the column).
    The printed value and unit are retained unchanged — this function never
    converts or coerces (Req 4.8).
    """

    if unit is None:
        return
    allowed = RECOGNIZED_UNITS.get(field_code, frozenset())
    if unit.strip().lower() not in {u.lower() for u in allowed}:
        fail(
            IngestionErrorCode.UNSUPPORTED_UNIT,
            affected_unit=f"field:{field_code}",
            trigger="unit not recognized for this field; value retained unchanged",
            detail={
                "field_code": field_code,
                "printed_value": printed_value,
                "printed_unit": unit,
            },
        )


# --- Dual torque (Property 7) ------------------------------------------------


@dataclass(frozen=True, slots=True)
class TorquePair:
    """Two independent torque figures, never derived from one another.

    ``inlbs`` and ``nm`` are stored exactly as printed. The Normalizer never
    computes one from the other; a missing figure is an honest absence, not a
    converted value.
    """

    inlbs: Measured
    nm: Measured


def normalize_torque(
    inlbs_cell: PrintedCell | None, nm_cell: PrintedCell | None
) -> TorquePair:
    """Normalize the two torque cells independently (Property 7)."""

    return TorquePair(
        inlbs=normalize_metric("torque_inlbs", inlbs_cell),
        nm=normalize_metric("torque_nm", nm_cell),
    )


# --- Service vs unqualified performance (Properties 8, 9) --------------------


@dataclass(frozen=True, slots=True)
class ServicePerformanceFact:
    """Performance attributed to exactly one printed service type (Property 8)."""

    service_type: str
    torque: TorquePair
    duty_s4_pct: Measured
    cycles_per_hour: Measured
    starts_per_hour: Measured


@dataclass(frozen=True, slots=True)
class UnqualifiedPerformanceFact:
    """T03 performance with NO service attribution (Property 9).

    ``cycles_per_hour`` and ``starts_per_hour`` are two separate retrievable
    fields; there is deliberately no ``service_type`` and no On/Off/Modulating
    split.
    """

    torque: TorquePair
    duty_s4_pct: Measured
    cycles_per_hour: Measured
    starts_per_hour: Measured


@dataclass(frozen=True, slots=True)
class PrintedServiceRow:
    """A printed performance row carrying its (possibly absent) service type."""

    service_type: str | None
    torque_inlbs: PrintedCell | None = None
    torque_nm: PrintedCell | None = None
    duty_s4_pct: PrintedCell | None = None
    cycles_per_hour: PrintedCell | None = None
    starts_per_hour: PrintedCell | None = None


def normalize_service_performance(
    rows: list[PrintedServiceRow],
) -> list[ServicePerformanceFact]:
    """Emit exactly one fact per distinct printed service type (Property 8).

    Rows without a printed service type are ignored here (they belong to
    :func:`normalize_unqualified_performance`). Duplicate service types collapse
    to a single record keyed by the service type.

    Raises:
        IngestionError: ``EXTRACTOR_DISAGREEMENT`` if two rows print the *same*
            service type with differing metric values (an unresolved conflict
            that must not be silently merged).
    """

    by_service: dict[str, ServicePerformanceFact] = {}
    for row in rows:
        if row.service_type is None or row.service_type.strip() == "":
            continue
        service_type = row.service_type.strip()
        fact = ServicePerformanceFact(
            service_type=service_type,
            torque=normalize_torque(row.torque_inlbs, row.torque_nm),
            duty_s4_pct=normalize_metric("duty_s4_pct", row.duty_s4_pct),
            cycles_per_hour=normalize_metric("cycles_per_hour", row.cycles_per_hour),
            starts_per_hour=normalize_metric("starts_per_hour", row.starts_per_hour),
        )
        existing = by_service.get(service_type)
        if existing is not None and existing != fact:
            fail(
                IngestionErrorCode.EXTRACTOR_DISAGREEMENT,
                affected_unit=f"service:{service_type}",
                trigger="same service type printed with differing values",
                detail={"service_type": service_type},
            )
        by_service[service_type] = fact
    return [by_service[k] for k in sorted(by_service)]


def normalize_unqualified_performance(
    row: PrintedServiceRow,
) -> UnqualifiedPerformanceFact:
    """Normalize a T03 row with NO service attribution (Property 9).

    Any printed service type on the input is ignored by construction: T03 is
    unqualified, so a service is never fabricated or inferred, and the row is
    never split by On/Off or Modulating.
    """

    return UnqualifiedPerformanceFact(
        torque=normalize_torque(row.torque_inlbs, row.torque_nm),
        duty_s4_pct=normalize_metric("duty_s4_pct", row.duty_s4_pct),
        cycles_per_hour=normalize_metric("cycles_per_hour", row.cycles_per_hour),
        starts_per_hour=normalize_metric("starts_per_hour", row.starts_per_hour),
    )


# --- Frequency binding (Property 10) -----------------------------------------


@dataclass(frozen=True, slots=True)
class OperatingConditionFact:
    """A frequency context plus its one bound measurement block (Property 10)."""

    frequency_state: FrequencyState
    frequency_hz: Decimal | None
    operating_speed_sec: Measured
    fla_a: Measured
    lra_a: Measured

    def __post_init__(self) -> None:
        # Mirror the DB CHECK: EXPLICIT <=> frequency_hz present and > 0.
        explicit = self.frequency_state is FrequencyState.EXPLICIT
        if explicit != (self.frequency_hz is not None):
            raise ValueError("EXPLICIT frequency state requires frequency_hz, and vice versa")
        if explicit and (self.frequency_hz is None or self.frequency_hz <= 0):
            raise ValueError("EXPLICIT frequency_hz must be positive")


@dataclass(frozen=True, slots=True)
class PrintedFrequencyBlock:
    """A printed measurement block tagged with its printed frequency."""

    frequency_state: FrequencyState
    frequency_hz_text: str | None = None
    operating_speed_sec: PrintedCell | None = None
    fla_a: PrintedCell | None = None
    lra_a: PrintedCell | None = None


def normalize_operating_condition(
    block: PrintedFrequencyBlock,
) -> OperatingConditionFact:
    """Bind speed/FLA/LRA to exactly one operating condition (Property 10).

    The EXPLICIT<->Hz invariant is enforced: a not-specified or not-applicable
    frequency never invents an Hz number. An EXPLICIT frequency requires a
    positive, parseable Hz value.

    Raises:
        IngestionError: ``UNSUPPORTED_UNIT`` if a measurement unit is
            unrecognized (value retained unchanged).
    """

    frequency_hz: Decimal | None = None
    if block.frequency_state is FrequencyState.EXPLICIT:
        if block.frequency_hz_text is None or block.frequency_hz_text.strip() == "":
            raise ValueError("EXPLICIT frequency requires a printed Hz value")
        try:
            frequency_hz = Decimal(block.frequency_hz_text.strip())
        except InvalidOperation as exc:
            raise ValueError("frequency_hz is not a parseable number") from exc
        if frequency_hz <= 0:
            raise ValueError("EXPLICIT frequency_hz must be positive")

    return OperatingConditionFact(
        frequency_state=block.frequency_state,
        frequency_hz=frequency_hz,
        operating_speed_sec=normalize_metric(
            "operating_speed_sec", block.operating_speed_sec
        ),
        fla_a=normalize_metric("fla_a", block.fla_a),
        lra_a=normalize_metric("lra_a", block.lra_a),
    )


# --- T04 vs T05 distinct configurations (Property 11) ------------------------


@dataclass(frozen=True, slots=True)
class ConfigurationKey:
    """The identity of a documented configuration.

    T04 (On/Off, 24V, {AC, DC}) and T05 (Modulating, 24V, {DC}) differ in their
    ``control_mode`` (and admitted supply modes), so their keys are never equal.
    They are therefore stored as distinct configurations and never merged.
    """

    table_code: str
    control_mode: str
    voltage_text: str
    supply_modes: tuple[str, ...]


def configuration_key(
    table_code: str, control_mode: str, voltage_text: str, supply_modes: list[str]
) -> ConfigurationKey:
    """Build a normalized, order-stable configuration identity (Property 11)."""

    return ConfigurationKey(
        table_code=table_code,
        control_mode=control_mode.strip().lower(),
        voltage_text=voltage_text.strip().lower(),
        supply_modes=tuple(sorted({m.strip().upper() for m in supply_modes})),
    )


# --- Notes / asterisks (Property 12) -----------------------------------------


@dataclass(frozen=True, slots=True)
class NoteFact:
    """A note/asterisk preserved verbatim and scoped to exactly its rows.

    ``printed_text`` is the source text unchanged; ``covered_rows`` is exactly
    the set of rows the note covers in the source — never forward-filled to
    uncovered rows (Property 12).
    """

    marker: str | None
    printed_text: str
    covered_rows: frozenset[int]


def normalize_note(
    marker: str | None, printed_text: str, covered_rows: set[int]
) -> NoteFact:
    """Preserve a note verbatim and bind it to exactly ``covered_rows``.

    The text is stored byte-for-byte (no trimming of meaningful content) and the
    covered-row set is copied as-is; the Normalizer never extends scope.
    """

    return NoteFact(
        marker=marker,
        printed_text=printed_text,
        covered_rows=frozenset(covered_rows),
    )


@dataclass(slots=True)
class NormalizedConfiguration:
    """The assembled, typed result for one documented configuration."""

    key: ConfigurationKey
    availability: AvailabilityStatus
    motor_power_w: Measured
    service_performance: list[ServicePerformanceFact] = field(default_factory=list)
    unqualified_performance: UnqualifiedPerformanceFact | None = None
    operating_conditions: list[OperatingConditionFact] = field(default_factory=list)
    notes: list[NoteFact] = field(default_factory=list)

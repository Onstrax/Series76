"""The ``get_part`` domain operation (Task 4.1, Req 2.*).

Exact part lookup over the :class:`~series76_domain.repository.port.TypedRepository`:

* a malformed PN yields ``INVALID_PN`` (checked before any catalog query);
* a well-formed PN absent from the pinned edition yields ``PART_NOT_LISTED``
  with **no** substitution and no commercial-existence claim;
* a present PN yields ``PART_FOUND`` with configurations, service/unqualified
  performance, condition-bound measurements, and notes — each carrying its
  :class:`~series76_domain.model.enums.DataStatus` and
  :class:`~series76_domain.model.evidence.EvidenceReference`;
* facts requested under an explicit service/frequency are the bound facts and
  are labeled; when none is given and several measurements apply, **all** are
  returned labeled with none silently selected (Property 5);
* a new lookup against a withdrawn edition yields ``SOURCE_WITHDRAWN``.

Field-level ``NOT_APPLICABLE`` / ``NOT_DOCUMENTED`` states are preserved on the
returned metrics and never coerced (Property 10).
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from series76_data.models.enums import FrequencyState
from series76_domain.model.enums import SemanticFailureCode
from series76_domain.model.types import (
    ElectricalMeasurement,
    OperatingCondition,
    Part,
    ServicePerformance,
    UnqualifiedPerformance,
)
from series76_domain.operations.pn import is_well_formed_pn, normalize_pn
from series76_domain.operations.results import GetPartResult, PartView
from series76_domain.repository.port import TypedRepository


def get_part(
    repository: TypedRepository,
    part_number: str,
    *,
    service: str | None = None,
    frequency_hz: Decimal | int | str | None = None,
    allow_withdrawn: bool = True,
) -> GetPartResult:
    """Look up one part by canonical PN and return labeled facts or a failure.

    Args:
        repository: the edition-pinned read port.
        part_number: the canonical PN to look up.
        service: optional service type to bind service-performance facts to.
        frequency_hz: optional frequency (Hz) to bind measurements to.
        allow_withdrawn: when ``False``, a withdrawn pinned edition yields
            ``SOURCE_WITHDRAWN`` (used by the recommendation path). Pinned
            historical reads keep ``True`` so prior facts remain retrievable.

    Returns:
        A :class:`GetPartResult` with either a labeled :class:`PartView` or a
        single :class:`SemanticFailureCode`.
    """

    if not is_well_formed_pn(part_number):
        return GetPartResult(
            failure=SemanticFailureCode.INVALID_PN, offending_input=part_number
        )

    if not allow_withdrawn and repository.pinned_edition.is_withdrawn:
        return GetPartResult(
            failure=SemanticFailureCode.SOURCE_WITHDRAWN, offending_input=part_number
        )

    requested_freq = _parse_frequency(frequency_hz)
    if frequency_hz is not None and requested_freq is None:
        # A non-numeric frequency is a malformed request input.
        return GetPartResult(
            failure=SemanticFailureCode.INVALID_PN, offending_input=str(frequency_hz)
        )

    canonical = normalize_pn(part_number)
    found = repository.find_part_number(canonical)
    if found is None:
        # Well-formed but absent: no substitution, no existence claim.
        return GetPartResult(
            failure=SemanticFailureCode.PART_NOT_LISTED, offending_input=part_number
        )

    configurations = repository.configurations_for(found)
    service_perf: list[ServicePerformance] = []
    unqualified: list[UnqualifiedPerformance] = []
    conditions: list[OperatingCondition] = []
    measurements: list[ElectricalMeasurement] = []
    for cfg in configurations:
        service_perf.extend(repository.service_performance_for(cfg))
        unqualified.extend(repository.unqualified_performance_for(cfg))
        cfg_conditions = repository.operating_conditions_for(cfg)
        conditions.extend(cfg_conditions)
        for cond in cfg_conditions:
            measurements.extend(repository.measurements_for(cond))

    notes = repository.notes_for_part(found)

    # Apply explicit service/frequency labeling as a *filter over labeled
    # facts* — never a silent selection. When a service is given, only service
    # rows for that service are returned; when a frequency is given, only
    # measurements bound to a condition at that frequency are returned.
    labeled_service = _filter_service(tuple(service_perf), service)
    labeled_measurements = _filter_measurements(
        tuple(measurements), tuple(conditions), requested_freq
    )

    part = Part(
        part_number=found,
        configurations=configurations,
        service_performance=tuple(service_perf),
        unqualified_performance=tuple(unqualified),
        operating_conditions=tuple(conditions),
        measurements=tuple(measurements),
        notes=notes,
    )
    view = PartView(
        part=part,
        configurations=configurations,
        service_performance=labeled_service,
        unqualified_performance=tuple(unqualified),
        operating_conditions=tuple(conditions),
        measurements=labeled_measurements,
        notes=notes,
        requested_service=service,
        requested_frequency_hz=requested_freq,
    )
    return GetPartResult(view=view)


def _parse_frequency(value: Decimal | int | str | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value if value.is_finite() else None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _filter_service(
    rows: tuple[ServicePerformance, ...], service: str | None
) -> tuple[ServicePerformance, ...]:
    if service is None:
        return rows
    return tuple(r for r in rows if r.service_type == service)


def _filter_measurements(
    measurements: tuple[ElectricalMeasurement, ...],
    conditions: tuple[OperatingCondition, ...],
    frequency_hz: Decimal | None,
) -> tuple[ElectricalMeasurement, ...]:
    if frequency_hz is None:
        # No frequency requested: return every applicable measurement labeled,
        # none silently selected (Property 5).
        return measurements
    matching_condition_ids = {
        c.condition_id
        for c in conditions
        if c.frequency_state is FrequencyState.EXPLICIT
        and c.frequency_hz.value is not None
        and c.frequency_hz.value == frequency_hz
    }
    return tuple(m for m in measurements if m.condition_id in matching_condition_ids)

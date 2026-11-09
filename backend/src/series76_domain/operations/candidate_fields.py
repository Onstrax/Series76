"""Build a candidate's filterable :class:`CandidateFields` from repository facts.

This projects the pure domain facts of a part (configurations, service and
unqualified performance, operating conditions, measurements, notes) onto the
:class:`~series76_domain.model.filter_ast.AllowlistField` surface the
``Filter_AST`` evaluator consumes. N/A and absent states are preserved as the
underlying :class:`~series76_domain.model.metric_value.MetricValue` so numeric
predicates never match them and never coerce them (Property 10).
"""

from __future__ import annotations

from series76_domain.model.enums import DataStatus
from series76_domain.model.evaluation import CandidateFields, FieldValue
from series76_domain.model.filter_ast import AllowlistField
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.types import (
    Configuration,
    ElectricalMeasurement,
    Note,
    PartNumber,
    ServicePerformance,
    UnqualifiedPerformance,
)


def build_candidate_fields(
    part: PartNumber,
    configurations: tuple[Configuration, ...],
    service_performance: tuple[ServicePerformance, ...],
    unqualified_performance: tuple[UnqualifiedPerformance, ...],
    measurements: tuple[ElectricalMeasurement, ...],
    notes: tuple[Note, ...],
) -> CandidateFields:
    """Project a part's facts onto the filterable allowlist surface."""

    fields: dict[AllowlistField, list[FieldValue]] = {}

    def add_metric(field: AllowlistField, metric: MetricValue) -> None:
        fields.setdefault(field, []).append(
            FieldValue(status=metric.status, metric=metric)
        )

    def add_scalar(field: AllowlistField, scalar: str | None) -> None:
        status = DataStatus.AVAILABLE if scalar is not None else DataStatus.NOT_DOCUMENTED
        fields.setdefault(field, []).append(FieldValue(status=status, scalar=scalar))

    add_scalar(AllowlistField.EXACT_PN, part.canonical_pn)

    for cfg in configurations:
        add_scalar(AllowlistField.ENCLOSURE, cfg.enclosure)
        add_metric(AllowlistField.MOTOR_POWER, cfg.motor_power)
        if cfg.supply_profile is not None:
            add_metric(AllowlistField.NOMINAL_VOLTAGE, cfg.supply_profile.voltage_v)
            add_scalar(AllowlistField.PHASE, cfg.supply_profile.phase_state)
            for mode in cfg.supply_profile.modes:
                fields.setdefault(AllowlistField.CURRENT_MODE, []).append(
                    FieldValue(status=DataStatus.AVAILABLE, scalar=mode.value)
                )

    for sp in service_performance:
        add_scalar(AllowlistField.SERVICE, sp.service_type)
        add_metric(AllowlistField.TORQUE_INLBS, sp.torque_inlbs)
        add_metric(AllowlistField.TORQUE_NM, sp.torque_nm)
        add_metric(AllowlistField.DUTY_S4, sp.duty_s4)
        add_metric(AllowlistField.CYCLES_PER_HOUR, sp.cycles_per_hour)
        add_metric(AllowlistField.STARTS_PER_HOUR, sp.starts_per_hour)

    for up in unqualified_performance:
        add_metric(AllowlistField.TORQUE_INLBS, up.torque_inlbs)
        add_metric(AllowlistField.TORQUE_NM, up.torque_nm)
        add_metric(AllowlistField.DUTY_S4, up.duty_s4)
        add_metric(AllowlistField.CYCLES_PER_HOUR, up.cycles_per_hour)
        add_metric(AllowlistField.STARTS_PER_HOUR, up.starts_per_hour)

    for m in measurements:
        add_metric(AllowlistField.OPERATING_SPEED, m.operating_speed)
        add_metric(AllowlistField.FLA, m.fla)
        add_metric(AllowlistField.LRA, m.lra)

    for note in notes:
        add_scalar(AllowlistField.NOTE, note.printed_text)

    return {field: tuple(values) for field, values in fields.items()}

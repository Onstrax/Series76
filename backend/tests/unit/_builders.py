"""Helpers to build in-memory parts for fake-repository unit tests."""

from __future__ import annotations

import itertools
import uuid
from decimal import Decimal

from _fakes import FakePartData

from series76_data.models.enums import FrequencyState
from series76_domain.model.enums import DataStatus
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.metric_value import MetricValue
from series76_domain.model.types import (
    Configuration,
    ElectricalMeasurement,
    Note,
    OperatingCondition,
    PartNumber,
    ServicePerformance,
)
from series76_domain.model.units import Unit

_ids = itertools.count(1)


def _next() -> int:
    return next(_ids)


def build_part(
    canonical_pn: str,
    edition_id: uuid.UUID,
    *,
    torque_inlbs: int | None = 100,
    fla: int | None = 2,
    service_type: str = "On/Off",
    enclosure: str = "NEMA 4",
    note_text: str | None = None,
) -> FakePartData:
    """Build one fully-formed fake part with a config, service, measurement."""

    part_id = _next()
    config_id = _next()
    condition_id = _next()
    measurement_id = _next()

    pn = PartNumber(
        canonical_pn=canonical_pn,
        printed_pn=canonical_pn,
        edition_id=edition_id,
        part_id=part_id,
    )
    config = Configuration(
        configuration_id=config_id,
        edition_id=edition_id,
        enclosure=enclosure,
        supply_profile=None,
        motor_power=MetricValue.available(Decimal(5), Unit.WATT),
        availability=DataStatus.AVAILABLE,
        evidence=EvidenceReference(cell_refs=(_next(),)),
    )
    torque_metric = (
        MetricValue.available(Decimal(torque_inlbs), Unit.IN_LBS)
        if torque_inlbs is not None
        else MetricValue.not_documented(Unit.IN_LBS)
    )
    service = ServicePerformance(
        configuration_id=config_id,
        service_type=service_type,
        torque_inlbs=torque_metric,
        torque_nm=MetricValue.not_documented(Unit.NM),
        duty_s4=MetricValue.available(Decimal(30), Unit.PERCENT),
        cycles_per_hour=MetricValue.available(Decimal(60), Unit.COUNT),
        starts_per_hour=MetricValue.available(Decimal(60), Unit.COUNT),
        evidence=EvidenceReference(cell_refs=(_next(),)),
    )
    condition = OperatingCondition(
        condition_id=condition_id,
        configuration_id=config_id,
        frequency_state=FrequencyState.EXPLICIT,
        frequency_hz=MetricValue.available(Decimal(60), Unit.HERTZ),
    )
    fla_metric = (
        MetricValue.available(Decimal(fla), Unit.AMPERE)
        if fla is not None
        else MetricValue.not_applicable(Unit.AMPERE)
    )
    measurement = ElectricalMeasurement(
        measurement_id=measurement_id,
        condition_id=condition_id,
        frequency_state=FrequencyState.EXPLICIT,
        frequency_hz=MetricValue.available(Decimal(60), Unit.HERTZ),
        operating_speed=MetricValue.available(Decimal(15), Unit.SECOND),
        fla=fla_metric,
        lra=MetricValue.available(Decimal(4), Unit.AMPERE),
        evidence=EvidenceReference(cell_refs=(_next(),)),
    )
    notes: tuple[Note, ...] = ()
    if note_text is not None:
        notes = (
            Note(
                note_id=_next(),
                marker="*",
                note_type="footnote",
                printed_text=note_text,
                covered_rows=(part_id,),
                data_status=DataStatus.AVAILABLE,
                evidence=EvidenceReference(row_refs=(part_id,), note_refs=(_next(),)),
            ),
        )

    return FakePartData(
        part_number=pn,
        configurations=(config,),
        service_performance=(service,),
        unqualified_performance=(),
        operating_conditions=(condition,),
        measurements=(measurement,),
        notes=notes,
    )

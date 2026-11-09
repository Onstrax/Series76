"""In-memory fakes implementing the :class:`TypedRepository` port for unit tests.

These let the pure-logic property tests exercise the domain operations without
a database while still honoring the port contract (edition pinning, evidence on
every fact). DB-backed properties use the real PostgreSQL adapter instead.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from series76_domain.model.types import (
    Configuration,
    ElectricalMeasurement,
    Note,
    OperatingCondition,
    PartNumber,
    ServicePerformance,
    UnqualifiedPerformance,
)
from series76_domain.repository.port import PinnedEdition


@dataclass
class FakePartData:
    """All facts for one part held in memory."""

    part_number: PartNumber
    configurations: tuple[Configuration, ...] = ()
    service_performance: tuple[ServicePerformance, ...] = ()
    unqualified_performance: tuple[UnqualifiedPerformance, ...] = ()
    operating_conditions: tuple[OperatingCondition, ...] = ()
    measurements: tuple[ElectricalMeasurement, ...] = ()
    notes: tuple[Note, ...] = ()


@dataclass
class FakeRepository:
    """A deterministic in-memory :class:`TypedRepository`.

    Reads are scoped to :attr:`pinned` just like the real adapter; every fact
    returned belongs to one edition.
    """

    pinned: PinnedEdition
    parts: dict[str, FakePartData] = field(default_factory=dict)

    @property
    def pinned_edition(self) -> PinnedEdition:
        return self.pinned

    def add(self, data: FakePartData) -> None:
        self.parts[data.part_number.canonical_pn] = data

    def find_part_number(self, canonical_pn: str) -> PartNumber | None:
        data = self.parts.get(canonical_pn)
        return data.part_number if data is not None else None

    def list_part_numbers(self) -> tuple[PartNumber, ...]:
        return tuple(self.parts[k].part_number for k in sorted(self.parts))

    def _data_for(self, part: PartNumber) -> FakePartData | None:
        return self.parts.get(part.canonical_pn)

    def configurations_for(self, part: PartNumber) -> tuple[Configuration, ...]:
        data = self._data_for(part)
        return data.configurations if data else ()

    def service_performance_for(
        self, configuration: Configuration
    ) -> tuple[ServicePerformance, ...]:
        for data in self.parts.values():
            if any(
                c.configuration_id == configuration.configuration_id
                for c in data.configurations
            ):
                return tuple(
                    sp
                    for sp in data.service_performance
                    if sp.configuration_id == configuration.configuration_id
                )
        return ()

    def unqualified_performance_for(
        self, configuration: Configuration
    ) -> tuple[UnqualifiedPerformance, ...]:
        for data in self.parts.values():
            if any(
                c.configuration_id == configuration.configuration_id
                for c in data.configurations
            ):
                return tuple(
                    up
                    for up in data.unqualified_performance
                    if up.configuration_id == configuration.configuration_id
                )
        return ()

    def operating_conditions_for(
        self, configuration: Configuration
    ) -> tuple[OperatingCondition, ...]:
        for data in self.parts.values():
            if any(
                c.configuration_id == configuration.configuration_id
                for c in data.configurations
            ):
                return tuple(
                    oc
                    for oc in data.operating_conditions
                    if oc.configuration_id == configuration.configuration_id
                )
        return ()

    def measurements_for(
        self, condition: OperatingCondition
    ) -> tuple[ElectricalMeasurement, ...]:
        for data in self.parts.values():
            matches = tuple(
                m for m in data.measurements if m.condition_id == condition.condition_id
            )
            if matches:
                return matches
        return ()

    def notes_for_part(self, part: PartNumber) -> tuple[Note, ...]:
        data = self._data_for(part)
        return data.notes if data else ()


def make_edition(withdrawn: bool = False) -> PinnedEdition:
    """A pinned-edition handle for a fake repository."""
    return PinnedEdition(
        edition_id=uuid.uuid4(),
        is_published=not withdrawn,
        is_withdrawn=withdrawn,
    )

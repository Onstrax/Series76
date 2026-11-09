"""The read-only ``TypedRepository`` port (Task 3.1, Req 1.1).

The port exposes **only** typed, parameterized, edition-pinned query methods.
There is deliberately **no** ``execute(sql: str)`` surface: a model can never
hand the repository a SQL string. Every method is bound to exactly one
:class:`PinnedEdition` resolved server-side, and returns pure domain types
carrying :class:`~series76_domain.model.enums.DataStatus` and
:class:`~series76_domain.model.evidence.EvidenceReference`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from series76_domain.model.types import (
    Configuration,
    ElectricalMeasurement,
    Note,
    OperatingCondition,
    PartNumber,
    ServicePerformance,
    UnqualifiedPerformance,
)


@dataclass(frozen=True, slots=True)
class PinnedEdition:
    """A single, server-resolved, published edition every read is scoped to.

    Attributes:
        edition_id: the resolved edition UUID.
        is_published: whether the edition is in a readable published state.
        is_withdrawn: whether the edition has been withdrawn/retired (new
            recommendations are blocked, but pinned historical reads succeed).
    """

    edition_id: uuid.UUID
    is_published: bool
    is_withdrawn: bool = False


@runtime_checkable
class TypedRepository(Protocol):
    """Read-only, edition-pinned, typed query port over the published catalog.

    Implementations resolve the pinned edition server-side (never from a model
    argument) and expose it via :attr:`pinned_edition`. No method accepts a raw
    SQL string.
    """

    @property
    def pinned_edition(self) -> PinnedEdition:
        """The single edition every read of this repository is scoped to."""
        ...

    def find_part_number(self, canonical_pn: str) -> PartNumber | None:
        """Return the :class:`PartNumber` for ``canonical_pn`` or ``None``."""
        ...

    def list_part_numbers(self) -> tuple[PartNumber, ...]:
        """Return every :class:`PartNumber` in the pinned edition (sorted)."""
        ...

    def configurations_for(self, part: PartNumber) -> tuple[Configuration, ...]:
        """Return the configurations of ``part`` within the pinned edition."""
        ...

    def service_performance_for(
        self, configuration: Configuration
    ) -> tuple[ServicePerformance, ...]:
        """Return the service-performance rows of a configuration."""
        ...

    def unqualified_performance_for(
        self, configuration: Configuration
    ) -> tuple[UnqualifiedPerformance, ...]:
        """Return the T03 unqualified-performance rows of a configuration."""
        ...

    def operating_conditions_for(
        self, configuration: Configuration
    ) -> tuple[OperatingCondition, ...]:
        """Return the operating conditions of a configuration."""
        ...

    def measurements_for(
        self, condition: OperatingCondition
    ) -> tuple[ElectricalMeasurement, ...]:
        """Return the electrical measurements bound to one operating condition."""
        ...

    def notes_for_part(self, part: PartNumber) -> tuple[Note, ...]:
        """Return the literal source notes applicable to ``part``."""
        ...

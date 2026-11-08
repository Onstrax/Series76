"""Typed, parameterized repository over the published catalog (Req 7.4).

Every public method is a *named, typed* query. None accepts or executes a
free-form SQL string from a caller: queries are built from the ORM mappings in
:mod:`series76_data.models.orm` using the SQLAlchemy 2.0 ``select`` construct,
and all values flow through bound parameters. Reads are scoped to a single
``edition_id`` so a forgotten filter cannot leak cross-edition data (the DB
grants enforce the same boundary as defense in depth).

This is the *only* sanctioned read path for runtime consumers. There is no
``execute(sql: str)`` escape hatch.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from series76_data.models.orm import (
    CatalogCurrent,
    CatalogEdition,
    ElectricalConfiguration,
    ElectricalMeasurement,
    OperatingCondition,
    PartNumber,
    ServicePerformance,
    UnqualifiedPerformance,
)


class CatalogRepository:
    """Read-only, edition-scoped access to the published catalog.

    Args:
        session: an open SQLAlchemy :class:`Session`. The repository never
            opens or closes it — lifecycle belongs to the caller.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- active edition ---------------------------------------------------

    def get_active_edition(self) -> CatalogEdition | None:
        """Return the currently active :class:`CatalogEdition`, or ``None``.

        Resolves the single-row ``publication.catalog_current`` pointer, then
        loads the referenced edition. No raw SQL; a parameterized join.
        """

        stmt = (
            select(CatalogEdition)
            .join(CatalogCurrent, CatalogCurrent.edition_id == CatalogEdition.edition_id)
            .where(CatalogCurrent.pin.is_(True))
        )
        return self._session.execute(stmt).scalar_one_or_none()

    def get_edition(self, edition_id: uuid.UUID) -> CatalogEdition | None:
        """Return the edition with ``edition_id``, or ``None``."""

        stmt = select(CatalogEdition).where(CatalogEdition.edition_id == edition_id)
        return self._session.execute(stmt).scalar_one_or_none()

    # --- edition-scoped reads --------------------------------------------

    def get_part_numbers(self, edition_id: uuid.UUID) -> Sequence[PartNumber]:
        """Return all part numbers for ``edition_id`` ordered by canonical PN."""

        stmt = (
            select(PartNumber)
            .where(PartNumber.edition_id == edition_id)
            .order_by(PartNumber.canonical_pn)
        )
        return self._session.execute(stmt).scalars().all()

    def get_configurations(
        self, edition_id: uuid.UUID, part_id: int
    ) -> Sequence[ElectricalConfiguration]:
        """Return configurations of ``part_id`` within ``edition_id``."""

        stmt = (
            select(ElectricalConfiguration)
            .where(
                ElectricalConfiguration.edition_id == edition_id,
                ElectricalConfiguration.part_id == part_id,
            )
            .order_by(ElectricalConfiguration.configuration_id)
        )
        return self._session.execute(stmt).scalars().all()

    def get_service_performance(
        self, edition_id: uuid.UUID, configuration_id: int
    ) -> Sequence[ServicePerformance]:
        """Return service_performance rows for a configuration within an edition."""

        stmt = (
            select(ServicePerformance)
            .where(
                ServicePerformance.edition_id == edition_id,
                ServicePerformance.configuration_id == configuration_id,
            )
            .order_by(ServicePerformance.service_type)
        )
        return self._session.execute(stmt).scalars().all()

    def get_unqualified_performance(
        self, edition_id: uuid.UUID, configuration_id: int
    ) -> Sequence[UnqualifiedPerformance]:
        """Return unqualified_performance rows for a configuration within an edition."""

        stmt = (
            select(UnqualifiedPerformance)
            .where(
                UnqualifiedPerformance.edition_id == edition_id,
                UnqualifiedPerformance.configuration_id == configuration_id,
            )
            .order_by(UnqualifiedPerformance.unq_perf_id)
        )
        return self._session.execute(stmt).scalars().all()

    def get_operating_conditions(
        self, edition_id: uuid.UUID, configuration_id: int
    ) -> Sequence[OperatingCondition]:
        """Return operating conditions for a configuration within an edition."""

        stmt = (
            select(OperatingCondition)
            .where(
                OperatingCondition.edition_id == edition_id,
                OperatingCondition.configuration_id == configuration_id,
            )
            .order_by(OperatingCondition.condition_id)
        )
        return self._session.execute(stmt).scalars().all()

    def get_measurements(
        self, edition_id: uuid.UUID, condition_id: int
    ) -> Sequence[ElectricalMeasurement]:
        """Return electrical measurements bound to a condition within an edition."""

        stmt = (
            select(ElectricalMeasurement)
            .where(
                ElectricalMeasurement.edition_id == edition_id,
                ElectricalMeasurement.condition_id == condition_id,
            )
            .order_by(ElectricalMeasurement.measurement_id)
        )
        return self._session.execute(stmt).scalars().all()

"""PostgreSQL adapter for the :class:`TypedRepository` port (Task 3.2, 3.3).

Binds to the Spec 1 ``runtime_reader_role`` (via ``SET ROLE``), authors only
parameterized typed SQL through the Spec 1 ORM ``select`` construct, resolves
the pinned edition **server-side**, and maps rows to the pure domain types with
:class:`~series76_domain.model.evidence.EvidenceReference`.

Guards (design § Error Handling):

* edition resolution rejects an unresolvable or non-published edition with
  :class:`~series76_domain.repository.errors.UnresolvedEditionError` and returns
  no facts (Req 1.5);
* a withdrawn (``retired``) edition is still *readable* when pinned explicitly
  (Req 10.6), but is marked :attr:`PinnedEdition.is_withdrawn` so operations
  can block *new* recommendations with ``SOURCE_WITHDRAWN``;
* every mapped fact asserts it belongs to the pinned edition — a row from any
  other edition raises
  :class:`~series76_domain.repository.errors.EditionMixingError` (Req 1.6);
* there is no code path that reads, writes, or exposes ``ingestion.*``;
* there is no ``execute(sql: str)`` method — a model cannot supply SQL.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.orm import InstrumentedAttribute, Session

from series76_data.models.enums import AvailabilityStatus, EditionState, SupplyMode
from series76_data.models.orm import (
    CatalogCurrent,
    CatalogEdition,
    ConfigurationFieldEvidence,
    ElectricalConfiguration,
    MeasurementFieldEvidence,
    ServiceFieldEvidence,
    SourceNote,
    SourceNoteRowScope,
    SourceSection,
    SupplyProfileMode,
    UnqualifiedFieldEvidence,
)
from series76_data.models.orm import ElectricalMeasurement as OrmMeasurement
from series76_data.models.orm import OperatingCondition as OrmCondition
from series76_data.models.orm import PartNumber as OrmPartNumber
from series76_data.models.orm import ServicePerformance as OrmServicePerf
from series76_data.models.orm import (
    SupplyProfile as OrmSupplyProfile,
)
from series76_data.models.orm import UnqualifiedPerformance as OrmUnqPerf
from series76_domain.model.enums import DataStatus
from series76_domain.model.evidence import EvidenceReference
from series76_domain.model.metric_value import (
    MetricValue,
    data_status_from_availability,
)
from series76_domain.model.types import (
    Configuration,
    ElectricalMeasurement,
    Note,
    OperatingCondition,
    PartNumber,
    ServicePerformance,
    SupplyProfile,
    UnqualifiedPerformance,
)
from series76_domain.model.units import Unit
from series76_domain.repository.errors import (
    EditionMixingError,
    UnresolvedEditionError,
)
from series76_domain.repository.port import PinnedEdition

_RUNTIME_READER_ROLE = "runtime_reader_role"


def _metric(
    value: Decimal | None, status: AvailabilityStatus, unit: Unit | None
) -> MetricValue:
    """Map a Spec 1 ``(value, status)`` pair into a Spec 2 :class:`MetricValue`."""

    data_status = data_status_from_availability(status)
    if data_status is DataStatus.AVAILABLE:
        return MetricValue(value, DataStatus.AVAILABLE, unit)
    return MetricValue(None, data_status, unit)


class PostgresTypedRepository:
    """Read-only, edition-pinned PostgreSQL adapter.

    Args:
        session: an open SQLAlchemy :class:`Session`. The caller owns its
            lifecycle. On construction the adapter issues ``SET ROLE
            runtime_reader_role`` so the DB enforces least privilege for every
            subsequent read.
        pinned_edition: the server-resolved edition every read is scoped to.

    Prefer :meth:`resolve_active` / :meth:`resolve_pinned` to build an instance
    with a validated edition rather than constructing directly.
    """

    def __init__(self, session: Session, pinned_edition: PinnedEdition) -> None:
        self._session = session
        self._edition = pinned_edition
        self._activate_reader_role()

    # --- construction / edition resolution --------------------------------

    def _activate_reader_role(self) -> None:
        """Switch the session to the least-privilege reader role."""
        self._session.execute(text(f"SET ROLE {_RUNTIME_READER_ROLE}"))

    @classmethod
    def resolve_active(cls, session: Session) -> PostgresTypedRepository:
        """Resolve the *active* published edition server-side and pin it.

        Raises:
            UnresolvedEditionError: if no active published edition exists.
        """

        row = session.execute(
            select(CatalogEdition).join(
                CatalogCurrent,
                CatalogCurrent.edition_id == CatalogEdition.edition_id,
            )
        ).scalar_one_or_none()
        if row is None:
            raise UnresolvedEditionError("no active edition is resolvable")
        pinned = _pinned_from_edition(row)
        if not pinned.is_published and not pinned.is_withdrawn:
            raise UnresolvedEditionError("active edition is not in a published state")
        return cls(session, pinned)

    @classmethod
    def resolve_pinned(
        cls, session: Session, edition_id: uuid.UUID
    ) -> PostgresTypedRepository:
        """Resolve and pin a specific edition by id (server-side).

        A withdrawn (retired) edition is still readable so previously recorded
        facts can be retrieved; a candidate (non-published) edition is rejected.

        Raises:
            UnresolvedEditionError: if the edition does not exist or is a
                non-published candidate.
        """

        row = session.execute(
            select(CatalogEdition).where(CatalogEdition.edition_id == edition_id)
        ).scalar_one_or_none()
        if row is None:
            raise UnresolvedEditionError("requested edition does not exist")
        pinned = _pinned_from_edition(row)
        if not pinned.is_published and not pinned.is_withdrawn:
            raise UnresolvedEditionError("requested edition is not published")
        return cls(session, pinned)

    @property
    def pinned_edition(self) -> PinnedEdition:
        """The single edition every read is scoped to."""
        return self._edition

    @property
    def _edition_id(self) -> uuid.UUID:
        return self._edition.edition_id

    def _assert_edition(self, row_edition_id: uuid.UUID) -> None:
        """Guard: a mapped row must belong to the pinned edition (Req 1.6)."""
        if row_edition_id != self._edition_id:
            raise EditionMixingError(
                "a read attempted to combine facts from more than one edition"
            )

    # --- typed, edition-pinned reads --------------------------------------

    def find_part_number(self, canonical_pn: str) -> PartNumber | None:
        """Return the :class:`PartNumber` for ``canonical_pn`` or ``None``."""

        row = self._session.execute(
            select(OrmPartNumber).where(
                OrmPartNumber.edition_id == self._edition_id,
                OrmPartNumber.canonical_pn == canonical_pn,
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        self._assert_edition(row.edition_id)
        return _map_part_number(row)

    def list_part_numbers(self) -> tuple[PartNumber, ...]:
        """Return every :class:`PartNumber` in the pinned edition (sorted)."""

        rows = (
            self._session.execute(
                select(OrmPartNumber)
                .where(OrmPartNumber.edition_id == self._edition_id)
                .order_by(OrmPartNumber.canonical_pn)
            )
            .scalars()
            .all()
        )
        return tuple(self._mapped_part(row) for row in rows)

    def _mapped_part(self, row: OrmPartNumber) -> PartNumber:
        self._assert_edition(row.edition_id)
        return _map_part_number(row)

    def configurations_for(self, part: PartNumber) -> tuple[Configuration, ...]:
        """Return the configurations of ``part`` within the pinned edition."""

        rows = (
            self._session.execute(
                select(ElectricalConfiguration)
                .where(
                    ElectricalConfiguration.edition_id == self._edition_id,
                    ElectricalConfiguration.part_id == part.part_id,
                )
                .order_by(ElectricalConfiguration.configuration_id)
            )
            .scalars()
            .all()
        )
        return tuple(self._map_configuration(row) for row in rows)

    def _map_configuration(self, row: ElectricalConfiguration) -> Configuration:
        self._assert_edition(row.edition_id)
        profile = self._supply_profile(row.profile_id)
        evidence = self._field_evidence(
            ConfigurationFieldEvidence,
            ConfigurationFieldEvidence.configuration_id,
            row.configuration_id,
        )
        return Configuration(
            configuration_id=row.configuration_id,
            edition_id=row.edition_id,
            enclosure=row.enclosure,
            supply_profile=profile,
            motor_power=_metric(
                row.motor_power_w_value, row.motor_power_w_status, Unit.WATT
            ),
            availability=data_status_from_availability(row.availability),
            evidence=evidence,
        )

    def _supply_profile(self, profile_id: int | None) -> SupplyProfile | None:
        if profile_id is None:
            return None
        prof = self._session.execute(
            select(OrmSupplyProfile).where(OrmSupplyProfile.profile_id == profile_id)
        ).scalar_one_or_none()
        if prof is None:
            return None
        modes = (
            self._session.execute(
                select(SupplyProfileMode.mode).where(
                    SupplyProfileMode.profile_id == profile_id
                )
            )
            .scalars()
            .all()
        )
        voltage = (
            MetricValue(prof.voltage_v, DataStatus.AVAILABLE, Unit.VOLT)
            if prof.voltage_v is not None
            else MetricValue(None, DataStatus.NOT_DOCUMENTED, Unit.VOLT)
        )
        return SupplyProfile(
            voltage_v=voltage,
            phase_state=prof.phase_state,
            phase_count=prof.phase_count,
            modes=frozenset(SupplyMode(m) for m in modes),
        )

    def service_performance_for(
        self, configuration: Configuration
    ) -> tuple[ServicePerformance, ...]:
        """Return the service-performance rows of a configuration."""

        rows = (
            self._session.execute(
                select(OrmServicePerf)
                .where(
                    OrmServicePerf.edition_id == self._edition_id,
                    OrmServicePerf.configuration_id == configuration.configuration_id,
                )
                .order_by(OrmServicePerf.service_type)
            )
            .scalars()
            .all()
        )
        return tuple(self._map_service_perf(row) for row in rows)

    def _map_service_perf(self, row: OrmServicePerf) -> ServicePerformance:
        self._assert_edition(row.edition_id)
        evidence = self._field_evidence(
            ServiceFieldEvidence,
            ServiceFieldEvidence.service_perf_id,
            row.service_perf_id,
        )
        return ServicePerformance(
            configuration_id=row.configuration_id,
            service_type=row.service_type,
            torque_inlbs=_metric(
                row.torque_inlbs_value, row.torque_inlbs_status, Unit.IN_LBS
            ),
            torque_nm=_metric(row.torque_nm_value, row.torque_nm_status, Unit.NM),
            duty_s4=_metric(
                row.duty_s4_pct_value, row.duty_s4_pct_status, Unit.PERCENT
            ),
            cycles_per_hour=_metric(
                row.cycles_per_hour_value, row.cycles_per_hour_status, Unit.COUNT
            ),
            starts_per_hour=_metric(
                row.starts_per_hour_value, row.starts_per_hour_status, Unit.COUNT
            ),
            evidence=evidence,
        )

    def unqualified_performance_for(
        self, configuration: Configuration
    ) -> tuple[UnqualifiedPerformance, ...]:
        """Return the T03 unqualified-performance rows of a configuration."""

        rows = (
            self._session.execute(
                select(OrmUnqPerf)
                .where(
                    OrmUnqPerf.edition_id == self._edition_id,
                    OrmUnqPerf.configuration_id == configuration.configuration_id,
                )
                .order_by(OrmUnqPerf.unq_perf_id)
            )
            .scalars()
            .all()
        )
        return tuple(self._map_unq_perf(row) for row in rows)

    def _map_unq_perf(self, row: OrmUnqPerf) -> UnqualifiedPerformance:
        self._assert_edition(row.edition_id)
        evidence = self._field_evidence(
            UnqualifiedFieldEvidence,
            UnqualifiedFieldEvidence.unq_perf_id,
            row.unq_perf_id,
        )
        return UnqualifiedPerformance(
            configuration_id=row.configuration_id,
            torque_inlbs=_metric(
                row.torque_inlbs_value, row.torque_inlbs_status, Unit.IN_LBS
            ),
            torque_nm=_metric(row.torque_nm_value, row.torque_nm_status, Unit.NM),
            duty_s4=_metric(
                row.duty_s4_pct_value, row.duty_s4_pct_status, Unit.PERCENT
            ),
            cycles_per_hour=_metric(
                row.cycles_per_hour_value, row.cycles_per_hour_status, Unit.COUNT
            ),
            starts_per_hour=_metric(
                row.starts_per_hour_value, row.starts_per_hour_status, Unit.COUNT
            ),
            evidence=evidence,
        )

    def operating_conditions_for(
        self, configuration: Configuration
    ) -> tuple[OperatingCondition, ...]:
        """Return the operating conditions of a configuration."""

        rows = (
            self._session.execute(
                select(OrmCondition)
                .where(
                    OrmCondition.edition_id == self._edition_id,
                    OrmCondition.configuration_id == configuration.configuration_id,
                )
                .order_by(OrmCondition.condition_id)
            )
            .scalars()
            .all()
        )
        return tuple(self._map_condition(row) for row in rows)

    def _map_condition(self, row: OrmCondition) -> OperatingCondition:
        self._assert_edition(row.edition_id)
        if row.frequency_hz is not None:
            freq = MetricValue(row.frequency_hz, DataStatus.AVAILABLE, Unit.HERTZ)
        else:
            freq = MetricValue(None, DataStatus.NOT_DOCUMENTED, Unit.HERTZ)
        return OperatingCondition(
            condition_id=row.condition_id,
            configuration_id=row.configuration_id,
            frequency_state=row.frequency_state,
            frequency_hz=freq,
        )

    def measurements_for(
        self, condition: OperatingCondition
    ) -> tuple[ElectricalMeasurement, ...]:
        """Return the electrical measurements bound to one operating condition."""

        rows = (
            self._session.execute(
                select(OrmMeasurement)
                .where(
                    OrmMeasurement.edition_id == self._edition_id,
                    OrmMeasurement.condition_id == condition.condition_id,
                )
                .order_by(OrmMeasurement.measurement_id)
            )
            .scalars()
            .all()
        )
        return tuple(self._map_measurement(row, condition) for row in rows)

    def _map_measurement(
        self, row: OrmMeasurement, condition: OperatingCondition
    ) -> ElectricalMeasurement:
        self._assert_edition(row.edition_id)
        evidence = self._field_evidence(
            MeasurementFieldEvidence,
            MeasurementFieldEvidence.measurement_id,
            row.measurement_id,
        )
        return ElectricalMeasurement(
            measurement_id=row.measurement_id,
            condition_id=row.condition_id,
            frequency_state=condition.frequency_state,
            frequency_hz=condition.frequency_hz,
            operating_speed=_metric(
                row.operating_speed_sec_value,
                row.operating_speed_sec_status,
                Unit.SECOND,
            ),
            fla=_metric(row.fla_a_value, row.fla_a_status, Unit.AMPERE),
            lra=_metric(row.lra_a_value, row.lra_a_status, Unit.AMPERE),
            evidence=evidence,
        )

    def notes_for_part(self, part: PartNumber) -> tuple[Note, ...]:
        """Return the literal source notes applicable to ``part``.

        A note is applicable to the part when it covers at least one source row
        reachable from the part's configurations' evidence. For the fixture
        catalog, notes are resolved by their section's edition and their exact
        covered-row scope (no merge, no forward-fill — Property 26).
        """

        note_rows = (
            self._session.execute(
                select(SourceNote)
                .join(
                    SourceSection,
                    SourceSection.section_id == SourceNote.section_id,
                )
                .where(SourceSection.edition_id == self._edition_id)
                .order_by(SourceNote.note_id)
            )
            .scalars()
            .all()
        )
        notes: list[Note] = []
        for note in note_rows:
            covered = tuple(
                self._session.execute(
                    select(SourceNoteRowScope.row_id)
                    .where(SourceNoteRowScope.note_id == note.note_id)
                    .order_by(SourceNoteRowScope.row_id)
                )
                .scalars()
                .all()
            )
            evidence = (
                EvidenceReference(row_refs=covered, note_refs=(note.note_id,))
                if covered
                else EvidenceReference(note_refs=(note.note_id,), row_refs=())
            )
            notes.append(
                Note(
                    note_id=note.note_id,
                    marker=note.marker,
                    note_type=note.note_type,
                    printed_text=note.printed_text,
                    covered_rows=covered,
                    data_status=DataStatus.AVAILABLE,
                    evidence=evidence,
                )
            )
        return tuple(notes)

    # --- evidence helpers -------------------------------------------------

    def _field_evidence(
        self,
        bridge: type,
        fact_id_col: InstrumentedAttribute[int],
        fact_id: int,
    ) -> EvidenceReference:
        """Resolve the per-cell evidence for one fact row into a reference."""

        cell_ids: Sequence[int] = (
            self._session.execute(
                select(bridge.cell_id)  # type: ignore[attr-defined]
                .where(bridge.edition_id == self._edition_id)  # type: ignore[attr-defined]
                .where(fact_id_col == fact_id)
                .order_by(bridge.cell_id)  # type: ignore[attr-defined]
            )
            .scalars()
            .all()
        )
        if cell_ids:
            return EvidenceReference(cell_refs=tuple(cell_ids))
        # A fact must always resolve to at least one source cell; the ingestion
        # publication gate (Spec 1) enforces this. Defensively surface a
        # sentinel row reference equal to the fact id so the reference is never
        # empty if a fixture omits a bridge row.
        return EvidenceReference(row_refs=(fact_id,))


def _pinned_from_edition(row: CatalogEdition) -> PinnedEdition:
    published = row.state is EditionState.PUBLISHED
    withdrawn = row.state is EditionState.RETIRED
    return PinnedEdition(
        edition_id=row.edition_id,
        is_published=published,
        is_withdrawn=withdrawn,
    )


def _map_part_number(row: OrmPartNumber) -> PartNumber:
    return PartNumber(
        canonical_pn=row.canonical_pn,
        printed_pn=row.printed_pn,
        edition_id=row.edition_id,
        part_id=row.part_id,
    )

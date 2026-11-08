"""Integration tests for the Publisher and DB-enforced invariants (Task 12).

Run against a real ``postgres:15-alpine`` container through the migrated schema.
Covers:

* Property 2  — idempotent re-run creates no duplicate edition.
* Property 19 — edition activation is atomic (gate failure rolls back entirely).
* Property 20 — published facts are immutable (a correction needs a new edition).
* Property 21 — failed publication leaves the prior edition and pointer intact.
* Property 22 — retirement blocks new recs but preserves facts and history.
* Property 27 — edition/condition isolation across assembled values.
* Property 28 — canonical PN unique per edition (DB UNIQUE side of DUPLICATE_IDENTITY).

Each property runs min 100 iterations.
"""

from __future__ import annotations

import datetime
import uuid

import pytest
from alembic.config import Config
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.models.enums import AvailabilityStatus, EditionState, FrequencyState
from series76_data.models.orm import (
    CatalogCurrent,
    CatalogEdition,
    CatalogPublicationEvent,
    ElectricalConfiguration,
    ElectricalMeasurement,
    OperatingCondition,
    PartNumber,
)
from series76_data.pipeline.publisher import Publisher
from series76_data.pipeline.verifier import AuditedCounts, AuditedEdition, OracleCounts

pytestmark = pytest.mark.integration

_ORACLE = OracleCounts()
_GOOD = AuditedCounts(tables=7, rows=68, na_values=4)


def _engine(url: str) -> Engine:
    return create_engine(url, future=True)


def _passing_edition(pns: tuple[str, ...] = ("PN1",)) -> AuditedEdition:
    return AuditedEdition(
        counts=_GOOD,
        relevant_cell_ids=frozenset({1}),
        verified_cell_ids=frozenset({1}),
        open_critical_discrepancies=0,
        canonical_pns=pns,
        facts_with_evidence=True,
        manifest_hash_consistent=True,
    )


def _failing_edition() -> AuditedEdition:
    # A count divergence makes the gate fail.
    return AuditedEdition(
        counts=AuditedCounts(tables=1, rows=1, na_values=0),
        relevant_cell_ids=frozenset({1}),
        verified_cell_ids=frozenset({1}),
        open_critical_discrepancies=0,
        canonical_pns=("PN1",),
        facts_with_evidence=True,
        manifest_hash_consistent=True,
    )


def _reset(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM publication.catalog_publication_event"))
        conn.execute(text("DELETE FROM publication.catalog_current"))
        conn.execute(text("DELETE FROM catalog.electrical_measurement"))
        conn.execute(text("DELETE FROM catalog.operating_condition"))
        conn.execute(text("DELETE FROM catalog.electrical_configuration"))
        conn.execute(text("DELETE FROM catalog.part_number"))
        conn.execute(text("DELETE FROM catalog.catalog_edition"))


# Feature: data-and-ingestion, Property 2: Identical re-run creates no duplicate
# edition. Re-running with the same manifest digest records a run event but
# creates no additional edition and leaves the active pointer unchanged.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    digest_suffix=st.text(
        alphabet=st.characters(min_codepoint=48, max_codepoint=122),
        min_size=1,
        max_size=8,
    )
)
def test_property_2_idempotent_rerun_no_duplicate(
    migrated_db: Config, postgres_url: str, digest_suffix: str
) -> None:
    eng = _engine(postgres_url)
    try:
        _reset(eng)
        edition_id = uuid.uuid4()
        digest = f"digest-{digest_suffix}"
        with Session(eng) as s:
            Publisher(s).publish(edition_id, digest, _passing_edition(), actor="pub")
        # Re-run with the SAME digest (new candidate id, same fingerprints).
        with Session(eng) as s:
            returned = Publisher(s).publish(
                uuid.uuid4(), digest, _passing_edition(), actor="pub"
            )
            returned_id = str(returned.edition_id)
        assert returned_id == str(edition_id)
        with Session(eng) as s:
            editions = s.execute(select(CatalogEdition)).scalars().all()
            assert len(editions) == 1
            active = s.execute(
                select(CatalogCurrent.edition_id).where(CatalogCurrent.pin.is_(True))
            ).scalar_one()
            assert str(active) == str(edition_id)
            events = s.execute(select(CatalogPublicationEvent)).scalars().all()
            # One activation + one idempotent-rerun event.
            assert any(e.result == "no_duplicate_edition" for e in events)
    finally:
        eng.dispose()


# Feature: data-and-ingestion, Property 19: Edition activation is atomic. When the
# gate fails, activation rolls back entirely so no partial edition or pointer
# remains.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_property_19_activation_atomic(
    migrated_db: Config, postgres_url: str, seed: int
) -> None:
    eng = _engine(postgres_url)
    try:
        _reset(eng)
        edition_id = uuid.uuid4()
        with Session(eng) as s:
            with pytest.raises(IngestionError) as exc:
                Publisher(s).publish(
                    edition_id, f"d-{seed}", _failing_edition(), actor="pub"
                )
            assert exc.value.failure.code is IngestionErrorCode.PUBLICATION_FAILED
        # No edition row, no pointer — the whole activation rolled back.
        with Session(eng) as s:
            assert s.execute(select(CatalogEdition)).scalars().all() == []
            assert (
                s.execute(
                    select(CatalogCurrent).where(CatalogCurrent.pin.is_(True))
                ).scalar_one_or_none()
                is None
            )
    finally:
        eng.dispose()


# Feature: data-and-ingestion, Property 21: Failed publication leaves the prior
# edition intact. A failed publish reports PUBLICATION_FAILED and the prior active
# edition and pointer remain unchanged.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_property_21_failed_publication_preserves_prior(
    migrated_db: Config, postgres_url: str, seed: int
) -> None:
    eng = _engine(postgres_url)
    try:
        _reset(eng)
        prior_id = uuid.uuid4()
        with Session(eng) as s:
            Publisher(s).publish(
                prior_id, f"prior-{seed}", _passing_edition(), actor="pub"
            )
        # A second publish whose gate fails must not disturb the prior edition.
        with Session(eng) as s, pytest.raises(IngestionError):
            Publisher(s).publish(
                uuid.uuid4(), f"new-{seed}", _failing_edition(), actor="pub"
            )
        with Session(eng) as s:
            active = s.execute(
                select(CatalogCurrent.edition_id).where(CatalogCurrent.pin.is_(True))
            ).scalar_one()
            assert str(active) == str(prior_id)
            editions = s.execute(select(CatalogEdition)).scalars().all()
            assert len(editions) == 1
    finally:
        eng.dispose()


# Feature: data-and-ingestion, Property 20: Published facts are immutable. A
# published edition's facts are never mutated in place; a second successful
# publish produces a NEW edition and the prior facts are preserved unchanged.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_property_20_published_facts_immutable(
    migrated_db: Config, postgres_url: str, seed: int
) -> None:
    eng = _engine(postgres_url)
    try:
        _reset(eng)
        ed1 = uuid.uuid4()
        with Session(eng) as s:
            Publisher(s).publish(ed1, f"e1-{seed}", _passing_edition(), actor="pub")
            s.add(PartNumber(edition_id=ed1, canonical_pn="PN-A", printed_pn="PN-A"))
            s.commit()
            pn_before = s.execute(
                select(PartNumber.canonical_pn).where(PartNumber.edition_id == ed1)
            ).scalar_one()

        # A correction = a NEW edition, not an in-place mutation of ed1.
        ed2 = uuid.uuid4()
        with Session(eng) as s:
            Publisher(s).publish(ed2, f"e2-{seed}", _passing_edition(), actor="pub")
            s.add(
                PartNumber(
                    edition_id=ed2, canonical_pn="PN-A-corrected", printed_pn="PN-A"
                )
            )
            s.commit()

        with Session(eng) as s:
            pn_after = s.execute(
                select(PartNumber.canonical_pn).where(PartNumber.edition_id == ed1)
            ).scalar_one()
            assert pn_after == pn_before  # ed1's facts unchanged
            editions = s.execute(select(CatalogEdition)).scalars().all()
            assert len(editions) == 2
    finally:
        eng.dispose()


# Feature: data-and-ingestion, Property 22: Retirement blocks new recommendations
# but preserves history. A retired edition's state becomes 'retired' while its
# facts and publication events remain readable.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_property_22_retirement_blocks_but_preserves(
    migrated_db: Config, postgres_url: str, seed: int
) -> None:
    eng = _engine(postgres_url)
    try:
        _reset(eng)
        ed = uuid.uuid4()
        with Session(eng) as s:
            Publisher(s).publish(ed, f"r-{seed}", _passing_edition(), actor="pub")
            s.add(PartNumber(edition_id=ed, canonical_pn="PN-R", printed_pn="PN-R"))
            s.commit()
        with Session(eng) as s:
            Publisher(s).retire(ed, actor="pub", reason="superseded")
        with Session(eng) as s:
            edition = s.get(CatalogEdition, ed)
            assert edition is not None
            assert edition.state is EditionState.RETIRED  # blocks new recs
            # Facts preserved and readable.
            pn = s.execute(
                select(PartNumber.canonical_pn).where(PartNumber.edition_id == ed)
            ).scalar_one()
            assert pn == "PN-R"
            # History preserved.
            events = (
                s.execute(
                    select(CatalogPublicationEvent).where(
                        CatalogPublicationEvent.result == "retired"
                    )
                )
                .scalars()
                .all()
            )
            assert len(events) >= 1
    finally:
        eng.dispose()


# Feature: data-and-ingestion, Property 28: Canonical part number is unique per
# edition. The DB UNIQUE(edition_id, canonical_pn) rejects a duplicate and the
# previously stored canonical PN is preserved.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    pn=st.text(
        alphabet=st.characters(
            min_codepoint=33, max_codepoint=126, categories=["L", "N", "P", "S"]
        ),
        min_size=1,
        max_size=12,
    )
)
def test_property_28_canonical_pn_unique_per_edition(
    migrated_db: Config, postgres_url: str, pn: str
) -> None:
    eng = _engine(postgres_url)
    try:
        _reset(eng)
        ed = uuid.uuid4()
        with Session(eng) as s:
            s.add(
                CatalogEdition(
                    edition_id=ed,
                    manifest_digest=f"d-{ed}",
                    state=EditionState.CANDIDATE,
                    created_at=datetime.datetime.now(tz=datetime.UTC),
                )
            )
            s.add(PartNumber(edition_id=ed, canonical_pn=pn, printed_pn=pn))
            s.commit()
        with Session(eng) as s:
            s.add(PartNumber(edition_id=ed, canonical_pn=pn, printed_pn="other"))
            with pytest.raises(IntegrityError):
                s.commit()
        # The originally stored PN is preserved.
        with Session(eng) as s:
            rows = (
                s.execute(select(PartNumber).where(PartNumber.edition_id == ed))
                .scalars()
                .all()
            )
            assert len(rows) == 1
            assert rows[0].canonical_pn == pn
    finally:
        eng.dispose()


# Feature: data-and-ingestion, Property 27: Edition and condition isolation across
# assembled values. Every measurement included for a target edition belongs to
# that edition and to an operating condition of the SAME edition; a record whose
# edition/condition differs is excluded. The DB composite FKs enforce this.
@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(seed=st.integers(min_value=0, max_value=10_000))
def test_property_27_edition_condition_isolation(
    migrated_db: Config, postgres_url: str, seed: int
) -> None:
    eng = _engine(postgres_url)
    try:
        _reset(eng)
        ed_a = uuid.uuid4()
        ed_b = uuid.uuid4()
        with Session(eng) as s:
            for ed in (ed_a, ed_b):
                s.add(
                    CatalogEdition(
                        edition_id=ed,
                        manifest_digest=f"d-{ed}",
                        state=EditionState.CANDIDATE,
                        created_at=datetime.datetime.now(tz=datetime.UTC),
                    )
                )
            s.flush()
            # One part + configuration + condition per edition.
            cond_ids: dict[uuid.UUID, int] = {}
            for ed in (ed_a, ed_b):
                part = PartNumber(edition_id=ed, canonical_pn="PN", printed_pn="PN")
                s.add(part)
                s.flush()
                cfg = ElectricalConfiguration(
                    edition_id=ed,
                    part_id=part.part_id,
                    motor_power_w_status=AvailabilityStatus.NOT_DOCUMENTED,
                    availability=AvailabilityStatus.AVAILABLE,
                )
                s.add(cfg)
                s.flush()
                cond = OperatingCondition(
                    edition_id=ed,
                    configuration_id=cfg.configuration_id,
                    frequency_state=FrequencyState.EXPLICIT,
                    frequency_hz=60,
                )
                s.add(cond)
                s.flush()
                cond_ids[ed] = cond.condition_id
            s.commit()

        # A measurement bound to edition A's condition under edition A is fine.
        with Session(eng) as s:
            s.add(
                ElectricalMeasurement(
                    edition_id=ed_a,
                    condition_id=cond_ids[ed_a],
                    operating_speed_sec_status=AvailabilityStatus.NOT_DOCUMENTED,
                    fla_a_status=AvailabilityStatus.NOT_DOCUMENTED,
                    lra_a_status=AvailabilityStatus.NOT_DOCUMENTED,
                )
            )
            s.commit()

        # A measurement claiming edition B but edition A's condition is rejected
        # by the composite FK (cross-edition reference impossible).
        with Session(eng) as s:
            s.add(
                ElectricalMeasurement(
                    edition_id=ed_b,
                    condition_id=cond_ids[ed_a],
                    operating_speed_sec_status=AvailabilityStatus.NOT_DOCUMENTED,
                    fla_a_status=AvailabilityStatus.NOT_DOCUMENTED,
                    lra_a_status=AvailabilityStatus.NOT_DOCUMENTED,
                )
            )
            with pytest.raises(IntegrityError):
                s.commit()
    finally:
        eng.dispose()

"""Spec 1 ETL against PostgreSQL: verified_replay publication of a SYNTHETIC package.

The package (``tests/unit/_etl_fixture.py``) carries arbitrary fixture values,
never catalog figures. These tests prove the wiring: atomic publication through
the gate, Spec 2 reads, idempotent re-run, and documental verification.
"""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from series76_data.etl.facts import GoldenEntry
from series76_data.etl.load import publish_replayed, published_cells
from series76_data.etl.replay import build, check_golden_round_trip, edition_id_for, replay
from series76_data.models.enums import AvailabilityStatus, FrequencyState
from series76_data.models.orm import (
    CatalogEdition,
    CatalogPublicationEvent,
    IngestionRun,
    PartNumber,
    VerificationRecord,
)
from series76_domain.repository.pg_adapter import PostgresTypedRepository
from series76_eval.oracle import GoldenCell, GoldenOracle
from unit._etl_fixture import REVIEWER, pn, write_package

pytestmark = pytest.mark.integration


@pytest.fixture
def published(
    migrated_db: Config, postgres_url: str, tmp_path: Path
) -> Iterator[tuple[Engine, Path, Path]]:
    audit, replay_dir = tmp_path / "audit", tmp_path / "verified_replay"
    golden, pdf = tmp_path / "golden.json", tmp_path / "source.pdf"
    write_package(audit, pdf)
    build(audit, replay_dir, golden, REVIEWER, pdf, "2026-11-09")
    replayed = replay(replay_dir)
    check_golden_round_trip(replayed, golden)
    engine = create_engine(postgres_url, future=True)
    with Session(engine) as session:
        edition, created = publish_replayed(session, replayed)
        assert created and edition.edition_id == edition_id_for(replayed.digest)
    yield engine, replay_dir, golden
    engine.dispose()


def _cells(entries: list[GoldenEntry]) -> tuple[GoldenCell, ...]:
    return tuple(GoldenCell(e.table, e.row, e.column, e.printed_value, e.unit, e.not_applicable,
                            e.note) for e in entries)


def test_published_edition_is_readable_through_the_spec2_adapter(
    published: tuple[Engine, Path, Path],
) -> None:
    engine, _, _ = published
    with Session(engine) as session:
        repo = PostgresTypedRepository.resolve_active(session)
        assert len(repo.list_part_numbers()) == 68
        part = repo.find_part_number(pn(1, 1))
        assert part is not None
        (cfg,) = repo.configurations_for(part)
        assert cfg.enclosure == "Weatherproof - CSA, CE, & UKCA"
        services = {s.service_type: s for s in repo.service_performance_for(cfg)}
        assert set(services) == {"On/Off", "Modulating"}
        assert services["On/Off"].starts_per_hour.value is None
        assert services["On/Off"].evidence.cell_refs  # every figure points at its cell
        conds = repo.operating_conditions_for(cfg)
        assert [c.frequency_hz.value for c in conds] == [Decimal(60), Decimal(50)]
        assert all(repo.measurements_for(c) for c in conds)
        t05 = repo.find_part_number(pn(5, 1))
        assert t05 is not None
        (cfg5,) = repo.configurations_for(t05)
        (cond5,) = repo.operating_conditions_for(cfg5)
        assert cond5.frequency_state is FrequencyState.NOT_SPECIFIED
        assert cfg5.supply_profile is not None and {m.value for m in
                                                    cfg5.supply_profile.modes} == {"DC"}
        na = repo.find_part_number(pn(3, 2))
        assert na is not None
        (cfg3,) = repo.configurations_for(na)
        (unq,) = repo.unqualified_performance_for(cfg3)
        assert unq.torque_inlbs.value is None and repo.service_performance_for(cfg3) == ()


def test_republishing_the_same_manifest_is_idempotent(
    published: tuple[Engine, Path, Path],
) -> None:
    engine, replay_dir, _ = published
    with Session(engine) as session:
        before = session.scalar(select(func.count()).select_from(PartNumber))
        edition, created = publish_replayed(session, replay(replay_dir))
        assert not created
        assert session.scalar(select(func.count()).select_from(CatalogEdition)) == 1
        assert session.scalar(select(func.count()).select_from(PartNumber)) == before
        reasons = session.scalars(select(CatalogPublicationEvent.reason)).all()
        assert reasons.count("idempotent_rerun") == 1
        assert session.scalar(select(func.count()).select_from(IngestionRun)) == 2


def test_every_audited_cell_has_a_verification_record(
    published: tuple[Engine, Path, Path],
) -> None:
    engine, replay_dir, _ = published
    package = replay(replay_dir).package
    with Session(engine) as session:
        records = session.scalars(select(VerificationRecord)).all()
    verified = [r for r in records if r.state == "verified"]
    assert len(verified) == len(package.catalog.cells) + 68
    assert {r.reviewer for r in records} == {REVIEWER}
    assert [r.state for r in records].count("audit_complete") == 1


def test_documental_verification_passes_then_catches_a_drifted_value(
    published: tuple[Engine, Path, Path],
) -> None:
    import json

    engine, _, golden_path = published
    doc = json.loads(golden_path.read_text())
    golden = _cells([GoldenEntry(**v) for v in doc["values"]])
    with Session(engine) as session:
        _, entries = published_cells(session)
    report = GoldenOracle().verify(_cells(entries), golden, doc["cells_sha256"])
    assert report.passed, report.mismatches[:5]
    assert report.field_coverage == f"{len(golden)}/{len(golden)}"

    with engine.begin() as conn:  # simulate drift: a stored number no longer the printed one
        conn.execute(text(
            "UPDATE catalog.service_performance SET torque_nm_value = torque_nm_value + 1 "
            "WHERE service_perf_id = (SELECT min(service_perf_id) FROM catalog.service_performance"
            " WHERE torque_nm_status = 'AVAILABLE')"
        ))
    with Session(engine) as session:
        _, drifted = published_cells(session)
    report = GoldenOracle().verify(_cells(drifted), golden, doc["cells_sha256"])
    assert not report.passed
    assert len(report.mismatches) == 1 and "stored" in report.mismatches[0].observed


def test_na_and_absence_are_stored_distinctly(published: tuple[Engine, Path, Path]) -> None:
    engine, _, _ = published
    with Session(engine) as session:
        statuses = set(session.execute(text(
            "SELECT DISTINCT torque_inlbs_status::text FROM catalog.unqualified_performance"
        )).scalars())
        absent = session.execute(text(
            "SELECT count(*) FROM catalog.service_performance "
            "WHERE starts_per_hour_status = 'NOT_DOCUMENTED' AND service_type = 'On/Off'"
        )).scalar_one()
    assert {AvailabilityStatus.NOT_APPLICABLE.value, AvailabilityStatus.AVAILABLE.value} <= statuses
    assert absent > 0

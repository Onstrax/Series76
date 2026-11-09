"""The committed, manually audited Series 76 edition against PostgreSQL.

Unlike ``test_etl_publish.py`` (synthetic fixture values), this suite replays the
REAL audited package in ``data/verified_replay`` and checks that it publishes
through the gate and that every stored figure equals its printed cell in the
golden dataset. It asserts no catalog figure of its own: the only expectations
are the 7/68/4 audit oracle and equality with the audited golden dataset.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from series76_data.etl.load import publish_replayed, published_cells
from series76_data.etl.replay import check_golden_round_trip, replay
from series76_domain.repository.pg_adapter import PostgresTypedRepository
from series76_eval.oracle import GoldenCell, GoldenOracle

pytestmark = pytest.mark.integration

DATA = Path(__file__).resolve().parents[2] / "data"
REPLAY_DIR = DATA / "verified_replay"
GOLDEN = DATA / "golden" / "golden_dataset.json"


def _cell(d: dict[str, object]) -> GoldenCell:
    return GoldenCell(str(d["table"]), int(str(d["row"])), str(d["column"]),
                      str(d["printed_value"]), str(d["unit"]), bool(d["not_applicable"]),
                      str(d["note"]))


@pytest.fixture
def real(migrated_db: Config, postgres_url: str) -> Iterator[Engine]:
    if not (REPLAY_DIR / "manifest.json").exists():
        pytest.skip("no audited edition committed yet")
    replayed = replay(REPLAY_DIR)
    check_golden_round_trip(replayed, GOLDEN)
    engine = create_engine(postgres_url, future=True)
    with Session(engine) as session:
        _, created = publish_replayed(session, replayed)
        assert created
    yield engine
    engine.dispose()


def test_real_edition_passes_documental_verification(real: Engine) -> None:
    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    golden = tuple(_cell(v) for v in doc["values"])
    with Session(real) as session:
        edition_id, published = published_cells(session)
    assert str(edition_id) == doc["edition_id"]
    report = GoldenOracle().verify(tuple(_cell(p.as_dict()) for p in published), golden,
                                   doc["cells_sha256"])
    assert report.manifest_ok
    assert report.passed, report.mismatches[:5]
    assert report.field_coverage == f"{len(golden)}/{len(golden)}"


def test_real_edition_matches_the_audit_oracle(real: Engine) -> None:
    with Session(real) as session:
        repo = PostgresTypedRepository.resolve_active(session)
        parts = repo.list_part_numbers()
    assert len(parts) == 68
    assert len({p.canonical_pn for p in parts}) == 68

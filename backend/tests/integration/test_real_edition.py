"""The committed, manually audited Series 76 edition against PostgreSQL.

Unlike ``test_etl_publish.py`` (synthetic fixture values), this suite replays the
REAL audited package in ``data/verified_replay`` and checks that it publishes
through the gate and that every stored figure equals its printed cell in the
golden dataset. It asserts no catalog figure of its own: the only expectations
are the 7/68/4 audit oracle and equality with the audited golden dataset.
"""

from __future__ import annotations

import json
import uuid
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


def test_catalog_tools_bind_to_a_model_and_read_the_real_edition(real: Engine) -> None:
    """Every tool the agent hands to ``bind_tools`` has an OpenAI schema and runs."""

    from langchain_core.utils.function_calling import convert_to_openai_tool

    from series76_agent.integration.spec3 import PgCatalogToolProvider
    from series76_domain.tools.context import ToolContext

    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    context = ToolContext(edition_id=uuid.UUID(doc["edition_id"]))
    for tool_set, names in (("B", {"get_part_details", "search_parts", "get_source_notes"}),
                            ("A", {"query_parts"})):
        tools = PgCatalogToolProvider(real, tool_set).tools(context)
        assert set(tools) == names
        for name, tool in tools.items():
            schema = convert_to_openai_tool(tool)
            assert schema["function"]["name"] == name
            assert schema["function"]["parameters"]["properties"]
    with Session(real) as session:
        pn = PostgresTypedRepository.resolve_active(session).list_part_numbers()[0].canonical_pn
    result = PgCatalogToolProvider(real, "B").tools(context)["get_part_details"].invoke(
        {"part_number": pn})
    assert result.failure is None and result.facts


def test_supply_mode_filters_select_the_printed_tables(real: Engine) -> None:
    """'Runs on AC/DC' is T04 exactly; 'only DC' is T05 exactly (golden rows)."""

    from series76_agent.integration.spec3 import PgCatalogToolProvider
    from series76_agent.interpreter import settle_supply_modes
    from series76_domain.tools.context import ToolContext
    from series76_eval.ab_live import golden_rows

    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    rows = golden_rows(doc)
    tables = {t: {pn for pn, r in rows.items() if r.table == t} for t in ("T04", "T05")}
    search = PgCatalogToolProvider(real, "B").tools(
        ToolContext(edition_id=uuid.UUID(doc["edition_id"]), max_results=50))["search_parts"]
    model_wrote = {"type": "predicate", "field": "current_mode", "operator": "IN",
                   "value": ["AC", "DC"]}
    for message, table in (("Which parts run on 24 V AC/DC?", "T04"),
                           ("¿Qué partes funcionan solo con 24 V DC?", "T05")):
        ast = {"type": "and", "children": [
            {"type": "predicate", "field": "nominal_voltage", "operator": "EQ", "value": "24",
             "unit": "V"},
            settle_supply_modes(model_wrote, message)]}
        result = search.invoke({"filter_ast": ast})
        assert result.failure is None
        assert set(result.verified_pns) == tables[table], (message, result.verified_pns)


def test_parts_without_a_service_exclude_every_dual_service_row(real: Engine) -> None:
    from series76_agent.integration.spec3 import PgCatalogToolProvider
    from series76_agent.interpreter import _prune_filter
    from series76_domain.tools.context import ToolContext
    from series76_eval.ab_live import golden_rows

    doc = json.loads(GOLDEN.read_text(encoding="utf-8"))
    rows = golden_rows(doc)
    no_mod = {pn for pn, r in rows.items() if r.value("mod.torque_inlbs") is None}
    t04 = {pn for pn, r in rows.items() if r.table == "T04"}
    ast = _prune_filter({"type": "predicate", "field": "service", "operator": "NE",
                         "value": "modulante"}, frozenset(), [])
    search = PgCatalogToolProvider(real, "B").tools(
        ToolContext(edition_id=uuid.UUID(doc["edition_id"]), max_results=50))["search_parts"]
    result = search.invoke({"filter_ast": ast})
    assert result.failure is None
    listed = set(result.verified_pns) | set(result.preliminary_pns)
    assert t04 <= listed <= no_mod, sorted(listed - no_mod)

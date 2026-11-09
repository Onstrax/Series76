"""Spec 4 end-to-end integration on real PostgreSQL (Task 14.2, zero LLM cost).

The real orchestrator is mounted on the Spec 3 seam with the real adapters
(edition pinning, AES-256-GCM domain state, plan revisions, turn-state audit
events, Spec 2 PostgreSQL catalog tools on ``runtime_reader_role``). Only the
two language-model seams are fakes (recorded interpreter + scripted LangChain
chat model), so no provider is contacted and nothing is spent.

Every figure the API returns is cross-checked against the catalog through the
Spec 2 PostgreSQL adapter — the single source of numbers.
"""

from __future__ import annotations

import base64
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))

from _agent_fakes import (  # noqa: E402
    RecordedInterpreter,
    ScriptedChatModel,
    follow_plan,
    interp,
    pred,
    usage_of,
)

from series76_agent.agent_graph import ToolAgent  # noqa: E402
from series76_agent.domain.enums import Capability  # noqa: E402
from series76_agent.domain.ledger import CostLedger  # noqa: E402
from series76_agent.integration.spec3 import (  # noqa: E402
    PgCancellationPort,
    PgCatalogToolProvider,
    PgDomainStateStore,
    PgEditionPort,
    PgPlanPort,
    PgTurnStateRecorder,
)
from series76_agent.interpreter import SemanticInterpreter  # noqa: E402
from series76_agent.models import CapabilityRegistry, ModelConfig, ModelGateway  # noqa: E402
from series76_agent.orchestrator import AgentOrchestrator  # noqa: E402
from series76_agent.rendering import RenderedText, Span, untraceable_digit_runs  # noqa: E402
from series76_agent.seam import Series76Agent  # noqa: E402
from series76_api.app import create_app  # noqa: E402
from series76_api.infrastructure.clock import FixedClock  # noqa: E402
from series76_api.infrastructure.crypto import CryptoService  # noqa: E402
from series76_api.infrastructure.engine import (  # noqa: E402
    create_app_engine,
    create_session_factory,
)
from series76_api.infrastructure.settings import Settings  # noqa: E402
from series76_domain.operations.get_part import get_part  # noqa: E402
from series76_domain.repository.pg_adapter import PostgresTypedRepository  # noqa: E402

from ._spec3_helpers import register_and_login  # noqa: E402

pytestmark = pytest.mark.integration

KEK = base64.b64encode(b"series76-test-kek-32-bytes!!_ok_").decode("ascii")


def _table(seeded):  # type: ignore[no-untyped-def]
    dual, freq = seeded.dual_unit_pn, seeded.multi_freq_pn
    return {
        f"show {dual}": interp("EXACT_LOOKUP", part_numbers=[dual]),
        f"muestra {freq}": interp("EXACT_LOOKUP", part_numbers=[freq]),
        "parts with torque at least 1 in-lbs": interp(
            "FILTER_SEARCH", filter_ast=pred("torque_inlbs", "GE", "1", "in-lbs")
        ),
        "show the first one": interp("EXACT_LOOKUP", ordinal_references=[1]),
        "show ZZ-9999": interp("EXACT_LOOKUP", part_numbers=["ZZ-9999"]),
        "what is the weather": interp("OUT_OF_SCOPE"),
        "rank parts with torque at least 1 in-lbs": interp(
            "RECOMMENDATION",
            ranking_requested=True,
            filter_ast=pred("torque_inlbs", "GE", "1", "in-lbs"),
            criteria=[
                {
                    "description": "minimum torque",
                    "group": "REQUIRED_TORQUE",
                    "status": "SPECIFIED",
                    "declared_value": "1",
                    "declared_unit": "in-lbs",
                }
            ],
            proposed_priorities=[{"key": "torque_inlbs", "direction": "DESC"}],
        ),
    }


@pytest.fixture
def agent_app(seeded_catalog, postgres_url):  # type: ignore[no-untyped-def]
    seeded, _factory, engine = seeded_catalog
    crypto = CryptoService.from_base64_kek(KEK)
    adapter_engine = create_app_engine(postgres_url)
    sf = create_session_factory(adapter_engine)
    config = ModelConfig(agent_model="test/agent", interpreter_model="test/interp")
    registry = CapabilityRegistry(
        {
            "test/agent": frozenset({Capability.TOOLS}),
            "test/interp": frozenset({Capability.STRUCTURED_OUTPUT}),
        }
    )
    gateway = ModelGateway(config, registry, CostLedger())
    chat = ScriptedChatModel(responder=follow_plan)
    orchestrator = AgentOrchestrator(
        interpreter=SemanticInterpreter(RecordedInterpreter(_table(seeded)), gateway),
        tool_agent=ToolAgent(gateway, lambda _spec: chat, usage_of),
        catalog=PgCatalogToolProvider(engine, "B"),
        editions=PgEditionPort(sf),
        states=PgDomainStateStore(sf, crypto),
        turn_states=PgTurnStateRecorder(sf),
        plans=PgPlanPort(sf, crypto),
        cancellation=PgCancellationPort(sf),
    )
    settings = Settings(
        _env_file=None,
        DATABASE_URL=postgres_url,  # type: ignore[call-arg]
        ENCRYPTION_KEK=KEK,
    )
    app = create_app(
        settings,
        clock=FixedClock(datetime(2026, 1, 1, tzinfo=UTC)),
        crypto=crypto,
        agent=Series76Agent(orchestrator),
    )
    return app, seeded, engine, adapter_engine


def _figures(body: dict) -> list[dict]:  # type: ignore[type-arg]
    out = []
    for block in body["content_blocks"]:
        out.extend(block.get("figures", []))
        for row in block.get("metric_rows", []):
            out.extend(row["cells"])
    return out


def _check_against_catalog(engine, edition_id, body) -> None:  # type: ignore[no-untyped-def]
    """Every returned figure equals the catalog value digit-for-digit."""

    from sqlalchemy.orm import Session

    with Session(engine) as session:
        repo = PostgresTypedRepository.resolve_pinned(session, edition_id)
        cache: dict[str, set[tuple[str, str | None]]] = {}
        for fig in _figures(body):
            pn = fig["part_number"]
            if pn not in cache:
                view = get_part(repo, pn).view
                assert view is not None
                values: set[tuple[str, str | None]] = set()
                for sp in view.service_performance:
                    values.add(("torque_inlbs", _s(sp.torque_inlbs.value)))
                    values.add(("torque_nm", _s(sp.torque_nm.value)))
                    values.add(("duty_s4", _s(sp.duty_s4.value)))
                    values.add(("cycles_per_hour", _s(sp.cycles_per_hour.value)))
                    values.add(("starts_per_hour", _s(sp.starts_per_hour.value)))
                for up in view.unqualified_performance:
                    values.add(("torque_inlbs", _s(up.torque_inlbs.value)))
                    values.add(("torque_nm", _s(up.torque_nm.value)))
                    values.add(("duty_s4", _s(up.duty_s4.value)))
                    values.add(("cycles_per_hour", _s(up.cycles_per_hour.value)))
                    values.add(("starts_per_hour", _s(up.starts_per_hour.value)))
                for m in view.measurements:
                    values.add(("operating_speed", _s(m.operating_speed.value)))
                    values.add(("fla", _s(m.fla.value)))
                    values.add(("lra", _s(m.lra.value)))
                for c in view.configurations:
                    values.add(("motor_power", _s(c.motor_power.value)))
                    if c.supply_profile is not None:
                        values.add(("nominal_voltage", _s(c.supply_profile.voltage_v.value)))
                cache[pn] = values
            assert (fig["metric_key"], fig["value"]) in cache[pn], fig
        session.rollback()


def _s(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _answer_has_no_free_numbers(body: dict, edition_id: uuid.UUID) -> None:  # type: ignore[type-arg]
    """No digit in the answer outside figure/PN/edition text from typed results."""

    text_ = body["answer"]
    allowed: list[str] = [f"series_76_electric_data.pdf, edition {str(edition_id)[:8]}"]
    for fig in _figures(body):
        allowed.append(fig["part_number"])
        if fig["value"]:
            allowed.append(fig["value"])
        if fig["frequency_hz"]:
            allowed.append(fig["frequency_hz"])
        if fig["supply"]:
            allowed.append(fig["supply"])
        if fig["formula"]:
            allowed.append(fig["formula"])
    for block in body["content_blocks"]:
        allowed.extend(block.get("part_numbers", []) or [])
        if block.get("total") is not None:
            allowed.append(str(block["total"]))
    spans = []
    for token in sorted(set(allowed), key=len, reverse=True):
        start = text_.find(token)
        while start >= 0:
            spans.append(Span(start, start + len(token), "allowed", token))
            start = text_.find(token, start + 1)
    leftover = untraceable_digit_runs(RenderedText(text_, tuple(spans), ()))
    assert leftover == [] or all(r in ("1",) for r in leftover), leftover  # "1" = user's


async def test_spec4_end_to_end_on_real_postgres(agent_app) -> None:  # type: ignore[no-untyped-def]
    app, seeded, engine, adapter_engine = agent_app
    dual = seeded.dual_unit_pn
    transport = ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://testserver") as client,
    ):
        _email, headers = await register_and_login(client)

        # 1) Exact lookup: single pass, typed figures, pinned edition.
        r = await client.post("/api/conversation", json={"query": f"show {dual}"}, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        sid = body["session_id"]
        assert body["catalog_edition_id"] == str(seeded.published_edition_id)
        assert body["interpretation_summary"]["intent"]
        assert any(b["kind"] == "product_card" for b in body["content_blocks"])
        assert _figures(body)
        _check_against_catalog(engine, seeded.published_edition_id, body)
        _answer_has_no_free_numbers(body, seeded.published_edition_id)

        # 2) Spanish follow-up in the same conversation: response language follows.
        r = await client.post(
            "/api/conversation",
            json={"query": f"muestra {seeded.multi_freq_pn}", "session_id": sid},
            headers=headers,
        )
        assert r.status_code == 200 and r.json()["answer"].startswith("Datos documentados")
        _check_against_catalog(engine, seeded.published_edition_id, r.json())

        # 3) Search, then an ordinal follow-up resolved from persisted state.
        r = await client.post(
            "/api/conversation",
            json={"query": "parts with torque at least 1 in-lbs", "session_id": sid},
            headers=headers,
        )
        assert r.status_code == 200
        listing = next(
            b for b in r.json()["content_blocks"] if b["kind"] == "matching_part_numbers"
        )
        first = listing["part_numbers"][0]
        r = await client.post(
            "/api/conversation",
            json={"query": "show the first one", "session_id": sid},
            headers=headers,
        )
        assert r.status_code == 200
        cards = [b for b in r.json()["content_blocks"] if b["kind"] == "product_card"]
        assert cards and cards[0]["part_number"] == first

        # 4) Not listed + out of scope.
        r = await client.post(
            "/api/conversation", json={"query": "show ZZ-9999", "session_id": sid}, headers=headers
        )
        assert "not listed" in r.json()["answer"]
        r = await client.post(
            "/api/conversation",
            json={"query": "what is the weather", "session_id": sid},
            headers=headers,
        )
        assert r.json()["content_blocks"] == [] or all(
            b["kind"] == "text" for b in r.json()["content_blocks"]
        )

        # 5) Unaccepted priority -> plan revision awaiting confirmation; confirm
        #    executes exactly once through the Spec 3 plan seam.
        r = await client.post(
            "/api/conversation",
            json={"query": "rank parts with torque at least 1 in-lbs", "session_id": sid},
            headers=headers,
        )
        body = r.json()
        assert body["status"] == "AWAITING_CONFIRMATION"
        rev = body["plan"]["revision"]
        c1 = await client.post(f"/api/sessions/{sid}/plans/{rev}/confirm", headers=headers)
        assert c1.status_code == 200, c1.text
        result = c1.json()["result"]
        assert result is not None and result["status"] == "COMPLETED"
        c2 = await client.post(f"/api/sessions/{sid}/plans/{rev}/confirm", headers=headers)
        assert c2.status_code == 200 and c2.json()["result"] is None  # idempotent

    # Persistence: edition pinned, state encrypted, transitions audited.
    from sqlalchemy import create_engine

    sync = create_engine(engine.url)
    with sync.connect() as conn:
        pinned = conn.execute(
            text("SELECT catalog_edition_id FROM conversation.conversations WHERE session_id = :s"),
            {"s": sid},
        ).scalar_one()
        assert str(pinned) == str(seeded.published_edition_id)
        blob = conn.execute(
            text("SELECT state_ciphertext FROM conversation.domain_states WHERE session_id = :s"),
            {"s": sid},
        ).scalar_one()
        assert dual.encode() not in bytes(blob)  # ciphertext, never plaintext
        events = conn.execute(
            text(
                "SELECT count(*) FROM execution.audit_events_minimal "
                "WHERE event_type LIKE 'turn_state:%'"
            )
        ).scalar_one()
        assert events > 0
        traces = conn.execute(
            text("SELECT count(*) FROM execution.tool_traces WHERE session_id = :s"), {"s": sid}
        ).scalar_one()
        assert traces > 0
    sync.dispose()
    await adapter_engine.dispose()

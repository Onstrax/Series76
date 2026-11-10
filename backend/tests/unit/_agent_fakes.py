"""Zero-cost test harness for Spec 4 (agent-orchestration-response).

* Spec 2 is exercised for real (operations, services, LangChain tools) over an
  in-memory :class:`FakeRepository` — no database, no SQL.
* The interpreter LLM is a **recorded** model returning fixed structured
  interpretations; the tool-calling LLM is a scripted LangChain
  ``BaseChatModel``. Both count their calls; neither touches the network.
* Spec 3 seams (edition pinning, encrypted domain state, turn-state recorder,
  plan revisions, cancellation) are in-memory fakes modeling the contracts,
  with a transaction flag so tests can assert no transaction spans a model call.

The fixture catalog values are arbitrary test data — not figures from the PDF.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from _fakes import FakePartData, FakeRepository
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

from series76_agent.agent_graph import ToolAgent
from series76_agent.composer import ResponseComposer
from series76_agent.domain.budget import TurnBudget
from series76_agent.domain.conversation import DomainConversationState
from series76_agent.domain.enums import Capability, TurnState
from series76_agent.domain.ledger import CostLedger
from series76_agent.fallback import RetryPolicy
from series76_agent.interpreter import InterpretationOutput, SemanticInterpreter
from series76_agent.models import CapabilityRegistry, ModelConfig, ModelGateway, RequestSpec, Usage
from series76_agent.orchestrator import AgentOrchestrator, OrchestratorConfig, TurnInput, TurnResult
from series76_agent.policy import ConfirmationSignal
from series76_agent.ports import EditionInfo
from series76_agent.tools import TOOL_SET_B
from series76_data.models.enums import FrequencyState, SupplyMode
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
    SupplyProfile,
    UnqualifiedPerformance,
)
from series76_domain.model.units import Unit
from series76_domain.repository.port import PinnedEdition
from series76_domain.tools import build_set_a, build_set_b
from series76_domain.tools.context import ToolContext

_ids = itertools.count(1000)
TEST_AGENT_MODEL = "test/agent-model"
TEST_INTERPRETER_MODEL = "test/interpreter-model"


def _nid() -> int:
    return next(_ids)


def _metric(value: str | int | None, unit: Unit, *, na: bool = False) -> MetricValue:
    if value is None:
        return MetricValue.not_applicable(unit) if na else MetricValue.not_documented(unit)
    return MetricValue.available(Decimal(str(value)), unit)


def make_part(
    pn: str,
    edition_id: uuid.UUID,
    *,
    services: Mapping[str, tuple[str | int | None, str | int | None]] | None = None,
    measurements: tuple[tuple[int, str | int | None, str | int | None, str | int | None], ...] = (),
    voltage: int | None = 24,
    modes: frozenset[SupplyMode] = frozenset({SupplyMode.AC, SupplyMode.DC}),
    enclosure: str = "NEMA 4X",
    unqualified_torque: tuple[str | int | None, str | int | None] | None = None,
    notes: tuple[str, ...] = (),
    na: bool = True,
    evidence_id: int | None = None,
    motor_power: str | int | None = None,
) -> FakePartData:
    """Build a part with service rows, frequency-bound measurements, a supply."""

    cfg_id = _nid()

    def ev() -> EvidenceReference:
        return EvidenceReference(cell_refs=(evidence_id if evidence_id is not None else _nid(),))

    profile = SupplyProfile(
        voltage_v=_metric(voltage, Unit.VOLT, na=na),
        phase_state=None,
        phase_count=None,
        modes=modes,
    )
    config = Configuration(
        configuration_id=cfg_id,
        edition_id=edition_id,
        enclosure=enclosure,
        supply_profile=profile,
        motor_power=_metric(motor_power, Unit.WATT, na=False),
        availability=DataStatus.AVAILABLE,
        evidence=ev(),
    )
    sps = tuple(
        ServicePerformance(
            configuration_id=cfg_id,
            service_type=name,
            torque_inlbs=_metric(inlbs, Unit.IN_LBS, na=na),
            torque_nm=_metric(nm, Unit.NM, na=na),
            duty_s4=_metric(None, Unit.PERCENT, na=False),
            cycles_per_hour=_metric(None, Unit.COUNT, na=False),
            starts_per_hour=_metric(None, Unit.COUNT, na=False),
            evidence=ev(),
        )
        for name, (inlbs, nm) in (services or {}).items()
    )
    ups: tuple[UnqualifiedPerformance, ...] = ()
    if unqualified_torque is not None:
        ups = (
            UnqualifiedPerformance(
                configuration_id=cfg_id,
                torque_inlbs=_metric(unqualified_torque[0], Unit.IN_LBS, na=True),
                torque_nm=_metric(unqualified_torque[1], Unit.NM, na=True),
                duty_s4=_metric(None, Unit.PERCENT, na=False),
                cycles_per_hour=_metric(None, Unit.COUNT, na=False),
                starts_per_hour=_metric(None, Unit.COUNT, na=False),
                evidence=ev(),
            ),
        )
    conds: list[OperatingCondition] = []
    meas: list[ElectricalMeasurement] = []
    for freq, speed, fla, lra in measurements:
        cid = _nid()
        hz = MetricValue.available(Decimal(freq), Unit.HERTZ)
        conds.append(
            OperatingCondition(
                condition_id=cid,
                configuration_id=cfg_id,
                frequency_state=FrequencyState.EXPLICIT,
                frequency_hz=hz,
            )
        )
        meas.append(
            ElectricalMeasurement(
                measurement_id=_nid(),
                condition_id=cid,
                frequency_state=FrequencyState.EXPLICIT,
                frequency_hz=hz,
                operating_speed=_metric(speed, Unit.SECOND, na=na),
                fla=_metric(fla, Unit.AMPERE, na=na),
                lra=_metric(lra, Unit.AMPERE, na=na),
                evidence=ev(),
            )
        )
    part = PartNumber(canonical_pn=pn, printed_pn=pn, edition_id=edition_id, part_id=_nid())
    note_objs = tuple(
        Note(
            note_id=_nid(),
            marker="*",
            note_type="footnote",
            printed_text=text,
            covered_rows=(part.part_id,),
            data_status=DataStatus.AVAILABLE,
            evidence=EvidenceReference(row_refs=(part.part_id,)),
        )
        for text in notes
    )
    return FakePartData(
        part_number=part,
        configurations=(config,),
        service_performance=sps,
        unqualified_performance=ups,
        operating_conditions=tuple(conds),
        measurements=tuple(meas),
        notes=note_objs,
    )


def default_catalog(edition: PinnedEdition) -> FakeRepository:
    """A small fixture catalog covering the shapes the agent must handle."""

    eid = edition.edition_id
    repo = FakeRepository(pinned=edition)
    repo.add(
        make_part(
            "76-100",
            eid,
            services={"On/Off": (100, "11.3"), "Modulating": (90, "10.2")},
            measurements=((50, 18, "1.2", 3), (60, 15, "1.0", "2.5")),
        )
    )
    repo.add(
        make_part("76-200", eid, services={"On/Off": (200, "22.6")}, measurements=((60, 20, 2, 5),))
    )
    repo.add(
        make_part(
            "76-300",
            eid,
            services={"On/Off": (150, "16.9")},
            measurements=((60, 12, None, 4),),
            voltage=120,
            modes=frozenset({SupplyMode.AC}),
            enclosure="NEMA 4",
        )
    )
    repo.add(
        make_part(
            "76-T03",
            eid,
            unqualified_torque=(None, None),
            measurements=((60, None, None, None),),
            notes=("Torque not documented for this model.",),
        )
    )
    return repo


class CountingRepository:
    """Wraps a repository and counts every typed read (there is no SQL method)."""

    def __init__(self, inner: FakeRepository) -> None:
        self._inner = inner
        self.reads: list[str] = []

    @property
    def pinned_edition(self) -> PinnedEdition:
        return self._inner.pinned_edition

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._inner, name)
        if callable(attr):

            def wrapped(*args: Any, **kwargs: Any) -> Any:
                self.reads.append(name)
                return attr(*args, **kwargs)

            return wrapped
        return attr


class SpyCatalog:
    """CatalogToolProvider over the real Spec 2 tools; records server contexts."""

    def __init__(self, repo: FakeRepository, *, tool_set: str = "B") -> None:
        self.repo = CountingRepository(repo)
        self.contexts: list[ToolContext] = []
        self.tool_set = tool_set

    def tools(self, context: ToolContext) -> dict[str, Any]:
        self.contexts.append(context)

        def provider() -> ToolContext:
            return context

        def factory(ctx: ToolContext) -> Any:
            assert ctx.edition_id == context.edition_id
            return self.repo

        if self.tool_set == "A":
            return dict(build_set_a(provider, factory))
        return dict(build_set_b(provider, factory))


# --- recorded interpreter LLM -------------------------------------------------


class RecordedInterpreter:
    """Replays recorded structured interpretations; counts calls (zero spend)."""

    def __init__(
        self,
        table: Mapping[str, InterpretationOutput] | Callable[[str], InterpretationOutput],
        events: list[tuple[str, str]] | None = None,
        txn_flag: Callable[[], bool] | None = None,
    ) -> None:
        self._table = table
        self.calls: list[tuple[str, str]] = []
        self.events = events if events is not None else []
        self._txn_flag = txn_flag

    async def interpret(
        self, spec: RequestSpec, system: str, message: str, context_hint: str
    ) -> tuple[InterpretationOutput, Usage]:
        if self._txn_flag is not None:
            assert not self._txn_flag(), "a SQL transaction is open across a model call"
        self.calls.append((spec.model, message))
        self.events.append(("model", "interpret"))
        if callable(self._table):
            out = self._table(message)
        else:
            last = message.split("\n")[-1]
            out = self._table.get(message) or self._table[last]
        return out, Usage(
            prompt_tokens=12, completion_tokens=8, cost_usd=Decimal("0.0001"), provider="recorded"
        )


# --- scripted tool-calling chat model ------------------------------------------

Responder = Callable[[list[BaseMessage], list[str]], AIMessage]


def follow_plan(messages: list[BaseMessage], tool_names: list[str]) -> AIMessage:
    """A well-behaved tool selector: issues exactly the plan's reads, then DONE."""

    if any(isinstance(m, ToolMessage) for m in messages):
        return AIMessage(content="DONE")
    human = next(m for m in messages if isinstance(m, HumanMessage))
    plan = json.loads(str(human.content))["validated_plan"]
    generic = "query_parts" in tool_names
    calls: list[dict[str, Any]] = []
    pns = list(plan.get("part_numbers") or [])
    for i, need in enumerate(plan.get("needs") or []):
        if need == "GET":
            pn = pns[i] if i < len(pns) else pns[0]
            args: dict[str, Any] = (
                {"op": "GET", "part_number": pn} if generic else {"part_number": pn}
            )
            calls.append(
                {
                    "name": "query_parts" if generic else "get_part_details",
                    "args": args,
                    "id": f"c{i}",
                    "type": "tool_call",
                }
            )
        elif need == "SEARCH":
            args = (
                {"op": "SEARCH", "filter_ast": plan["filter_ast"]}
                if generic
                else {"filter_ast": plan["filter_ast"]}
            )
            calls.append(
                {
                    "name": "query_parts" if generic else "search_parts",
                    "args": args,
                    "id": f"c{i}",
                    "type": "tool_call",
                }
            )
        elif need == "NOTES":
            calls.append(
                {
                    "name": "get_source_notes",
                    "args": {"part_number": pns[0]},
                    "id": f"c{i}",
                    "type": "tool_call",
                }
            )
    return AIMessage(content="", tool_calls=calls)


def lazy(messages: list[BaseMessage], tool_names: list[str]) -> AIMessage:
    """A model that calls no tool (the coordinator completes required reads)."""
    return AIMessage(content="I think the torque is 999 in-lbs. DONE")


class ScriptedChatModel(BaseChatModel):
    """A LangChain chat model with scripted tool calls (no network)."""

    responder: Any
    calls: list[list[BaseMessage]] = Field(default_factory=list)
    txn_flag: Any = None
    events: Any = None

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> Any:
        names = [getattr(t, "name", str(t)) for t in tools]
        return self.bind(tool_names=names)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        if self.txn_flag is not None:
            assert not self.txn_flag(), "a SQL transaction is open across a model call"
        self.calls.append(list(messages))
        if self.events is not None:
            self.events.append(("model", "agent"))
        msg = self.responder(list(messages), list(kwargs.get("tool_names", [])))
        msg.usage_metadata = {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25}
        return ChatResult(generations=[ChatGeneration(message=msg)])


def usage_of(message: AIMessage) -> Usage:
    meta = message.usage_metadata
    return Usage(
        prompt_tokens=int(meta["input_tokens"]) if meta else 0,
        completion_tokens=int(meta["output_tokens"]) if meta else 0,
        cost_usd=Decimal("0.0002"),
        provider="scripted",
    )


# --- Spec 3 seams (in memory) ---------------------------------------------------


@dataclass
class MemEditions:
    edition: EditionInfo | None

    async def pinned_edition(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID
    ) -> EditionInfo | None:
        return self.edition


@dataclass
class MemStates:
    data: dict[tuple[uuid.UUID, uuid.UUID], DomainConversationState] = field(default_factory=dict)
    saves: int = 0

    async def load(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID
    ) -> DomainConversationState | None:
        return self.data.get((session_id, owner_id))

    async def save(self, state: DomainConversationState) -> None:
        self.saves += 1
        # Round-trip through JSON exactly like the encrypted Spec 3 store.
        self.data[(state.session_id, state.owner_id)] = DomainConversationState.from_json(
            json.loads(json.dumps(state.to_json()))
        )


@dataclass
class RecordingTurnStates:
    events: list[tuple[str, str]] = field(default_factory=list)
    records: list[tuple[str, TurnState]] = field(default_factory=list)
    in_txn: bool = False

    async def record(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID, turn_id: str, state: TurnState
    ) -> None:
        self.in_txn = True  # BEGIN
        self.records.append((turn_id, state))
        self.events.append(("record", state.value))
        self.in_txn = False  # COMMIT


@dataclass
class MemPlans:
    revisions: dict[uuid.UUID, int] = field(default_factory=dict)
    created: list[tuple[uuid.UUID, str, int]] = field(default_factory=list)

    async def create_revision(
        self, *, session_id: uuid.UUID, owner_id: uuid.UUID, payload: str
    ) -> tuple[str, int]:
        rev = self.revisions.get(session_id, 0) + 1
        self.revisions[session_id] = rev
        plan_id = uuid.uuid4().hex
        self.created.append((session_id, plan_id, rev))
        return plan_id, rev


@dataclass
class FlagCancel:
    cancelled: bool = False

    async def is_cancelled(self, *, session_id: uuid.UUID, owner_id: uuid.UUID) -> bool:
        return self.cancelled


async def _no_sleep(_: float) -> None:
    return None


@dataclass
class Harness:
    orch: AgentOrchestrator
    interp: RecordedInterpreter
    chat: ScriptedChatModel
    states: MemStates
    turns: RecordingTurnStates
    plans: MemPlans
    editions: MemEditions
    catalog: SpyCatalog
    gateway: ModelGateway
    ledger: CostLedger
    cancel: FlagCancel
    edition: PinnedEdition
    events: list[tuple[str, str]]
    specs: list[RequestSpec]

    def run(
        self,
        session_id: uuid.UUID,
        owner_id: uuid.UUID,
        message: str | None = None,
        confirmation: ConfirmationSignal | None = None,
    ) -> TurnResult:
        return asyncio.run(
            self.orch.run_turn(
                TurnInput(
                    session_id=session_id,
                    owner_id=owner_id,
                    message=message,
                    confirmation=confirmation,
                    trace_id="trace-test",
                )
            )
        )


def make_harness(
    table: Mapping[str, InterpretationOutput] | Callable[[str], InterpretationOutput],
    *,
    responder: Responder = follow_plan,
    budget: TurnBudget | None = None,
    allow: frozenset[str] = TOOL_SET_B,
    tool_set: str = "B",
    withdrawn: bool = False,
    repo: FakeRepository | None = None,
    no_edition: bool = False,
    caps: Mapping[str, frozenset[Capability]] | None = None,
    composer: ResponseComposer | None = None,
) -> Harness:
    edition = PinnedEdition(edition_id=uuid.uuid4(), is_published=True, is_withdrawn=withdrawn)
    catalog_repo = repo if repo is not None else default_catalog(edition)
    if repo is not None:
        edition = repo.pinned
    events: list[tuple[str, str]] = []
    turns = RecordingTurnStates(events=events)
    interp = RecordedInterpreter(table, events=events, txn_flag=lambda: turns.in_txn)
    chat = ScriptedChatModel(responder=responder, txn_flag=lambda: turns.in_txn, events=events)
    config = ModelConfig(agent_model=TEST_AGENT_MODEL, interpreter_model=TEST_INTERPRETER_MODEL)
    registry = CapabilityRegistry(
        dict(caps)
        if caps is not None
        else {
            TEST_AGENT_MODEL: frozenset({Capability.TOOLS}),
            TEST_INTERPRETER_MODEL: frozenset({Capability.STRUCTURED_OUTPUT}),
        }
    )
    ledger = CostLedger()
    retry = RetryPolicy(sleep=_no_sleep)
    gateway = ModelGateway(config, registry, ledger, retry=retry)
    specs: list[RequestSpec] = []

    def factory(spec: RequestSpec) -> ScriptedChatModel:
        specs.append(spec)
        return chat

    states = MemStates()
    plans = MemPlans()
    editions = MemEditions(None if no_edition else EditionInfo(edition.edition_id, withdrawn))
    catalog = SpyCatalog(catalog_repo, tool_set=tool_set)
    cancel = FlagCancel()
    orch = AgentOrchestrator(
        interpreter=SemanticInterpreter(interp, gateway),
        tool_agent=ToolAgent(gateway, factory, usage_of),
        catalog=catalog,
        editions=editions,
        states=states,
        turn_states=turns,
        plans=plans,
        cancellation=cancel,
        config=OrchestratorConfig(
            tool_allow_list=allow, budget=budget or TurnBudget(), retry=retry
        ),
        composer=composer,
    )
    return Harness(
        orch,
        interp,
        chat,
        states,
        turns,
        plans,
        editions,
        catalog,
        gateway,
        ledger,
        cancel,
        edition,
        events,
        specs,
    )


# --- interpretation builders ------------------------------------------------------


def interp(intent: str, **kw: Any) -> InterpretationOutput:
    """Shorthand for a recorded interpretation."""
    return InterpretationOutput(intent=intent, **kw)


def pred(field_name: str, op: str, value: Any, unit: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"type": "predicate", "field": field_name, "operator": op, "value": value}
    if unit is not None:
        out["unit"] = unit
    return out


def visible_text(result: TurnResult) -> str:
    """Everything a user can see: answer, blocks, summary."""

    parts = [result.response.answer.text]
    parts.extend(b.model_dump_json() for b in result.response.blocks)
    if result.response.summary is not None:
        parts.append(result.response.summary.all_text())
    return "\n".join(parts)

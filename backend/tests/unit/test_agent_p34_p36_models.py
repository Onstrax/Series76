"""Spec 4 Properties 34-36: model configuration, capability routing, cost ledger.

No live call is made: every model is a fake. Nothing here (or in the shipped
code) declares a winning model or tool set.
"""

from __future__ import annotations

import asyncio
import pathlib
import re
import uuid
from decimal import Decimal

import pytest
from _agent_fakes import interp, make_harness
from hypothesis import given
from hypothesis import strategies as st

import series76_agent
from series76_agent.domain.budget import BudgetTracker, TurnBudget
from series76_agent.domain.enums import Capability, ModelFunction
from series76_agent.domain.ledger import (
    DEMO_RESERVE_USD,
    DEV_EVAL_CAP_USD,
    HARD_CAP_USD,
    CostCapReached,
    CostLedger,
    LedgerEntry,
    SpendCategory,
)
from series76_agent.fallback import RetryPolicy, TransientError
from series76_agent.models import (
    REQUIRED_CAPABILITIES,
    CapabilityRegistry,
    FallbackAborted,
    ModelConfig,
    ModelConfigError,
    ModelGateway,
    ProviderUnavailableError,
    RequestSpec,
    UnsupportedCapability,
    Usage,
    request_options,
    select_fallback,
)

model_ids = st.from_regex(r"[a-z]{3,8}/[a-z0-9.\-]{3,12}", fullmatch=True)
caps_sets = st.frozensets(st.sampled_from(list(Capability)))
SRC = pathlib.Path(series76_agent.__file__).parent
#: Patterns of real model identifiers that must never be hardcoded in shipped code.
MODEL_ID_PATTERN = re.compile(
    r"(qwen/|deepseek/|openai/gpt|anthropic/|google/gemini|meta-llama/|mistralai/|gpt-4)",
    re.IGNORECASE,
)


# Feature: agent-orchestration-response, Property 34: Models are env-configured with
# multiple candidates and bounded call counts, and no LLM produces numbers
@given(
    agent=model_ids,
    interpreter=st.one_of(st.none(), model_ids),
    candidates=st.lists(model_ids, min_size=2, max_size=4, unique=True),
    max_calls=st.integers(2, 6),
)
def test_property_34_env_models_candidates_bounded_calls(
    agent: str, interpreter: str | None, candidates: list[str], max_calls: int
) -> None:
    env = {
        "AGENT_MODEL": agent,
        "AGENT_MODEL_CANDIDATES": ",".join(candidates),
        "INTERPRETER_MODEL_CANDIDATES": ",".join(candidates),
        "ANSWER_MODEL_CANDIDATES": ",".join(candidates),
    }
    if interpreter:
        env["INTERPRETER_MODEL"] = interpreter
    config = ModelConfig.from_env(env)
    for fn in ModelFunction:
        assert len(config.candidates_for(fn)) >= 2
    assert config.model_for(ModelFunction.TOOL_CALLING) == agent
    assert config.model_for(ModelFunction.INTERPRETATION) == (interpreter or agent)
    with pytest.raises(ModelConfigError):
        ModelConfig.from_env({})
    # Several candidates configured never multiply calls within a turn.
    h = make_harness(
        {"show 76-100": interp("EXACT_LOOKUP", part_numbers=["76-100"])},
        budget=TurnBudget(max_model_calls_per_turn=max_calls),
    )
    h.run(uuid.uuid4(), uuid.uuid4(), "show 76-100")
    per_function: dict[ModelFunction, int] = {}
    for fn, _model in h.gateway.calls:
        per_function[fn] = per_function.get(fn, 0) + 1
    assert per_function.get(ModelFunction.INTERPRETATION, 0) == 1
    assert sum(per_function.values()) <= max_calls
    assert ModelFunction.EXPLANATION not in per_function  # composition is deterministic
    # No model identifier is hardcoded anywhere in the shipped agent package, and
    # ranking / composition / titles hold no model seam.
    for path in SRC.rglob("*.py"):
        assert not MODEL_ID_PATTERN.search(path.read_text(encoding="utf-8")), path
    for module in ("recommendation.py", "composer.py", "claim_verifier.py", "policy.py"):
        text = (SRC / module).read_text(encoding="utf-8")
        assert "ModelGateway" not in text and "langchain" not in text


# Feature: agent-orchestration-response, Property 35: Endpoint capability is verified and
# feature routing is strict or fails closed
@given(
    function=st.sampled_from(list(ModelFunction)),
    caps=caps_sets,
    known=st.booleans(),
    privacy=st.sampled_from(["deny", "allow"]),
)
def test_property_35_capability_verified_strict_routing(
    function: ModelFunction, caps: frozenset[Capability], known: bool, privacy: str
) -> None:
    config = ModelConfig(
        agent_model="x/agent",
        interpreter_model="x/interp",
        answer_model="x/answer",
        data_collection=privacy,
    )
    model = config.model_for(function)
    assert model is not None
    registry = CapabilityRegistry({model: caps} if known else {})
    gateway = ModelGateway(config, registry, CostLedger())
    invoked: list[RequestSpec] = []

    async def invoke(spec: RequestSpec) -> tuple[str, Usage]:
        invoked.append(spec)
        return "ok", Usage(1, 1, Decimal("0.0001"))

    required = REQUIRED_CAPABILITIES[function]
    budget = BudgetTracker(TurnBudget())
    if known and required <= caps:
        result = asyncio.run(gateway.call(function, budget, invoke))
        assert result.value == "ok" and len(invoked) == 1
        body = invoked[0].extra_body
        assert body["provider"]["require_parameters"] is True  # type: ignore[index]
        assert body["provider"]["data_collection"] == privacy  # type: ignore[index]
    else:
        with pytest.raises(UnsupportedCapability):
            asyncio.run(gateway.call(function, budget, invoke))
        assert invoked == []  # never silently proceeds against the endpoint
        assert budget.model_calls == 0
    assert (
        request_options(frozenset(), data_collection=privacy)["provider"][  # type: ignore[index]
            "require_parameters"
        ]
        is False
    )
    assert registry.supports_combined_phase(model) == (
        known and {Capability.TOOLS, Capability.STRUCTURED_OUTPUT} <= caps
    )


spends = st.lists(
    st.tuples(
        st.sampled_from(list(SpendCategory)),
        st.decimals(min_value=Decimal("0.01"), max_value=Decimal("3"), places=2),
    ),
    max_size=20,
)


# Feature: agent-orchestration-response, Property 36: The cost ledger respects the cap and
# the demo reserve, and fallback preserves capabilities or aborts
@given(seq=spends, fb_caps=caps_sets, privacy=st.sampled_from(["deny", "allow"]))
def test_property_36_ledger_cap_reserve_and_fallback(
    seq: list[tuple[SpendCategory, Decimal]], fb_caps: frozenset[Capability], privacy: str
) -> None:
    ledger = CostLedger()
    for category, cost in seq:
        try:
            ledger.authorize(category, cost)
        except CostCapReached:
            continue
        ledger.record(LedgerEntry("prov", "m", "f", 1, 1, cost, category))
        assert ledger.dev_eval_spent <= DEV_EVAL_CAP_USD
        assert ledger.total_spent <= HARD_CAP_USD
    if ledger.dev_eval_spent >= DEV_EVAL_CAP_USD:
        with pytest.raises(CostCapReached):
            ledger.authorize(SpendCategory.DEV_EVAL, Decimal("0.01"))
    # The demo reserve stays available after dev/eval is exhausted.
    assert ledger.remaining(SpendCategory.DEMO) >= min(
        DEMO_RESERVE_USD, HARD_CAP_USD - ledger.total_spent
    )
    # Provider fallback: preserves the required capabilities + privacy, or aborts.
    primary = RequestSpec("p/model", frozenset({Capability.TOOLS}), privacy)
    registry = CapabilityRegistry({"f/model": fb_caps})
    if Capability.TOOLS in fb_caps:
        fb = select_fallback(primary, "f/model", registry)
        assert fb.required == primary.required and fb.data_collection == privacy
    else:
        with pytest.raises(FallbackAborted):
            select_fallback(primary, "f/model", registry)
    # Gateway-level: an unavailable primary with an incompatible fallback aborts.
    config = ModelConfig(agent_model="p/model", fallback_model="f/model", data_collection=privacy)
    reg = CapabilityRegistry({"p/model": frozenset({Capability.TOOLS}), "f/model": fb_caps})

    async def no_sleep(_: float) -> None:
        return None

    gw = ModelGateway(config, reg, CostLedger(), retry=RetryPolicy(max_attempts=1, sleep=no_sleep))
    served: list[str] = []

    async def invoke(spec: RequestSpec) -> tuple[str, Usage]:
        served.append(spec.model)
        if spec.model == "p/model":
            raise TransientError("down")
        return "ok", Usage()

    if Capability.TOOLS in fb_caps:
        res = asyncio.run(gw.call(ModelFunction.TOOL_CALLING, BudgetTracker(TurnBudget()), invoke))
        assert res.spec.model == "f/model" and res.spec.data_collection == privacy
    else:
        with pytest.raises(ProviderUnavailableError):
            asyncio.run(gw.call(ModelFunction.TOOL_CALLING, BudgetTracker(TurnBudget()), invoke))
        assert served == ["p/model"]


def test_no_winner_declared_anywhere() -> None:
    """Req 11.10 status discipline: no code path declares a winning model/tool set."""

    pattern = re.compile(
        r"(winner_model|winning_model|best_model|winner_tool_set|"
        r"declare_winner|selected_winner)",
        re.IGNORECASE,
    )
    for path in SRC.rglob("*.py"):
        assert not pattern.search(path.read_text(encoding="utf-8")), path

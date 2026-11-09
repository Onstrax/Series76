"""Model / budget manager (Req 11.1-11.11) — harness-ready, **no winner**.

* :class:`ModelConfig` reads the model per function from environment variables
  (``AGENT_MODEL`` required; ``INTERPRETER_MODEL`` / ``ANSWER_MODEL`` /
  ``FALLBACK_MODEL`` optional) plus ``*_CANDIDATES`` lists so Spec 6 can compare
  at least two candidates per function. No model identifier is hardcoded.
* :class:`CapabilityRegistry` holds the *verified* capabilities of exact
  endpoints; an unknown model or a missing capability fails closed before any
  request is issued.
* :func:`request_options` routes OpenRouter with ``require_parameters=true``
  whenever a feature is required, so no incompatible provider is selected.
* :class:`ModelGateway` wraps every model call: per-turn budget, capability
  check, cost-ledger authorization (USD 10 / 6 / 4), bounded retry of transient
  errors, no fallback on a 402/quota error, and a fallback model only if it
  preserves the required capabilities and privacy setting.

Nothing here declares a winning model or tool set (Req 11.10); that is an
experiment resolved by Spec 6.
"""

from __future__ import annotations

import json
import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Generic, TypeVar

from series76_agent.domain.budget import BudgetTracker
from series76_agent.domain.enums import Capability, ModelFunction
from series76_agent.domain.ledger import CostLedger, LedgerEntry, SpendCategory
from series76_agent.fallback import RetryPolicy, TransientError, retry_idempotent

T = TypeVar("T")

DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

#: Capabilities each model function needs from its endpoint.
REQUIRED_CAPABILITIES: dict[ModelFunction, frozenset[Capability]] = {
    ModelFunction.INTERPRETATION: frozenset({Capability.STRUCTURED_OUTPUT}),
    ModelFunction.TOOL_CALLING: frozenset({Capability.TOOLS}),
    ModelFunction.EXPLANATION: frozenset({Capability.STRUCTURED_OUTPUT}),
}


class ModelConfigError(ValueError):
    """The model configuration is missing a required variable."""


class UnsupportedCapability(Exception):
    """The configured endpoint does not (verifiably) support a required feature."""


class ProviderQuotaExceeded(Exception):
    """OpenRouter returned 402 / quota exhausted. Never answered by switching."""


class ProviderUnavailableError(Exception):
    """The provider failed after bounded retries (and no valid fallback)."""


class FallbackAborted(Exception):
    """A fallback model would change required capabilities or privacy."""


def _split(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    return tuple(dict.fromkeys(x.strip() for x in raw.split(",") if x.strip()))


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Environment-configured model assignment per function (Req 11.1, 11.2)."""

    agent_model: str
    interpreter_model: str | None = None
    answer_model: str | None = None
    fallback_model: str | None = None
    candidates: Mapping[ModelFunction, tuple[str, ...]] = field(default_factory=dict)
    base_url: str = DEFAULT_BASE_URL
    data_collection: str = "deny"
    spend_category: SpendCategory = SpendCategory.DEV_EVAL
    call_estimate_usd: Decimal = Decimal("0.01")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> ModelConfig:
        """Build from env; ``AGENT_MODEL`` is required (no default model id)."""

        source = os.environ if env is None else env
        agent = (source.get("AGENT_MODEL") or "").strip()
        if not agent:
            raise ModelConfigError("AGENT_MODEL is required (no model id is hardcoded)")
        interpreter = (source.get("INTERPRETER_MODEL") or "").strip() or None
        answer = (source.get("ANSWER_MODEL") or "").strip() or None
        fallback = (source.get("FALLBACK_MODEL") or "").strip() or None
        candidates = {
            ModelFunction.INTERPRETATION: _split(source.get("INTERPRETER_MODEL_CANDIDATES"))
            or (interpreter or agent,),
            ModelFunction.TOOL_CALLING: _split(source.get("AGENT_MODEL_CANDIDATES")) or (agent,),
            ModelFunction.EXPLANATION: _split(source.get("ANSWER_MODEL_CANDIDATES"))
            or ((answer,) if answer else ()),
        }
        category = SpendCategory(source.get("SPEND_CATEGORY", "DEV_EVAL"))
        estimate = Decimal(source.get("MODEL_CALL_ESTIMATE_USD", "0.01"))
        privacy = source.get("OPENROUTER_DATA_COLLECTION", "deny")
        if privacy not in ("deny", "allow"):
            raise ModelConfigError("OPENROUTER_DATA_COLLECTION must be 'deny' or 'allow'")
        return cls(
            agent_model=agent,
            interpreter_model=interpreter,
            answer_model=answer,
            fallback_model=fallback,
            candidates=candidates,
            base_url=source.get("OPENROUTER_BASE_URL", DEFAULT_BASE_URL),
            data_collection=privacy,
            spend_category=category,
            call_estimate_usd=estimate,
        )

    def model_for(self, function: ModelFunction) -> str | None:
        """The single active model of a function (one call per function per turn)."""

        if function is ModelFunction.INTERPRETATION:
            return self.interpreter_model or self.agent_model
        if function is ModelFunction.TOOL_CALLING:
            return self.agent_model
        return self.answer_model

    def candidates_for(self, function: ModelFunction) -> tuple[str, ...]:
        """Configured candidates for Spec 6 to compare (never all called per turn)."""
        return tuple(self.candidates.get(function, ()))


@dataclass
class CapabilityRegistry:
    """Verified per-endpoint capabilities (from config or an endpoint probe)."""

    capabilities: dict[str, frozenset[Capability]] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> CapabilityRegistry:
        """Parse ``MODEL_CAPABILITIES`` = JSON ``{"model": ["tools", ...]}``."""

        source = os.environ if env is None else env
        raw = source.get("MODEL_CAPABILITIES")
        if not raw:
            return cls()
        parsed = json.loads(raw)
        return cls(
            capabilities={
                str(model): frozenset(Capability(c) for c in caps) for model, caps in parsed.items()
            }
        )

    def register(self, model: str, caps: frozenset[Capability]) -> None:
        """Record the verified capabilities of an exact endpoint."""
        self.capabilities[model] = caps

    def require(self, model: str, required: frozenset[Capability]) -> None:
        """Raise :class:`UnsupportedCapability` unless every feature is verified."""

        known = self.capabilities.get(model)
        if known is None:
            raise UnsupportedCapability("endpoint capabilities are not verified")
        if not required <= known:
            raise UnsupportedCapability("endpoint lacks a required capability")

    def supports_combined_phase(self, model: str) -> bool:
        """True iff the endpoint verifiably supports tools *and* structured output."""
        known = self.capabilities.get(model, frozenset())
        return {Capability.TOOLS, Capability.STRUCTURED_OUTPUT} <= known


def parse_openrouter_endpoints(payload: Mapping[str, object]) -> frozenset[Capability]:
    """Capabilities supported by **every** listed endpoint of a model.

    ``payload`` is the JSON of OpenRouter's ``/models/{id}/endpoints`` reply.
    Only features every endpoint supports are reported, so a provider fallback
    under ``require_parameters`` can never silently lose a capability.
    """

    data = payload.get("data")
    endpoints = data.get("endpoints", []) if isinstance(data, Mapping) else []
    common: set[Capability] | None = None
    for endpoint in endpoints if isinstance(endpoints, list) else []:
        params = set(endpoint.get("supported_parameters", []) or [])
        caps = set()
        if "tools" in params:
            caps.add(Capability.TOOLS)
        if "structured_outputs" in params or "response_format" in params:
            caps.add(Capability.STRUCTURED_OUTPUT)
        common = caps if common is None else common & caps
    return frozenset(common or ())


def resolve_phase_strategy(
    registry: CapabilityRegistry, interpreter_model: str, agent_model: str
) -> str:
    """Decide the phase layout (Req 11.3, 11.4).

    The interpretation phase (structured output) and the tool-invocation phase
    (native tools) are **separated** unless one endpoint verifiably supports
    both; this implementation always runs them as separate phases, and each
    phase's required capability is verified before its request, failing closed
    when absent.
    """

    registry.require(interpreter_model, REQUIRED_CAPABILITIES[ModelFunction.INTERPRETATION])
    registry.require(agent_model, REQUIRED_CAPABILITIES[ModelFunction.TOOL_CALLING])
    return "SEPARATED"


def request_options(required: frozenset[Capability], *, data_collection: str) -> dict[str, object]:
    """OpenRouter ``extra_body`` for a request.

    ``require_parameters`` is ``True`` whenever a feature is required, so the
    router only selects providers supporting every requested parameter and
    rejects the request otherwise; ``data_collection`` keeps the privacy
    requirement fixed across provider fallbacks; usage accounting is included.
    """

    return {
        "provider": {
            "require_parameters": bool(required),
            "allow_fallbacks": True,
            "data_collection": data_collection,
        },
        "usage": {"include": True},
    }


@dataclass(frozen=True, slots=True)
class RequestSpec:
    """The routing contract of one request: model + capabilities + privacy."""

    model: str
    required: frozenset[Capability]
    data_collection: str

    @property
    def extra_body(self) -> dict[str, object]:
        """The OpenRouter ``extra_body`` this spec implies."""
        return request_options(self.required, data_collection=self.data_collection)


def select_fallback(
    primary: RequestSpec, fallback_model: str | None, registry: CapabilityRegistry
) -> RequestSpec:
    """Return a fallback spec preserving capabilities + privacy, or abort."""

    if fallback_model is None:
        raise FallbackAborted("no fallback model configured")
    try:
        registry.require(fallback_model, primary.required)
    except UnsupportedCapability as exc:
        raise FallbackAborted("fallback cannot meet the required capabilities") from exc
    return RequestSpec(
        model=fallback_model, required=primary.required, data_collection=primary.data_collection
    )


@dataclass(frozen=True, slots=True)
class Usage:
    """Observed usage of one model call."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: Decimal | None = None
    provider: str | None = None

    @property
    def total_tokens(self) -> int:
        """Prompt plus completion tokens."""
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True, slots=True)
class ModelResult(Generic[T]):
    """A model call's value plus the spec it was served under."""

    value: T
    usage: Usage
    spec: RequestSpec


class QuotaSignal(Exception):
    """Raised by a call adapter when the provider reports 402 / quota."""


ModelCall = Callable[[RequestSpec], Awaitable[tuple[T, Usage]]]


class ModelGateway:
    """Every LLM call passes through here (budget, capability, ledger, retry)."""

    def __init__(
        self,
        config: ModelConfig,
        registry: CapabilityRegistry,
        ledger: CostLedger,
        *,
        retry: RetryPolicy | None = None,
    ) -> None:
        self._config = config
        self._registry = registry
        self._ledger = ledger
        self._retry = retry or RetryPolicy()
        self.calls: list[tuple[ModelFunction, str]] = []

    @property
    def config(self) -> ModelConfig:
        """The active model configuration."""
        return self._config

    async def call(
        self,
        function: ModelFunction,
        budget: BudgetTracker,
        invoke: ModelCall[T],
    ) -> ModelResult[T]:
        """Run one model call for ``function`` under every gate.

        Raises :class:`~series76_agent.domain.budget.BudgetExceeded`,
        :class:`UnsupportedCapability`, :class:`CostCapReached`,
        :class:`ProviderQuotaExceeded`, or :class:`ProviderUnavailableError`.
        """

        model = self._config.model_for(function)
        if model is None:
            raise UnsupportedCapability("no model configured for this function")
        primary = RequestSpec(
            model=model,
            required=REQUIRED_CAPABILITIES[function],
            data_collection=self._config.data_collection,
        )
        try:
            return await self._attempt(function, budget, primary, invoke)
        except ProviderUnavailableError:
            if self._config.fallback_model is None:
                raise
            try:
                fallback = select_fallback(primary, self._config.fallback_model, self._registry)
            except FallbackAborted as exc:
                raise ProviderUnavailableError("provider unavailable; fallback aborted") from exc
            return await self._attempt(function, budget, fallback, invoke)

    async def _attempt(
        self,
        function: ModelFunction,
        budget: BudgetTracker,
        spec: RequestSpec,
        invoke: ModelCall[T],
    ) -> ModelResult[T]:
        self._registry.require(spec.model, spec.required)
        self._ledger.authorize(self._config.spend_category, self._config.call_estimate_usd)
        budget.check_model_call(function)
        self.calls.append((function, spec.model))

        attempts = 0

        async def once() -> tuple[T, Usage]:
            nonlocal attempts
            attempts += 1
            if attempts > 1:
                # Every retry is another provider call and consumes budget.
                budget.check_model_call(function)
            try:
                return await invoke(spec)
            except QuotaSignal as exc:
                raise ProviderQuotaExceeded("provider quota exhausted") from exc

        try:
            value, usage = await retry_idempotent(
                once,
                policy=self._retry,
                can_continue=lambda: budget.exhausted is None,
            )
        except TransientError as exc:
            raise ProviderUnavailableError("provider unavailable") from exc
        cost = usage.cost_usd
        is_estimate = cost is None
        if cost is None:
            cost = self._config.call_estimate_usd
        self._ledger.record(
            LedgerEntry(
                provider=usage.provider or "unknown",
                model=spec.model,
                function=function.value,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                cost_usd=cost,
                category=self._config.spend_category,
                cost_is_estimate=is_estimate,
            )
        )
        budget.record_model_usage(tokens=usage.total_tokens, cost_usd=cost)
        return ModelResult(value=value, usage=usage, spec=spec)

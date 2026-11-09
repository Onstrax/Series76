"""Cost-gated model / tool-set A/B evaluation harness (Spec 6 Req 3, 1.6, 8.6).

Encodes *rules*, never *outcomes*: no model or tool-set winner is declared
anywhere in this repository. A result is emitted only when its
Evidence_Record exists. Expected scenario outputs are references to golden
dataset cells (never values written here, never produced by a model).

Live execution (Test_Level 7) is ``[EXPERIMENT]``: it needs the evaluator's
``OPENROUTER_API_KEY`` and runs strictly offline -> canary -> paired A/B under
the cumulative ledger (USD 10 cap, <= 6 dev/eval, >= 4 demo reserve).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from series76_agent.domain.enums import ModelFunction
from series76_agent.domain.ledger import CostCapReached, CostLedger, LedgerEntry, SpendCategory
from series76_eval.evidence import EvidenceStore, Result


class ScenarioFamily(str, Enum):
    EXACT_PN = "exact_pn"
    DUAL_SERVICE_FREQUENCY = "torque_dual_service_50_60hz"
    T03_NA = "t03_na_unattributed"
    SUPPLY_24V = "24v_ac_dc_vs_dc"
    BOOLEAN_RANGE = "boolean_range_filters"
    FOLLOWUP = "followups_corrections"
    RANKING_ABSTENTION = "ranking_abstention"
    INJECTION_IDOR = "prompt_injection_idor"


@dataclass(frozen=True, slots=True)
class Scenario:
    """A bilingual scenario. ``expected_cells`` are golden cell keys, never values."""

    id: str
    family: ScenarioFamily
    language: str
    input_template: str
    expected_cells: tuple[str, ...]
    expected_behavior: str
    critical: bool = True

    def __post_init__(self) -> None:
        if self.language not in ("es", "en"):
            raise ValueError("scenario language must be es or en")
        if any(ch.isdigit() for ch in self.expected_behavior):
            raise ValueError(
                "expected behavior must not carry a number (numbers come from the oracle)"
            )


class SuiteError(ValueError):
    """The scenario suite composition violates Req 3.2."""


def validate_suite(suite: Sequence[Scenario]) -> None:
    """34-38 scenarios, all eight families, ES and EN each 40-60%."""

    n = len(suite)
    if not 34 <= n <= 38:
        raise SuiteError(f"suite size {n} outside 34-38")
    missing = set(ScenarioFamily) - {s.family for s in suite}
    if missing:
        raise SuiteError(f"families without a scenario: {sorted(f.value for f in missing)}")
    es = sum(1 for s in suite if s.language == "es")
    if not (0.4 * n <= es <= 0.6 * n and 0.4 * n <= n - es <= 0.6 * n):
        raise SuiteError("ES/EN split outside 40-60%")
    if len({s.id for s in suite}) != n:
        raise SuiteError("scenario ids must be unique")


class Stage(str, Enum):
    OFFLINE = "offline"
    CANARY = "canary"
    PAIRED = "paired_ab"


class StageOrderError(RuntimeError):
    """A later stage was started before the prior one completed."""


@dataclass
class Staging:
    """Strict order offline -> canary -> paired A/B (Req 3.4)."""

    completed: list[Stage] = field(default_factory=list)
    started: list[Stage] = field(default_factory=list)

    _ORDER = (Stage.OFFLINE, Stage.CANARY, Stage.PAIRED)

    def start(self, stage: Stage) -> None:
        idx = self._ORDER.index(stage)
        for prior in self._ORDER[:idx]:
            if prior not in self.completed:
                raise StageOrderError(f"{stage.value} cannot start before {prior.value} completes")
        self.started.append(stage)

    def complete(self, stage: Stage) -> None:
        if stage not in self.started:
            raise StageOrderError(f"{stage.value} was never started")
        self.completed.append(stage)


@dataclass(frozen=True, slots=True)
class ModelProbe:
    """What was verified live about a candidate before any benchmark call."""

    identifier_ok: bool | None
    available: bool | None
    tool_calling: bool | None
    json_output: bool | None
    live_price_usd: Decimal | None


@dataclass(frozen=True, slots=True)
class Candidate:
    model_id: str
    function: ModelFunction
    tool_count: int = 1
    step_count: int = 1


@dataclass(frozen=True, slots=True)
class Exclusion:
    candidate: Candidate
    reason: str


def verify_candidate(candidate: Candidate, probe: ModelProbe | None) -> Exclusion | None:
    """Exclude (with a reason) any candidate not fully verified (Req 3.7)."""

    if probe is None:
        return Exclusion(candidate, "no live verification available")
    checks = (
        ("identifier", probe.identifier_ok),
        ("availability", probe.available),
        ("tool-calling", probe.tool_calling),
        ("json-output", probe.json_output),
    )
    for name, ok in checks:
        if ok is not True:
            return Exclusion(candidate, f"{name} not verified")
    if probe.live_price_usd is None or probe.live_price_usd < 0:
        return Exclusion(candidate, "live price not verified")
    return None


def candidates_ok(candidates: Sequence[Candidate]) -> bool:
    """At least two candidates per evaluated function (Req 3.1)."""
    return all(sum(1 for c in candidates if c.function is fn) >= 2 for fn in ModelFunction)


@dataclass(frozen=True, slots=True)
class PromotionGateResult:
    candidate: Candidate
    numeric_discrepancies: int
    authorization_leaks: int
    tool_param_validation_pct: Decimal
    missing_mandatory_scenarios: int

    @property
    def promotable(self) -> bool:
        return (
            self.numeric_discrepancies == 0
            and self.authorization_leaks == 0
            and self.tool_param_validation_pct == Decimal(100)
            and self.missing_mandatory_scenarios == 0
        )


@dataclass(frozen=True, slots=True)
class CandidateScore:
    candidate: Candidate
    critical_successes: int
    cost_usd: Decimal


def select(a: CandidateScore, b: CandidateScore) -> CandidateScore | None:
    """More critical successes wins (even if costlier); tie -> simpler; full tie -> none."""

    if a.critical_successes != b.critical_successes:
        return a if a.critical_successes > b.critical_successes else b
    ca = a.candidate.tool_count + a.candidate.step_count
    cb = b.candidate.tool_count + b.candidate.step_count
    if ca != cb:
        return a if ca < cb else b
    return None


@dataclass
class BudgetGate:
    """Cumulative ledger gate for dev/eval calls; the demo reserve is untouchable."""

    ledger: CostLedger
    suspended: bool = False

    def charge(self, provider: str, model: str, function: str, tokens: int, usd: Decimal) -> bool:
        """Authorize then record one dev/eval charge; ``False`` once suspended."""

        if self.suspended:
            return False
        try:
            self.ledger.authorize(SpendCategory.DEV_EVAL, usd)
        except CostCapReached:
            self.suspended = True  # suspend BEFORE any spend touches the reserve
            return False
        self.ledger.record(
            LedgerEntry(provider, model, function, tokens, 0, usd, SpendCategory.DEV_EVAL)
        )
        if self.ledger.remaining(SpendCategory.DEV_EVAL) <= 0:
            self.suspended = True
        return True

    @property
    def cumulative_usd(self) -> Decimal:
        return self.ledger.total_spent


@dataclass
class ABReport:
    """Results gated by evidence: nothing is reported without a persisted record."""

    store: EvidenceStore

    def result(self, claim_id: str) -> Result | None:
        record = self.store.latest(claim_id)
        return record.result if record is not None else None

    def winner(self, claim_id: str, scores: Sequence[CandidateScore]) -> Candidate | None:
        """A selection is reported only if a passing record backs this exact claim."""

        if self.result(claim_id) is not Result.PASSED or len(scores) != 2:
            return None
        chosen = select(scores[0], scores[1])
        return chosen.candidate if chosen is not None else None


@dataclass(frozen=True, slots=True)
class ServiceUnavailable:
    """Explicit fail-safe outcome (Req 8.6): no invented data, no reserve spend."""

    cause: str
    draft_preserved: bool = True
    history_preserved: bool = True
    reserve_spent: Decimal = Decimal(0)


def guarded_call(
    gate: BudgetGate,
    call: Callable[[], tuple[str, Decimal, int] | None],
    *,
    model: str,
    function: str,
    estimate: Decimal,
) -> str | ServiceUnavailable:
    """Run one live eval call only if the gate allows it; fail safe otherwise."""

    if gate.suspended:
        return ServiceUnavailable("evaluation budget exhausted")
    try:
        gate.ledger.authorize(SpendCategory.DEV_EVAL, estimate)
    except CostCapReached:
        gate.suspended = True  # suspended before the demo reserve is touched
        return ServiceUnavailable("evaluation budget exhausted")
    try:
        outcome = call()
    except Exception:  # noqa: BLE001 - any provider failure fails safe
        return ServiceUnavailable("model provider failure")
    if outcome is None:
        return ServiceUnavailable("model returned no usable response")
    text, usd, tokens = outcome
    # The observed charge is recorded truthfully, whatever it was.
    gate.ledger.record(
        LedgerEntry("openrouter", model, function, tokens, 0, usd, SpendCategory.DEV_EVAL)
    )
    if gate.ledger.remaining(SpendCategory.DEV_EVAL) <= 0:
        gate.suspended = True
    if not text.strip():
        return ServiceUnavailable("model returned no usable response")
    return text

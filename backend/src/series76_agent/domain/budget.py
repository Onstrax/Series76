"""``Turn_Budget`` and its fail-closed tracker (Req 1.8, 10.5, 11.6).

Every limit is checked **before** the guarded action. Once any limit is
reached the tracker becomes *exhausted* (sticky): every further model or tool
check raises :class:`BudgetExceeded`, so no further reasoning step or tool call
can be initiated for the turn, while results already produced are preserved by
the caller.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from series76_agent.domain.enums import ModelFunction


class BudgetLimit(str, Enum):
    """Which Turn_Budget limit was reached."""

    MODEL_CALLS = "max_model_calls_per_turn"
    TOOL_CALLS = "max_tool_calls_per_turn"
    TOKENS = "max_token_budget"
    WALLTIME = "max_walltime"
    COST = "max_cost_usd"
    RESULT_ROWS = "max_result_rows"


class BudgetExceeded(Exception):
    """A Turn_Budget limit was reached; the turn must stop fail-closed."""

    def __init__(self, limit: BudgetLimit) -> None:
        super().__init__(f"turn budget limit reached: {limit.value}")
        self.limit = limit


@dataclass(frozen=True, slots=True)
class TurnBudget:
    """Conservative, configurable per-turn limits (design § Turn_Budget)."""

    max_model_calls_per_turn: int = 4
    max_tool_calls_per_turn: int = 16
    max_token_budget: int = 24_000
    max_walltime_s: float = 60.0
    max_cost_usd: Decimal = Decimal("0.05")
    max_result_rows: int = 200

    def __post_init__(self) -> None:
        if isinstance(self.max_cost_usd, float):
            raise ValueError("max_cost_usd must be a Decimal, never a float")
        for name in (
            "max_model_calls_per_turn",
            "max_tool_calls_per_turn",
            "max_token_budget",
            "max_result_rows",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.max_walltime_s <= 0 or self.max_cost_usd < 0:
            raise ValueError("walltime must be positive and cost non-negative")

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> TurnBudget:
        """Read overrides from ``TURN_*`` environment variables."""

        source = os.environ if env is None else env
        default = cls()

        def _int(key: str, fallback: int) -> int:
            raw = source.get(key)
            return int(raw) if raw else fallback

        raw_cost = source.get("TURN_MAX_COST_USD")
        raw_wall = source.get("TURN_MAX_WALLTIME_S")
        return cls(
            max_model_calls_per_turn=_int("TURN_MAX_MODEL_CALLS", default.max_model_calls_per_turn),
            max_tool_calls_per_turn=_int("TURN_MAX_TOOL_CALLS", default.max_tool_calls_per_turn),
            max_token_budget=_int("TURN_MAX_TOKENS", default.max_token_budget),
            max_walltime_s=float(raw_wall) if raw_wall else default.max_walltime_s,
            max_cost_usd=Decimal(raw_cost) if raw_cost else default.max_cost_usd,
            max_result_rows=_int("TURN_MAX_RESULT_ROWS", default.max_result_rows),
        )


@dataclass
class BudgetTracker:
    """Tracks one turn's consumption against a :class:`TurnBudget`.

    ``clock`` returns monotonic seconds (injectable for deterministic tests).
    """

    budget: TurnBudget
    clock: Callable[[], float] = time.monotonic
    model_calls: int = 0
    tool_calls: int = 0
    tokens: int = 0
    cost_usd: Decimal = Decimal(0)
    result_rows: int = 0
    model_calls_by_function: dict[ModelFunction, int] = field(default_factory=dict)
    exhausted: BudgetLimit | None = None
    _started: float | None = None

    def __post_init__(self) -> None:
        self._started = self.clock()

    def _fail(self, limit: BudgetLimit) -> BudgetExceeded:
        if self.exhausted is None:
            self.exhausted = limit
        return BudgetExceeded(self.exhausted)

    def _check_common(self) -> None:
        if self.exhausted is not None:
            raise BudgetExceeded(self.exhausted)
        assert self._started is not None
        if self.clock() - self._started >= self.budget.max_walltime_s:
            raise self._fail(BudgetLimit.WALLTIME)
        if self.tokens >= self.budget.max_token_budget:
            raise self._fail(BudgetLimit.TOKENS)
        if self.cost_usd >= self.budget.max_cost_usd:
            raise self._fail(BudgetLimit.COST)

    def check_model_call(self, function: ModelFunction) -> None:
        """Authorize one model call or raise (no call may start once exhausted)."""

        self._check_common()
        if self.model_calls >= self.budget.max_model_calls_per_turn:
            raise self._fail(BudgetLimit.MODEL_CALLS)
        self.model_calls += 1
        self.model_calls_by_function[function] = self.model_calls_by_function.get(function, 0) + 1

    def record_model_usage(self, *, tokens: int, cost_usd: Decimal) -> None:
        """Account the observed usage of a completed model call."""

        if isinstance(cost_usd, float):
            raise ValueError("cost must be a Decimal")
        self.tokens += max(tokens, 0)
        self.cost_usd += max(cost_usd, Decimal(0))

    def check_tool_call(self) -> None:
        """Authorize one tool call or raise."""

        self._check_common()
        if self.tool_calls >= self.budget.max_tool_calls_per_turn:
            raise self._fail(BudgetLimit.TOOL_CALLS)
        self.tool_calls += 1

    def remaining_tool_calls(self) -> int:
        """How many tool calls can still be authorized."""
        if self.exhausted is not None:
            return 0
        return max(self.budget.max_tool_calls_per_turn - self.tool_calls, 0)

    def record_rows(self, rows: int) -> None:
        """Account returned catalog rows; raise when the row bound is crossed."""

        if self.exhausted is not None:
            raise BudgetExceeded(self.exhausted)
        if self.result_rows + rows > self.budget.max_result_rows:
            raise self._fail(BudgetLimit.RESULT_ROWS)
        self.result_rows += rows

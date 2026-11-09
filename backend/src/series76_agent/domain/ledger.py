"""The cumulative ``Cost_Ledger`` enforcing the USD 10 cap (Req 11.7, 11.8).

The ledger is **cumulative across every model and function** — never a quota
per model. Development/evaluation spend may reach at most USD 6.00; the final
demo has at least USD 4.00 reserved, and nothing may push total spend past
USD 10.00. A call is *authorized* against a conservative pre-call estimate
before it is issued; the observed cost is *recorded* truthfully afterwards
(the ledger never drops a real charge), and the cap check then blocks any
further call in that category.

Persistence is optional: with ``path`` set, entries are appended as JSON lines
so spend accumulates across processes/runs (Spec 6 reuses this file). Several
processes (api + worker) may share one file: every authorization re-reads it
under an exclusive file lock, so each cap check sees the spend recorded by the
others. Calls already in flight are bounded by their pre-call estimates; the
provider-side key credit limit remains the final backstop.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path

HARD_CAP_USD = Decimal("10.00")
DEV_EVAL_CAP_USD = Decimal("6.00")
DEMO_RESERVE_USD = Decimal("4.00")


class SpendCategory(str, Enum):
    """Which budget pool a call draws from."""

    DEV_EVAL = "DEV_EVAL"
    DEMO = "DEMO"


class CostCapReached(Exception):
    """A call would breach the dev/eval cap or the hard cap; it must not run."""


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One observed OpenRouter call (provider, model, usage, cost)."""

    provider: str
    model: str
    function: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: Decimal
    category: SpendCategory
    cost_is_estimate: bool = False
    at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if isinstance(self.cost_usd, float):
            raise ValueError("cost_usd must be a Decimal")
        if self.cost_usd < 0:
            raise ValueError("cost_usd must be non-negative")


@dataclass
class CostLedger:
    """Cumulative spend ledger with the 10 / 6 / 4 policy encoded as data."""

    hard_cap_usd: Decimal = HARD_CAP_USD
    dev_eval_cap_usd: Decimal = DEV_EVAL_CAP_USD
    demo_reserve_usd: Decimal = DEMO_RESERVE_USD
    path: Path | None = None
    entries: list[LedgerEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        if self.dev_eval_cap_usd + self.demo_reserve_usd > self.hard_cap_usd:
            raise ValueError("dev/eval cap plus demo reserve cannot exceed the hard cap")
        if self.path is not None and self.path.exists():
            self.entries[:] = self._read_file()

    def _read_file(self) -> list[LedgerEntry]:
        assert self.path is not None
        if not self.path.exists():
            return []
        return [
            _entry_from_json(json.loads(line))
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    @contextlib.contextmanager
    def _file_lock(self) -> Iterator[None]:
        """Exclusive cross-process lock on ``<path>.lock`` (no-op without a path)."""

        if self.path is None:
            yield
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.with_suffix(self.path.suffix + ".lock").open("a") as fh:
            try:
                import fcntl

                fcntl.flock(fh, fcntl.LOCK_EX)
            except ImportError:  # pragma: no cover - non-POSIX: thread lock only
                pass
            yield

    # --- totals ------------------------------------------------------------

    @property
    def total_spent(self) -> Decimal:
        """Cumulative spend across every model, function, and category."""
        return sum((e.cost_usd for e in self.entries), Decimal(0))

    @property
    def dev_eval_spent(self) -> Decimal:
        """Cumulative development/evaluation spend."""
        return sum(
            (e.cost_usd for e in self.entries if e.category is SpendCategory.DEV_EVAL),
            Decimal(0),
        )

    def remaining(self, category: SpendCategory) -> Decimal:
        """How much may still be spent in ``category`` without breaching a cap."""

        hard_room = self.hard_cap_usd - self.total_spent
        if category is SpendCategory.DEV_EVAL:
            dev_room = self.dev_eval_cap_usd - self.dev_eval_spent
            return max(min(dev_room, hard_room), Decimal(0))
        return max(hard_room, Decimal(0))

    # --- gate ----------------------------------------------------------------

    def authorize(self, category: SpendCategory, estimated_cost_usd: Decimal) -> None:
        """Raise :class:`CostCapReached` if a call of this estimate would breach.

        Dev/eval calls are blocked once dev/eval spend reaches USD 6.00, which
        keeps the USD 4.00 demo reserve intact (Req 11.8).
        """

        if isinstance(estimated_cost_usd, float):
            raise ValueError("estimate must be a Decimal")
        with self._lock, self._file_lock():
            if self.path is not None:
                self.entries[:] = self._read_file()  # spend recorded by other processes
            if self.remaining(category) <= 0:
                raise CostCapReached(f"{category.value} budget exhausted")
            if estimated_cost_usd > self.remaining(category):
                raise CostCapReached(f"{category.value} call would breach the cap")

    def record(self, entry: LedgerEntry) -> None:
        """Record an observed charge truthfully (never dropped)."""

        with self._lock, self._file_lock():
            self.entries.append(entry)
            if self.path is not None:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(_entry_to_json(entry)) + "\n")


def _entry_to_json(entry: LedgerEntry) -> dict[str, object]:
    raw = asdict(entry)
    raw["cost_usd"] = str(entry.cost_usd)
    raw["category"] = entry.category.value
    return raw


def _entry_from_json(raw: dict[str, object]) -> LedgerEntry:
    return LedgerEntry(
        provider=str(raw["provider"]),
        model=str(raw["model"]),
        function=str(raw["function"]),
        prompt_tokens=int(str(raw["prompt_tokens"])),
        completion_tokens=int(str(raw["completion_tokens"])),
        cost_usd=Decimal(str(raw["cost_usd"])),
        category=SpendCategory(str(raw["category"])),
        cost_is_estimate=bool(raw.get("cost_is_estimate", False)),
        at=str(raw.get("at", "")),
    )

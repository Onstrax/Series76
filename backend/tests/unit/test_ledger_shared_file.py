"""Two processes sharing one ledger file see each other's spend at authorization."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from series76_agent.domain.ledger import CostCapReached, CostLedger, LedgerEntry, SpendCategory


def _charge(ledger: CostLedger, usd: str) -> None:
    ledger.record(
        LedgerEntry("openrouter", "m/x", "TOOL_CALLING", 1, 1, Decimal(usd), SpendCategory.DEV_EVAL)
    )


def test_shared_file_caps_across_instances(tmp_path: Path) -> None:
    path = tmp_path / "ledger.jsonl"
    api, worker = CostLedger(path=path), CostLedger(path=path)  # as two processes would
    _charge(api, "3.50")
    _charge(worker, "2.40")
    api.authorize(SpendCategory.DEV_EVAL, Decimal("0.10"))  # 5.90 + 0.10 = 6.00 ok
    assert api.dev_eval_spent == Decimal("5.90")  # refreshed from the shared file
    with pytest.raises(CostCapReached):
        worker.authorize(SpendCategory.DEV_EVAL, Decimal("0.11"))  # would pass 6.00
    worker.authorize(SpendCategory.DEMO, Decimal("4.00"))  # the demo reserve is intact
    assert CostLedger(path=path).total_spent == Decimal("5.90")

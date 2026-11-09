"""The live A/B runner's binding and scoring, on the audited golden dataset.

No call is made: envelopes are built here from golden values, so these tests
pin the scoring rules (a drifted or invented number fails; a missing expected
figure fails; N/A shown as a number fails) without asserting any model result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from series76_eval.ab_live import (
    bind_roles,
    check_turn,
    golden_rows,
    render,
    score,
)
from series76_eval.scenarios import SCENARIOS

GOLDEN = Path(__file__).resolve().parents[2] / "data" / "golden" / "golden_dataset.json"

pytestmark = pytest.mark.skipif(not GOLDEN.exists(), reason="no audited golden dataset")


@pytest.fixture(scope="module")
def doc() -> dict[str, Any]:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


def _fig(pn: str, metric: str, value: str, service: str | None = None,
         hz: str | None = None, status: str = "AVAILABLE") -> dict[str, Any]:
    return {"part_number": pn, "metric_key": metric, "value": value, "service": service,
            "frequency_hz": hz, "status": status}


def _result(scenario_id: str, response: dict[str, Any], status: str = "COMPLETED"
            ) -> dict[str, Any]:
    return {"scenario": scenario_id, "turns": [{"status": status, "response": response}]}


def test_roles_bind_to_golden_part_numbers_and_printed_thresholds(doc: dict[str, Any]) -> None:
    rows = golden_rows(doc)
    b = bind_roles(rows)
    for role in ("dual", "freq", "t03", "acdc", "dc"):
        assert b.pns[role] in rows
    assert b.pns["unlisted"] not in rows
    assert rows[b.pns["t03"]].cells["unq.torque_inlbs"] == "N/A"
    printed = {v for r in rows.values() for v in r.cells.values()}
    assert b.nums["a"] in printed and b.nums["b"] in printed
    for s in SCENARIOS:
        assert all("{" not in t for t in render(s.input_template, b))


def test_exact_lookup_scores_and_a_drifted_number_fails(doc: dict[str, Any]) -> None:
    rows = golden_rows(doc)
    b = bind_roles(rows)
    s01 = next(s for s in SCENARIOS if s.id == "S06")  # both services of {pn:dual}
    pn = b.pns["dual"]
    row = rows[pn]
    good = {"content_blocks": [{"kind": "product_card", "part_number": pn, "fields": {},
                                "figures": [
        _fig(pn, "torque_inlbs", row.cells["onoff.torque_inlbs"].replace(",", ""), "On/Off"),
        _fig(pn, "torque_inlbs", row.cells["mod.torque_inlbs"].replace(",", ""), "Modulating"),
    ]}]}
    ok = score(_result("S06", good), s01, b, rows, doc["edition_id"])
    assert ok.success, ok.notes

    drifted = json.loads(json.dumps(good))
    drifted["content_blocks"][0]["figures"][0]["value"] = "1"
    bad = score(_result("S06", drifted), s01, b, rows, doc["edition_id"])
    assert not bad.fidelity and not bad.success

    missing = json.loads(json.dumps(good))
    missing["content_blocks"][0]["figures"].pop()
    assert not score(_result("S06", missing), s01, b, rows, doc["edition_id"]).expected


def test_na_shown_as_a_number_fails_and_unknown_parts_fail(doc: dict[str, Any]) -> None:
    rows = golden_rows(doc)
    b = bind_roles(rows)
    s10 = next(s for s in SCENARIOS if s.id == "S10")
    t03 = b.pns["t03"]
    na = {"content_blocks": [{"kind": "product_card", "part_number": t03, "fields": {},
                              "figures": [_fig(t03, "torque_inlbs", "", status="NOT_APPLICABLE")]}]}
    assert score(_result("S10", na), s10, b, rows, doc["edition_id"]).success
    zero = {"content_blocks": [{"kind": "product_card", "part_number": t03, "fields": {},
                                "figures": [_fig(t03, "torque_inlbs", "0")]}]}
    assert not score(_result("S10", zero), s10, b, rows, doc["edition_id"]).success

    ghost = {"content_blocks": [{"kind": "matching_part_numbers",
                                 "part_numbers": ["799Q99-00000000/A"]}]}
    assert check_turn(ghost, rows).unknown_parts == ["799Q99-00000000/A"]


def test_card_fields_may_only_show_printed_numbers(doc: dict[str, Any]) -> None:
    rows = golden_rows(doc)
    pn = bind_roles(rows).pns["dual"]
    row = rows[pn]
    card = {"content_blocks": [{"kind": "product_card", "part_number": pn, "figures": [],
                                "fields": {"motor power": f"{row.cells['config.motor_power_w']} W",
                                           "nominal voltage": "110 V"}}]}
    assert check_turn(card, rows).numeric_discrepancies == []
    card["content_blocks"][0]["fields"]["invented"] = "12345 W"  # type: ignore[index]
    assert check_turn(card, rows).numeric_discrepancies


def test_a_failed_turn_never_scores(doc: dict[str, Any]) -> None:
    rows = golden_rows(doc)
    b = bind_roles(rows)
    s33 = next(s for s in SCENARIOS if s.id == "S33")
    assert not score(_result("S33", {}, status="FAILED"), s33, b, rows, doc["edition_id"]).success
    leaky = {"answer": "Sure: SELECT * FROM catalog.part_number"}
    res = score(_result("S33", leaky), s33, b, rows, doc["edition_id"])
    assert res.authorization_leak and not res.success


def _report(label: str, varied: str | None, models: dict[str, str], ok: int,
            discrepancy: bool = False, used: dict[str, list[str]] | None = None) -> Any:
    from decimal import Decimal

    from series76_eval.ab_live import ConfigReport, LiveConfig, ScenarioScore

    scores = tuple(
        ScenarioScore(f"S{i:02d}", "lookup", True, not (discrepancy and i == 0), True, i < ok,
                      ("x",) if discrepancy and i == 0 else (), False, ())
        for i in range(36))
    return ConfigReport(LiveConfig(label, varied, models), scores, Decimal("0.01"),
                        used or {fn: [m] for fn, m in models.items()}, 4.0)


def test_one_factor_configs_and_selection_rules() -> None:
    from series76_eval.ab_live import choose, plan_configs

    configs = plan_configs("m/base", {"INTERPRETATION": ["m/base", "m/x"],
                                      "TOOL_CALLING": ["m/base", "m/y", "m/z"]})
    assert [c.label for c in configs] == ["baseline", "interpretation=m/x",
                                          "tool_calling=m/y", "tool_calling=m/z"]
    assert configs[2].models == {"INTERPRETATION": "m/base", "TOOL_CALLING": "m/y"}

    base = {"INTERPRETATION": "m/base", "TOOL_CALLING": "m/base"}
    reports = [
        _report("baseline", None, base, 30),
        _report("interpretation=m/x", "INTERPRETATION", {**base, "INTERPRETATION": "m/x"}, 33),
        _report("tool_calling=m/y", "TOOL_CALLING", {**base, "TOOL_CALLING": "m/y"}, 30),
        _report("tool_calling=m/z", "TOOL_CALLING", {**base, "TOOL_CALLING": "m/z"}, 35,
                discrepancy=True),
    ]
    assert choose("INTERPRETATION", reports)[0] == "m/x"
    model, why = choose("TOOL_CALLING", reports)  # m/z fails the gate; base and y tie
    assert model is None and "tie" in why

    wrong = _report("interpretation=m/x", "INTERPRETATION", {**base, "INTERPRETATION": "m/x"},
                    36, used={"INTERPRETATION": ["m/base"]})  # ledger: config not applied
    assert choose("INTERPRETATION", [reports[0], wrong])[0] == "m/base"


def test_ledger_delta_and_env_rewrite() -> None:
    from decimal import Decimal

    from series76_eval.ab_live import env_with, ledger_delta

    before = [{"cost_usd": "1", "function": "TOOL_CALLING", "model": "a"}]
    after = [*before, {"cost_usd": "0.25", "function": "TOOL_CALLING", "model": "b"},
             {"cost_usd": "0.5", "function": "INTERPRETATION", "model": "c"}]
    spent, used = ledger_delta(before, after)
    assert spent == Decimal("0.75") and used == {"TOOL_CALLING": {"b"}, "INTERPRETATION": {"c"}}
    text = "A=1\nAGENT_MODEL=old\n# c\n"
    assert env_with(text, {"AGENT_MODEL": "new", "X": "2"}) == "A=1\nAGENT_MODEL=new\n# c\nX=2\n"

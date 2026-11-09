"""Spec 6 Properties 11-18 and 40: cost-gated A/B harness logic (fakes, zero spend)."""

from __future__ import annotations

import random
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from series76_agent.domain.enums import ModelFunction
from series76_agent.domain.ledger import (
    DEMO_RESERVE_USD,
    DEV_EVAL_CAP_USD,
    CostLedger,
    SpendCategory,
)
from series76_eval.ab import (
    ABReport,
    BudgetGate,
    Candidate,
    CandidateScore,
    ModelProbe,
    PromotionGateResult,
    Scenario,
    ScenarioFamily,
    ServiceUnavailable,
    Stage,
    StageOrderError,
    Staging,
    SuiteError,
    candidates_ok,
    guarded_call,
    select,
    validate_suite,
    verify_candidate,
)
from series76_eval.evidence import EvidenceRecord, EvidenceStore, Result
from series76_eval.scenarios import SCENARIOS

usd = st.decimals(min_value=Decimal("0.001"), max_value=Decimal("1.5"), places=3)


# Feature: evaluation-and-reproducibility, Property 11: At least two candidates per function on identical A/B scenarios
@given(
    counts=st.dictionaries(st.sampled_from(list(ModelFunction)), st.integers(0, 3)),
    seed=st.integers(0, 999),
)
def test_property_11_two_candidates_identical_scenarios(counts, seed) -> None:  # type: ignore[no-untyped-def]
    cands = [Candidate(f"m/{fn.value}-{i}", fn) for fn, n in counts.items() for i in range(n)]
    expected = all(counts.get(fn, 0) >= 2 for fn in ModelFunction)
    assert candidates_ok(cands) == expected
    # Tool_Set_A and Tool_Set_B receive the very same scenario objects.
    for_a = list(SCENARIOS)
    for_b = list(SCENARIOS)
    random.Random(seed).shuffle(for_b)
    key = lambda s: (s.id, s.input_template, s.expected_cells)  # noqa: E731
    assert sorted(map(key, for_a)) == sorted(map(key, for_b))


fams = st.sampled_from(list(ScenarioFamily))


# Feature: evaluation-and-reproducibility, Property 12: Scenario suite composition is well-formed
@given(n=st.integers(30, 42), es_ratio=st.floats(0.2, 0.8), drop=st.one_of(st.none(), fams))
def test_property_12_suite_composition(n: int, es_ratio: float, drop) -> None:  # type: ignore[no-untyped-def]
    validate_suite(SCENARIOS)  # the shipped suite is well formed
    families = [f for f in ScenarioFamily if f is not drop]
    es = round(n * es_ratio)
    suite = [
        Scenario(f"X{i}", families[i % len(families)], "es" if i < es else "en", "q", (), "lookup")
        for i in range(n)
    ]
    ok = 34 <= n <= 38 and drop is None and 0.4 * n <= es <= 0.6 * n
    if ok:
        validate_suite(suite)
    else:
        with pytest.raises(SuiteError):
            validate_suite(suite)


# Feature: evaluation-and-reproducibility, Property 13: Strict staging order is enforced
@given(order=st.lists(st.sampled_from(list(Stage)), min_size=1, max_size=6))
def test_property_13_staging_order(order: list[Stage]) -> None:
    staging = Staging()
    seq = (Stage.OFFLINE, Stage.CANARY, Stage.PAIRED)
    for stage in order:
        allowed = all(p in staging.completed for p in seq[: seq.index(stage)])
        if allowed:
            staging.start(stage)
            staging.complete(stage)
        else:
            with pytest.raises(StageOrderError):
                staging.start(stage)
    for i, stage in enumerate(staging.started):
        for prior in seq[: seq.index(stage)]:
            assert prior in staging.completed[: i + 1] or prior in staging.completed


# Feature: evaluation-and-reproducibility, Property 14: Cumulative ledger preserves the demo reserve
@given(charges=st.lists(st.tuples(st.sampled_from(["m/a", "m/b", "m/c"]), usd), max_size=40))
def test_property_14_ledger_reserve(charges) -> None:  # type: ignore[no-untyped-def]
    gate = BudgetGate(CostLedger())
    total = Decimal(0)
    for model, cost in charges:
        if gate.charge("openrouter", model, "TOOL_CALLING", 10, cost):
            total += cost
        assert gate.ledger.dev_eval_spent <= DEV_EVAL_CAP_USD
    assert gate.cumulative_usd == total  # cumulative, across every model
    assert gate.ledger.remaining(SpendCategory.DEMO) >= DEMO_RESERVE_USD
    if gate.suspended:
        frozen = gate.cumulative_usd
        assert not gate.charge("openrouter", "m/a", "TOOL_CALLING", 1, Decimal("0.001"))
        assert gate.cumulative_usd == frozen  # totals retained at suspension


probe_field = st.one_of(st.none(), st.booleans())


# Feature: evaluation-and-reproducibility, Property 15: Unverifiable models are excluded before any benchmark call
@given(
    idok=probe_field,
    avail=probe_field,
    tools=probe_field,
    js=probe_field,
    price=st.one_of(st.none(), usd),
    missing=st.booleans(),
)
def test_property_15_unverifiable_excluded(idok, avail, tools, js, price, missing) -> None:  # type: ignore[no-untyped-def]
    cand = Candidate("m/x", ModelFunction.TOOL_CALLING)
    probe = None if missing else ModelProbe(idok, avail, tools, js, price)
    calls: list[str] = []
    exclusion = verify_candidate(cand, probe)
    if exclusion is None:
        calls.append(cand.model_id)  # only now may a benchmark call happen
    verified = (
        not missing and all(x is True for x in (idok, avail, tools, js)) and price is not None
    )
    assert (exclusion is None) == verified
    if exclusion is not None:
        assert exclusion.reason and calls == []


# Feature: evaluation-and-reproducibility, Property 16: Promotion gate is the conjunction of all four conditions
@given(
    num=st.integers(0, 2),
    leaks=st.integers(0, 2),
    pct=st.sampled_from([Decimal(100), Decimal("99.9"), Decimal(0)]),
    missing=st.integers(0, 2),
)
def test_property_16_promotion_gate(num, leaks, pct, missing) -> None:  # type: ignore[no-untyped-def]
    r = PromotionGateResult(
        Candidate("m/x", ModelFunction.INTERPRETATION), num, leaks, pct, missing
    )
    assert r.promotable == (num == 0 and leaks == 0 and pct == 100 and missing == 0)


# Feature: evaluation-and-reproducibility, Property 17: Selection prefers critical-case success, then simplicity
@given(
    ca=st.integers(0, 36),
    cb=st.integers(0, 36),
    costa=usd,
    costb=usd,
    ta=st.integers(1, 4),
    tb=st.integers(1, 4),
)
def test_property_17_selection_rule(ca, cb, costa, costb, ta, tb) -> None:  # type: ignore[no-untyped-def]
    a = CandidateScore(Candidate("m/a", ModelFunction.TOOL_CALLING, ta, 1), ca, costa)
    b = CandidateScore(Candidate("m/b", ModelFunction.TOOL_CALLING, tb, 1), cb, costb)
    chosen = select(a, b)
    if ca != cb:
        assert chosen is (a if ca > cb else b)  # even when the winner costs more
    elif ta != tb:
        assert chosen is (a if ta < tb else b)
    else:
        assert chosen is None  # no fabricated winner on a full tie


# Feature: evaluation-and-reproducibility, Property 18: No result without an Evidence_Record; no fabrication
@given(has_record=st.booleans(), passed=st.booleans(), ca=st.integers(0, 5), cb=st.integers(0, 5))
def test_property_18_no_result_without_evidence(
    has_record, passed, ca, cb, tmp_path_factory
) -> None:  # type: ignore[no-untyped-def]
    store = EvidenceStore(Path(tmp_path_factory.mktemp("ev")) / "e.jsonl")
    if has_record:
        store.persist(
            EvidenceRecord(
                "ab:tool-set",
                "pytest x",
                "2026-11-09T00:00:00Z",
                "abc123",
                "linux",
                Result.PASSED if passed else Result.FAILED,
                "ok",
                3 if passed else 2,
                3,
                passed,
                "fixture",
                Decimal("0"),
            )
        )
    report = ABReport(store)
    scores = [
        CandidateScore(Candidate("A", ModelFunction.TOOL_CALLING), ca, Decimal(0)),
        CandidateScore(Candidate("B", ModelFunction.TOOL_CALLING, 2, 1), cb, Decimal(0)),
    ]
    winner = report.winner("ab:tool-set", scores)
    if not (has_record and passed):
        assert winner is None
    assert report.result("never-run") is None
    # The repository itself declares no winner anywhere.
    src = Path(__file__).resolve().parents[2] / "src" / "series76_eval"
    for path in src.rglob("*.py"):
        assert "WINNER =" not in path.read_text(encoding="utf-8")


# Feature: evaluation-and-reproducibility, Property 40: Model failure or budget exhaustion fails safe
@given(mode=st.sampled_from(["ok", "raise", "none", "empty", "exhausted"]), cost=usd)
def test_property_40_fail_safe(mode: str, cost: Decimal) -> None:
    ledger = CostLedger()
    gate = BudgetGate(ledger)
    if mode == "exhausted":
        gate.suspended = True

    def call() -> tuple[str, Decimal, int] | None:
        if mode == "raise":
            raise RuntimeError("provider down")
        if mode == "none":
            return None
        return ("" if mode == "empty" else "an answer", cost, 10)

    out = guarded_call(gate, call, model="m/x", function="TOOL_CALLING", estimate=Decimal("0.01"))
    if mode == "ok":
        assert out == "an answer"
    else:
        assert isinstance(out, ServiceUnavailable)
        assert out.cause and out.draft_preserved and out.history_preserved
        assert out.reserve_spent == 0  # never the demo reserve, never invented data
    assert ledger.remaining(SpendCategory.DEMO) >= DEMO_RESERVE_USD

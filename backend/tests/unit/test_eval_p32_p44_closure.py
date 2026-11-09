"""Spec 6 Properties 32, 36-39, 41-44: honesty, integrity, release gate, traceability."""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from series76_eval.evidence import (
    EvidenceError,
    EvidenceRecord,
    EvidenceStore,
    HonestyPolicy,
    Result,
    redact,
)
from series76_eval.qa import UI_STATES, ui_state_coverage
from series76_eval.repro import ArtifactRejected, check_config_artifact, guarded_ingest
from series76_eval.traceability import (
    SPECS,
    CriticalCategory,
    Defect,
    ReleaseGateRecord,
    Status,
    TraceabilityRow,
    build_artifact,
    classify,
    obligations,
)

REPO = Path(__file__).resolve().parents[3]


# Feature: evaluation-and-reproducibility, Property 32: Every documented UiState is reachable and complete
@given(state=st.sampled_from(sorted(UI_STATES)))
def test_property_32_every_ui_state_is_produced(state: str) -> None:
    # Static reachability over the client sources; rendering on a device is
    # verified by the emulator flows (recorded separately as Evidence_Records).
    coverage = ui_state_coverage(REPO / "android" / "app" / "src" / "main")
    assert len(coverage) == 13
    assert coverage[state], f"UiState {state} is not produced by the client"


# Feature: evaluation-and-reproducibility, Property 36: Artifact hash mismatch rejects the artifact
@given(
    data=st.binary(min_size=1, max_size=512),
    tamper=st.booleans(),
    name=st.sampled_from(["series_76_electric_data.pdf", "verified_replay/manifest.json"]),
)
def test_property_36_hash_mismatch_rejects(data: bytes, tamper: bool, name: str) -> None:
    trusted = hashlib.sha256(data).hexdigest()
    delivered = data + b"\x00" if tamper else data
    ingested: list[bytes] = []
    if tamper:
        with pytest.raises(ArtifactRejected) as err:
            guarded_ingest(name, delivered, trusted, ingested.append)
        assert name in str(err.value)  # the mismatched artifact is identified
        assert ingested == []  # never published or ingested
    else:
        assert guarded_ingest(name, delivered, trusted, ingested.append).accepted
        assert ingested == [data]


fields = st.fixed_dictionaries(
    {
        "claim_id": st.sampled_from(["level:unit", "", "ab:tool-set"]),
        "command": st.sampled_from(["pytest tests/unit", " "]),
        "commit": st.sampled_from(["abc1234", ""]),
        "environment": st.sampled_from(["linux py3.12", ""]),
        "known_limits": st.sampled_from(["fakes only", ""]),
    }
)


# Feature: evaluation-and-reproducibility, Property 37: Every passed claim carries a complete Evidence_Record
@given(
    f=fields,
    n=st.integers(0, 50),
    d=st.integers(-1, 50),
    cost=st.decimals(-1, 5, places=3),
    log=st.sampled_from(["12 passed", "token=abc123456789 leaked", "ok"]),
)
def test_property_37_complete_record(f, n, d, cost, log, tmp_path_factory) -> None:  # type: ignore[no-untyped-def]
    complete = all(str(v).strip() for v in f.values())
    valid = complete and d > 0 and 0 <= n <= d and cost >= 0 and redact(log) == log and n == d
    kwargs = dict(
        f,
        date="2026-11-09T00:00:00Z",
        result=Result.PASSED,
        sanitized_log=log,
        case_count=n,
        denominator=d,
        no_critical_defects=True,
        cumulative_cost_usd=cost,
    )
    if not valid:
        with pytest.raises(EvidenceError):
            EvidenceRecord(**kwargs)
        return
    store = EvidenceStore(Path(tmp_path_factory.mktemp("ev")) / "e.jsonl")
    record = store.persist(EvidenceRecord(**kwargs))
    again = EvidenceStore(store.path).latest(record.claim_id)  # persisted, round-trips
    assert again == record and again.coverage() == f"{n}/{d}"


# Feature: evaluation-and-reproducibility, Property 38: Coverage is always a numerator over an explicit denominator
@given(
    n=st.integers(-2, 80),
    d=st.integers(-1, 80),
    basis=st.sampled_from(
        [
            "golden-rows-as-semantic",
            "scenarios-as-semantic",
            "code-lines-as-data",
            "golden-rows",
            "scenarios",
        ]
    ),
)
def test_property_38_coverage_has_denominator(n: int, d: int, basis: str, tmp_path: Path) -> None:
    verdict = HonestyPolicy(EvidenceStore(tmp_path / "e.jsonl")).check_coverage_claim(n, d, basis)
    well_formed = d > 0 and 0 <= n <= d
    forbidden = basis == "code-lines-as-data" or (basis.endswith("-as-semantic") and n == d)
    assert verdict.accepted == (well_formed and not forbidden)
    if verdict.accepted:
        assert f"{n}/{d}" in verdict.reason


# Feature: evaluation-and-reproducibility, Property 39: Release gate requires zero known critical defects
@given(
    defects=st.lists(
        st.tuples(st.sampled_from(list(CriticalCategory)), st.text(min_size=1, max_size=8)),
        max_size=6,
    )
)
def test_property_39_release_gate(defects: list[tuple[CriticalCategory, str]]) -> None:
    gate = ReleaseGateRecord(tuple(Defect(c, s) for c, s in defects))
    assert gate.releasable == (not defects)
    for category in CriticalCategory:
        hit = any(c is category for c, _ in defects)
        assert gate.state(category) == ("defect" if hit else "clear")
    assert {d.scope for d in gate.recorded_defects} == {
        s for _, s in defects
    }  # each with its scope


# Feature: evaluation-and-reproducibility, Property 41: Evidence-less passed claims are rejected
@given(
    claim=st.text(alphabet="abcdefgh:-", min_size=1, max_size=12),
    stored=st.booleans(),
    passed=st.booleans(),
)
def test_property_41_evidence_less_rejected(
    claim: str, stored: bool, passed: bool, tmp_path_factory
) -> None:  # type: ignore[no-untyped-def]
    store = EvidenceStore(Path(tmp_path_factory.mktemp("ev")) / "e.jsonl")
    if stored:
        store.persist(
            EvidenceRecord(
                claim,
                "pytest",
                "2026-11-09",
                "abc",
                "linux",
                Result.PASSED if passed else Result.FAILED,
                "log",
                1 if passed else 0,
                1,
                passed,
                "none",
                Decimal(0),
            )
        )
    policy = HonestyPolicy(store)
    verdict = policy.assert_honest(claim, Result.PASSED)
    assert verdict.accepted == (stored and passed)
    assert (claim in policy.missing_evidence) == (not stored)  # the condition is recorded


def _spec_tree(root: Path, mapping: dict[str, tuple[set[str], bool]]) -> None:
    """Write six minimal specs: item -> (specs tracing it, whether a task implements it)."""

    for spec in SPECS:
        reqs, tasks = [], []
        for n, (item, (specs, has_task)) in enumerate(sorted(mapping.items()), start=1):
            if spec in specs:
                reqs.append(
                    f"### Requirement {n}: r\n\n*(Traces: {item}.)*\n\n#### Acceptance Criteria\n"
                )
                if has_task:
                    tasks.append(f"- [ ] {n}. t\n  - _Requirements: {n}.1_\n")
        (root / spec).mkdir(parents=True)
        (root / spec / "requirements.md").write_text("\n".join(reqs) or "none\n", encoding="utf-8")
        (root / spec / "tasks.md").write_text("\n".join(tasks) or "none\n", encoding="utf-8")


item_map = st.dictionaries(
    st.sampled_from(obligations()),
    st.tuples(st.sets(st.sampled_from(SPECS), max_size=3), st.booleans()),
    min_size=1,
    max_size=12,
)


# Feature: evaluation-and-reproducibility, Property 42: Every obligation is mapped across all six specs
@given(mapping=item_map)
def test_property_42_every_obligation_mapped(mapping, tmp_path_factory) -> None:  # type: ignore[no-untyped-def]
    root = Path(tmp_path_factory.mktemp("specs"))
    _spec_tree(root, mapping)
    artifact = build_artifact(root, items=sorted(mapping))
    assert [r.item_id for r in artifact.rows] == sorted(mapping)  # no item absent
    for row in artifact.rows:
        specs, has_task = mapping[row.item_id]
        mapped = bool(specs) and has_task
        assert (row.status is Status.GAP) == (not mapped)
        if mapped:
            assert set(row.specs) == specs and row.tasks


def test_property_42_real_specs_have_no_gap() -> None:
    # F3-AT10/F3-AT11 were traced into Spec 5 Req 9 and Spec 4 Req 10 (owner decision D1).
    artifact = build_artifact(REPO / ".kiro" / "specs")
    assert len(artifact.rows) == len(obligations()) == 109
    assert [r.item_id for r in artifact.by_status(Status.GAP)] == []


# Feature: evaluation-and-reproducibility, Property 43: Mapped items are pending or gap, never both
@given(
    specs=st.lists(st.sampled_from(SPECS), max_size=3, unique=True),
    tasks=st.lists(st.text(alphabet="0123456789.", min_size=1, max_size=4), max_size=3),
    ev=st.one_of(st.none(), st.just("docs/evidence/evidence.jsonl#level:unit")),
)
def test_property_43_pending_gap_exclusive(
    specs: list[str], tasks: list[str], ev: str | None
) -> None:
    s, t = tuple(specs), tuple(tasks)
    status = classify(s, t, ev)
    mapped = bool(s) and bool(t)
    assert (status is Status.GAP) == (not mapped)
    assert (status is Status.PENDING) == (mapped and ev is None)
    TraceabilityRow("X", s, t, ev, status)  # the consistent row is accepted
    for wrong in set(Status) - {status}:
        if wrong is Status.VERIFIED and ev is not None and mapped:
            continue
        with pytest.raises(ValueError):
            TraceabilityRow("X", s, t, ev if wrong is not Status.VERIFIED else None, wrong)


secret_values = st.sampled_from(
    [
        "sk-or-v1-" + "a1b2c3d4e5" * 4,
        "AIza" + "Q" * 35,
        "ghp_" + "x" * 36,
        "AKIA" + "ABCDEFGHIJKLMNOP",
    ]
)
placeholders = st.sampled_from(["CHANGE_ME", "<your-openrouter-key>", "placeholder", ""])


# Feature: evaluation-and-reproducibility, Property 44: Config artifact contains no real secrets
@given(
    field=st.sampled_from(["OPENROUTER_API_KEY", "GEMINI_API_KEY", "ENCRYPTION_KEK"]),
    real=st.booleans(),
    secret=secret_values,
    placeholder=placeholders,
)
def test_property_44_config_no_real_secrets(
    field, real, secret, placeholder, tmp_path_factory
) -> None:  # type: ignore[no-untyped-def]
    repo = Path(tmp_path_factory.mktemp("repo"))
    (repo / ".kiro" / "settings").mkdir(parents=True)
    value = secret if real else placeholder
    cfg = repo / ".kiro" / "settings" / "env.md"
    cfg.write_text(f"# config\nMODEL=placeholder\n{field}={value}\n", encoding="utf-8")
    findings = check_config_artifact(repo)
    if real:
        assert findings and all(
            f.path == str(cfg) and f.line == 3 for f in findings
        )  # offending field
    else:
        assert findings == []


def test_property_44_committed_kiro_has_no_secrets() -> None:
    assert check_config_artifact(REPO) == []

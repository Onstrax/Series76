"""Spec 4 traceability map: Requirements and Properties -> implementation/tests.

Machine-checked by ``tests/unit/test_agent_traceability.py`` (Task 15.1): every
Requirement 1-12 clause maps to at least one property or example test, every
Correctness Property 1-38 maps to exactly one tagged Hypothesis test, and every
listed implementation module exists.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PropertyTrace:
    """One correctness property, its validated clauses, code, and test file."""

    number: int
    clauses: tuple[str, ...]
    implementation: tuple[str, ...]
    test_file: str


_T = "tests/unit/"

PROPERTIES: tuple[PropertyTrace, ...] = (
    PropertyTrace(1, ("1.1", "1.2", "1.3"), ("tools.py",), _T + "test_agent_p01_p04_tools.py"),
    PropertyTrace(2, ("1.4", "1.5", "2.7", "3.5"), ("tools.py", "policy.py"),
                  _T + "test_agent_p01_p04_tools.py"),
    PropertyTrace(3, ("1.6", "1.7"), ("tools.py", "agent_graph.py", "composer.py"),
                  _T + "test_agent_p01_p04_tools.py"),
    PropertyTrace(4, ("1.8",), ("tools.py", "domain/budget.py"),
                  _T + "test_agent_p01_p04_tools.py"),
    PropertyTrace(5, ("2.1", "2.6", "2.9"), ("interpreter.py",),
                  _T + "test_agent_p05_p09_interpreter.py"),
    PropertyTrace(6, ("2.2",), ("interpreter.py", "language.py"),
                  _T + "test_agent_p05_p09_interpreter.py"),
    PropertyTrace(7, ("2.3",), ("interpreter.py",), _T + "test_agent_p05_p09_interpreter.py"),
    PropertyTrace(8, ("2.4", "2.5"), ("interpreter.py",),
                  _T + "test_agent_p05_p09_interpreter.py"),
    PropertyTrace(9, ("2.8", "2.10"), ("interpreter.py", "orchestrator.py"),
                  _T + "test_agent_p05_p09_interpreter.py"),
    PropertyTrace(10, ("3.1",), ("policy.py", "orchestrator.py"),
                  _T + "test_agent_p10_p16_policy_state.py"),
    PropertyTrace(11, ("3.2", "3.3", "3.6", "3.7"), ("policy.py", "recommendation.py"),
                  _T + "test_agent_p10_p16_policy_state.py"),
    PropertyTrace(12, ("3.4",), ("policy.py",), _T + "test_agent_p10_p16_policy_state.py"),
    PropertyTrace(13, ("4.1", "4.2"), ("domain/state_machine.py",),
                  _T + "test_agent_p10_p16_policy_state.py"),
    PropertyTrace(14, ("4.3",), ("orchestrator.py", "ports.py", "integration/spec3.py"),
                  _T + "test_agent_p10_p16_policy_state.py"),
    PropertyTrace(15, ("4.4", "4.5"), ("orchestrator.py", "policy.py"),
                  _T + "test_agent_p10_p16_policy_state.py"),
    PropertyTrace(16, ("4.6", "4.7"), ("orchestrator.py",),
                  _T + "test_agent_p10_p16_policy_state.py"),
    PropertyTrace(17, ("5.1", "5.2", "5.3"), ("composer.py", "i18n.py"),
                  _T + "test_agent_p17_p21_turns.py"),
    PropertyTrace(18, ("5.4", "5.6"), ("orchestrator.py", "composer.py"),
                  _T + "test_agent_p17_p21_turns.py"),
    PropertyTrace(19, ("5.5",), ("policy.py", "orchestrator.py"),
                  _T + "test_agent_p17_p21_turns.py"),
    PropertyTrace(20, ("6.1", "6.2", "6.4", "4.8"), ("policy.py", "orchestrator.py"),
                  _T + "test_agent_p17_p21_turns.py"),
    PropertyTrace(21, ("6.3", "6.5", "6.6"), ("orchestrator.py", "seam.py"),
                  _T + "test_agent_p17_p21_turns.py"),
    PropertyTrace(22, ("7.1", "7.2", "7.8"), ("recommendation.py", "composer.py"),
                  _T + "test_agent_p22_p25_recommend.py"),
    PropertyTrace(23, ("7.3",), ("policy.py", "recommendation.py"),
                  _T + "test_agent_p22_p25_recommend.py"),
    PropertyTrace(24, ("7.4", "7.5"), ("recommendation.py",),
                  _T + "test_agent_p22_p25_recommend.py"),
    PropertyTrace(25, ("7.6", "7.7", "7.9"), ("recommendation.py", "composer.py"),
                  _T + "test_agent_p22_p25_recommend.py"),
    PropertyTrace(26, ("8.1", "8.2", "8.10", "12.1", "12.4", "12.7"),
                  ("rendering.py", "composer.py", "domain/figures.py"),
                  _T + "test_agent_p26_p28_compose.py"),
    PropertyTrace(27, ("8.3", "8.4", "8.5"), ("claim_verifier.py",),
                  _T + "test_agent_p26_p28_compose.py"),
    PropertyTrace(28, ("8.6", "8.7", "8.8", "8.9"), ("composer.py",),
                  _T + "test_agent_p26_p28_compose.py"),
    PropertyTrace(29, ("9.1", "9.2", "9.3", "9.6", "9.7"), ("context.py", "orchestrator.py"),
                  _T + "test_agent_p29_p31_context.py"),
    PropertyTrace(30, ("9.4", "9.5"), ("language.py", "orchestrator.py"),
                  _T + "test_agent_p29_p31_context.py"),
    PropertyTrace(31, ("10.1", "10.7"), ("composer.py", "orchestrator.py"),
                  _T + "test_agent_p29_p31_context.py"),
    PropertyTrace(32, ("10.2", "10.3"), ("fallback.py", "orchestrator.py"),
                  _T + "test_agent_p32_p33_fallback.py"),
    PropertyTrace(33, ("10.4", "10.5", "10.6", "11.6"), ("fallback.py", "domain/budget.py"),
                  _T + "test_agent_p32_p33_fallback.py"),
    PropertyTrace(34, ("11.1", "11.2", "11.9"), ("models.py",),
                  _T + "test_agent_p34_p36_models.py"),
    PropertyTrace(35, ("11.3", "11.4", "11.5"), ("models.py",),
                  _T + "test_agent_p34_p36_models.py"),
    PropertyTrace(36, ("11.7", "11.8", "11.11"), ("domain/ledger.py", "models.py"),
                  _T + "test_agent_p34_p36_models.py"),
    PropertyTrace(37, ("12.2", "12.3", "12.6", "12.8"), ("composer.py", "domain/figures.py"),
                  _T + "test_agent_p37_p38_figures.py"),
    PropertyTrace(38, ("12.5",), ("domain/figures.py", "composer.py"),
                  _T + "test_agent_p37_p38_figures.py"),
)

#: Clauses covered by example tests rather than (only) a property.
EXAMPLE_COVERAGE: dict[str, str] = {
    "11.10": _T + "test_agent_p34_p36_models.py::test_no_winner_declared_anywhere",
    "10.2": _T + "test_agent_examples.py::test_fallback_matrix_covers_every_f2_row_exactly_once",
    "2.9": _T + "test_agent_examples.py::test_ambiguous_classification_fallback",
    "1.7": _T + "test_agent_examples.py::test_injection_in_message_changes_nothing",
}

#: Number of acceptance-criteria clauses per requirement (requirements.md).
REQUIREMENT_CLAUSES: dict[int, int] = {
    1: 8, 2: 10, 3: 7, 4: 8, 5: 6, 6: 6, 7: 9, 8: 10, 9: 7, 10: 7, 11: 11, 12: 8,
}

#: End-to-end integration (Task 14.2) on real PostgreSQL with fake LLM seams.
INTEGRATION_TEST = "tests/integration/test_spec4_agent_api.py"


def covered_clauses() -> set[str]:
    """Every clause referenced by a property or an example test."""

    out: set[str] = set(EXAMPLE_COVERAGE)
    for p in PROPERTIES:
        out.update(p.clauses)
    return out


def all_clauses() -> set[str]:
    """Every acceptance-criteria clause of Requirements 1-12."""

    return {f"{r}.{i}" for r, n in REQUIREMENT_CLAUSES.items() for i in range(1, n + 1)}

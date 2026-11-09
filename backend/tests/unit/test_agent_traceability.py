"""Spec 4 Task 15.1: every Requirement clause and Property 1-38 is traced and tagged."""

from __future__ import annotations

import re
from pathlib import Path

import series76_agent
from series76_agent.traceability import (
    INTEGRATION_TEST,
    PROPERTIES,
    all_clauses,
    covered_clauses,
)

BACKEND = Path(__file__).resolve().parents[2]
SRC = Path(series76_agent.__file__).parent
TAG = re.compile(r"# Feature: agent-orchestration-response, Property (\d+): \S")


def test_every_requirement_clause_is_covered() -> None:
    missing = all_clauses() - covered_clauses()
    assert missing == set(), sorted(missing)


def test_every_property_has_exactly_one_tagged_hypothesis_test() -> None:
    tags: dict[int, list[str]] = {}
    for path in sorted((BACKEND / "tests" / "unit").glob("test_agent_*.py")):
        for match in TAG.finditer(path.read_text(encoding="utf-8")):
            tags.setdefault(int(match.group(1)), []).append(path.name)
    assert set(tags) == set(range(1, 39))
    assert all(len(files) == 1 for files in tags.values()), tags
    for trace in PROPERTIES:
        assert tags[trace.number] == [Path(trace.test_file).name]


def test_every_tagged_test_is_a_hypothesis_property() -> None:
    for path in sorted((BACKEND / "tests" / "unit").glob("test_agent_*.py")):
        text = path.read_text(encoding="utf-8")
        for match in TAG.finditer(text):
            following = text[match.end() : match.end() + 1500]
            assert "@given(" in following.split("def ", 1)[0] + following[:400], (
                path.name,
                match.group(1),
            )


def test_implementation_sites_exist() -> None:
    for trace in PROPERTIES:
        for module in trace.implementation:
            assert (SRC / module).is_file(), module
    assert (BACKEND / INTEGRATION_TEST).is_file()
    assert (BACKEND / "docs" / "adr" / "0004-agent-stategraph.md").is_file()

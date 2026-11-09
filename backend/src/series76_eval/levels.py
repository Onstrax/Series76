"""The twelve Test_Levels and their runner (Spec 6 Req 1).

Each level maps to concrete test selections in this repository. Running a
level executes the real command and turns the real JUnit result into an
Evidence_Record (passed only if every collected case passed). A level whose
tooling is not available in the current environment (Android SDK, an
OpenRouter key, a clean-clone cold start, the audited golden dataset) is
reported ``pending`` with the reason — never as passed.

Code coverage and scenario coverage are separate measures; neither is a
substitute for facts verified against the golden dataset.
"""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from pathlib import Path

from series76_eval.evidence import (
    EvidenceRecord,
    EvidenceStore,
    Result,
    git_commit,
    now_iso,
    redact,
)


class TestLevel(str, Enum):
    DOCUMENTAL = "01_documental_verification"
    UNIT_DOMAIN = "02_unit_domain"
    ETL_INTEGRATION = "03_etl_integration"
    DB_INTEGRATION = "04_db_integration"
    BACKEND_CONTRACT = "05_backend_contract"
    AGENT_MOCK_TOOLS = "06_agent_with_mock_tools"
    AGENT_LIVE_EVALS = "07_agent_evals_real_api"
    CONCURRENCY_FAILURE = "08_concurrency_failure"
    SECURITY_ADVERSARIAL = "09_security_adversarial"
    ANDROID_UNIT_UI = "10_android_unit_ui"
    ANDROID_INSTRUMENTED = "11_android_instrumented"
    COLD_START = "12_reproducibility_cold_start"


@dataclass(frozen=True, slots=True)
class LevelSpec:
    level: TestLevel
    command: tuple[str, ...]
    sources: tuple[str, ...]
    requires: str = ""

    @property
    def is_pytest(self) -> bool:
        return self.command[:1] == ("pytest",)


_U = "tests/unit/"
_I = "tests/integration/"

LEVELS: dict[TestLevel, LevelSpec] = {
    TestLevel.DOCUMENTAL: LevelSpec(
        TestLevel.DOCUMENTAL,
        (
            "pytest",
            "-m",
            "integration or not integration",
            _U + "test_eval_p01_p03_oracle.py",
            _I + "test_real_edition.py",
        ),
        ("src/series76_eval/oracle.py", _U + "test_eval_p01_p03_oracle.py"),
        requires="audited golden dataset + Docker (the real edition is published into a "
        "fresh PostgreSQL and compared cell by cell)",
    ),
    TestLevel.UNIT_DOMAIN: LevelSpec(
        TestLevel.UNIT_DOMAIN,
        (
            "pytest",
            _U + "test_eval_p04_p10_domain.py",
            _U + "test_prop_search_semantics.py",
            _U + "test_prop_ranking.py",
            _U + "test_prop_comparison.py",
            _U + "test_prop_conversion.py",
        ),
        (_U + "test_eval_p04_p10_domain.py",),
    ),
    TestLevel.ETL_INTEGRATION: LevelSpec(
        TestLevel.ETL_INTEGRATION,
        (
            "pytest",
            _U + "test_normalizer.py",
            _U + "test_reconciler.py",
            _U + "test_verifier.py",
            _U + "test_manifest_builder.py",
            _U + "test_golden_exporter.py",
            _U + "test_fresh_extraction_stub.py",
            _U + "test_etl_pipeline.py",
        ),
        (_U + "test_normalizer.py",),
    ),
    TestLevel.DB_INTEGRATION: LevelSpec(
        TestLevel.DB_INTEGRATION,
        (
            "pytest",
            "-m",
            "integration",
            _I + "test_migrations.py",
            _I + "test_roles.py",
            _I + "test_prop_repository.py",
            _I + "test_publisher.py",
            _I + "test_etl_publish.py",
            _I + "test_real_edition.py",
        ),
        (_I + "test_migrations.py",),
        requires="Docker (real PostgreSQL container)",
    ),
    TestLevel.BACKEND_CONTRACT: LevelSpec(
        TestLevel.BACKEND_CONTRACT,
        (
            "pytest",
            _U + "test_eval_contract_snapshot.py",
            "-m",
            "integration or not integration",
            _I + "test_spec3_conversation_api.py",
            _I + "test_spec3_errors_ready_api.py",
        ),
        (_U + "test_eval_contract_snapshot.py", "../docs/contract/openapi.json"),
        requires="Docker (real PostgreSQL container)",
    ),
    TestLevel.AGENT_MOCK_TOOLS: LevelSpec(
        TestLevel.AGENT_MOCK_TOOLS,
        (
            "pytest",
            "-p",
            "no:randomly",
            _U + "test_agent_examples.py",
            _U + "test_agent_p17_p21_turns.py",
            _U + "test_agent_p26_p28_compose.py",
        ),
        (_U + "test_agent_examples.py",),
    ),
    TestLevel.AGENT_LIVE_EVALS: LevelSpec(
        TestLevel.AGENT_LIVE_EVALS,
        ("python", "-m", "series76_eval", "live-eval"),
        ("src/series76_eval/ab.py", "src/series76_eval/scenarios.py"),
        requires="OPENROUTER_API_KEY + audited golden dataset + budget gate ([EXPERIMENT])",
    ),
    TestLevel.CONCURRENCY_FAILURE: LevelSpec(
        TestLevel.CONCURRENCY_FAILURE,
        (
            "pytest",
            "-m",
            "integration",
            _I + "test_spec3_worker_protocol.py",
            _I + "test_spec3_jobs_api.py",
            _I + "test_spec3_delete_trace_api.py",
        ),
        (_I + "test_spec3_worker_protocol.py",),
        requires="Docker (real PostgreSQL container)",
    ),
    TestLevel.SECURITY_ADVERSARIAL: LevelSpec(
        TestLevel.SECURITY_ADVERSARIAL,
        (
            "pytest",
            _U + "test_eval_p24_p26_security.py",
            "-m",
            "integration or not integration",
            _I + "test_eval_p19_p28_security.py",
        ),
        (_U + "test_eval_p24_p26_security.py", _I + "test_eval_p19_p28_security.py"),
        requires="Docker (real PostgreSQL container)",
    ),
    TestLevel.ANDROID_UNIT_UI: LevelSpec(
        TestLevel.ANDROID_UNIT_UI,
        ("../android/gradlew", "-p", "../android", ":app:testDebugUnitTest"),
        ("../android/app/src/test/java/com/series76/assistant/RenderPropertiesTest.kt",),
        requires="Android SDK + JDK 17 (Gradle build)",
    ),
    TestLevel.ANDROID_INSTRUMENTED: LevelSpec(
        TestLevel.ANDROID_INSTRUMENTED,
        ("../android/gradlew", "-p", "../android", ":app:connectedDebugAndroidTest"),
        ("../android/app/src/androidTest/java/com/series76/assistant/EmulatorSuite.kt",),
        requires="Android SDK + running emulator",
    ),
    TestLevel.COLD_START: LevelSpec(
        TestLevel.COLD_START,
        ("python", "-m", "series76_eval", "cold-start-checklist"),
        ("../README.md", "docker-compose.yml"),
        requires="a clean clone + Docker Compose, README commands only ([EXPERIMENT])",
    ),
}


@dataclass(frozen=True, slots=True)
class LevelResult:
    level: TestLevel
    present: bool
    non_empty: bool
    status: str  # "passed" | "failed" | "pending"
    reason: str
    evidence: EvidenceRecord | None = None


def presence(level: TestLevel, backend: Path) -> tuple[bool, bool]:
    """Every level is defined (present) and has at least one existing source (non-empty)."""

    spec = LEVELS[level]
    existing = [s for s in spec.sources if (backend / s).exists()]
    return True, bool(existing)


def _junit_counts(path: Path) -> tuple[int, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root)
    total = failed = 0
    for s in suites:
        total += int(s.get("tests", 0)) - int(s.get("skipped", 0))
        failed += int(s.get("failures", 0)) + int(s.get("errors", 0))
    return total - failed, total


def run_level(
    level: TestLevel, backend: Path, store: EvidenceStore, *, timeout: int = 3600
) -> LevelResult:
    """Execute a pytest-backed level and persist its Evidence_Record."""

    present, non_empty = presence(level, backend)
    spec = LEVELS[level]
    if not spec.is_pytest:
        return LevelResult(
            level, present, non_empty, "pending", spec.requires or "not automatable here"
        )
    with tempfile.TemporaryDirectory() as tmp:
        junit = Path(tmp) / "junit.xml"
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            *spec.command[1:],
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",
            f"--junitxml={junit}",
        ]
        proc = subprocess.run(
            cmd, cwd=backend, capture_output=True, text=True, timeout=timeout, env={**os.environ}
        )
        if not junit.exists():
            return LevelResult(level, present, non_empty, "failed", "no JUnit report produced")
        passed, total = _junit_counts(junit)
    if total == 0:
        return LevelResult(level, present, non_empty, "pending", "no runnable cases collected")
    result = Result.PASSED if passed == total and proc.returncode == 0 else Result.FAILED
    record = store.persist(
        EvidenceRecord(
            claim_id=f"level:{level.value}",
            command=" ".join(shlex.quote(c) for c in ["pytest", *spec.command[1:]]),
            date=now_iso(),
            commit=git_commit(backend),
            environment=(
                f"{platform.system()} {platform.release()} / Python {platform.python_version()}"
            ),
            result=result,
            sanitized_log=redact("\n".join(proc.stdout.strip().splitlines()[-5:])),
            case_count=passed,
            denominator=total,
            no_critical_defects=result is Result.PASSED,
            known_limits="LLM seams faked (zero spend); see the level requirements for gaps",
            cumulative_cost_usd=Decimal("0"),
        )
    )
    return LevelResult(level, present, non_empty, result.value, "executed", record)


@dataclass(frozen=True, slots=True)
class CoverageReport:
    """Two distinct, separately labeled measures (Req 1.8)."""

    code_coverage: str
    scenario_coverage: str

    def lines(self) -> list[str]:
        return [
            f"code coverage (lines): {self.code_coverage}",
            f"scenario coverage (scored scenarios / suite): {self.scenario_coverage}",
        ]

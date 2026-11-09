"""Evidence_Record, EvidenceStore, and the HonestyPolicy (Spec 6 Req 8).

A result exists only once a complete :class:`EvidenceRecord` is persisted. A
"passed" claim without one is rejected and the missing-evidence condition is
recorded. Coverage is always a numerator over an explicit denominator, never a
bare percentage, and code-line coverage is never accepted as evidence of
verified data. Logs are redacted before they are stored.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path


class EvidenceError(ValueError):
    """An Evidence_Record is incomplete or inconsistent."""


class Result(str, Enum):
    PASSED = "passed"
    FAILED = "failed"


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(bearer)\s+[A-Za-z0-9._\-]{8,}"),
    re.compile(r"(?i)((?:api[_-]?key|password|passwd|secret|token|kek|dek)\s*[=:]\s*)\S+"),
    re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:\s]+:)[^@\s]+@"),
)


def redact(text: str) -> str:
    """Remove credentials / tokens / keys from a log before it is persisted."""

    out = text
    out = _SECRET_PATTERNS[0].sub("[REDACTED]", out)
    out = _SECRET_PATTERNS[1].sub(r"\1 [REDACTED]", out)
    out = _SECRET_PATTERNS[2].sub(r"\1[REDACTED]", out)
    out = _SECRET_PATTERNS[3].sub(r"\1[REDACTED]@", out)
    return out


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """The facts captured for any "passed" (or "failed") claim (Req 8.1)."""

    claim_id: str
    command: str
    date: str
    commit: str
    environment: str
    result: Result
    sanitized_log: str
    case_count: int
    denominator: int
    no_critical_defects: bool
    known_limits: str
    cumulative_cost_usd: Decimal

    def __post_init__(self) -> None:
        for name in ("claim_id", "command", "date", "commit", "environment", "known_limits"):
            if not str(getattr(self, name)).strip():
                raise EvidenceError(f"Evidence_Record.{name} is required")
        if not isinstance(self.result, Result):
            raise EvidenceError("result must be passed or failed")
        if self.denominator <= 0 or not 0 <= self.case_count <= self.denominator:
            raise EvidenceError("case_count must be within an explicit positive denominator")
        if isinstance(self.cumulative_cost_usd, float) or self.cumulative_cost_usd < 0:
            raise EvidenceError("cumulative_cost_usd must be a non-negative Decimal")
        if redact(self.sanitized_log) != self.sanitized_log:
            raise EvidenceError("sanitized_log still contains a secret-like value")
        if self.result is Result.PASSED and self.case_count != self.denominator:
            raise EvidenceError("a passed record must have every case passing")

    def coverage(self) -> str:
        """Always numerator over explicit denominator (Req 8.2)."""
        return f"{self.case_count}/{self.denominator}"

    def to_json(self) -> dict[str, object]:
        raw = asdict(self)
        raw["result"] = self.result.value
        raw["cumulative_cost_usd"] = str(self.cumulative_cost_usd)
        return raw

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> EvidenceRecord:
        return cls(
            claim_id=str(raw["claim_id"]),
            command=str(raw["command"]),
            date=str(raw["date"]),
            commit=str(raw["commit"]),
            environment=str(raw["environment"]),
            result=Result(str(raw["result"])),
            sanitized_log=str(raw["sanitized_log"]),
            case_count=int(str(raw["case_count"])),
            denominator=int(str(raw["denominator"])),
            no_critical_defects=bool(raw["no_critical_defects"]),
            known_limits=str(raw["known_limits"]),
            cumulative_cost_usd=Decimal(str(raw["cumulative_cost_usd"])),
        )


@dataclass
class EvidenceStore:
    """Append-only JSONL store of Evidence_Records (committed under docs/evidence)."""

    path: Path
    _records: list[EvidenceRecord] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    self._records.append(EvidenceRecord.from_json(json.loads(line)))

    def persist(self, record: EvidenceRecord) -> EvidenceRecord:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_json(), sort_keys=True) + "\n")
        self._records.append(record)
        return record

    def records(self) -> list[EvidenceRecord]:
        return list(self._records)

    def latest(self, claim_id: str) -> EvidenceRecord | None:
        found = [r for r in self._records if r.claim_id == claim_id]
        return found[-1] if found else None


@dataclass(frozen=True, slots=True)
class HonestyVerdict:
    accepted: bool
    reason: str


@dataclass
class HonestyPolicy:
    """Rejects claims that are not backed by persisted evidence (Req 8.1-8.8)."""

    store: EvidenceStore
    missing_evidence: list[str] = field(default_factory=list)
    defects: list[tuple[str, str, str]] = field(default_factory=list)

    def assert_honest(self, claim_id: str, claimed: Result) -> HonestyVerdict:
        """A "passed" claim needs a persisted, passing record for that claim."""

        record = self.store.latest(claim_id)
        if record is None:
            self.missing_evidence.append(claim_id)
            return HonestyVerdict(False, "missing Evidence_Record")
        if claimed is Result.PASSED and record.result is not Result.PASSED:
            return HonestyVerdict(False, "evidence does not show a pass")
        return HonestyVerdict(True, f"evidence {record.coverage()} at {record.commit}")

    def check_coverage_claim(self, numerator: int, denominator: int, basis: str) -> HonestyVerdict:
        """Coverage claims: explicit denominator; no 100%-semantic from 68 rows / 36 scenarios."""

        if denominator <= 0 or not 0 <= numerator <= denominator:
            return HonestyVerdict(False, "coverage needs a numerator over a positive denominator")
        if basis == "code-lines-as-data":
            return HonestyVerdict(False, "code-line coverage is not verified-data evidence")
        if (
            basis in ("golden-rows-as-semantic", "scenarios-as-semantic")
            and numerator == denominator
        ):
            return HonestyVerdict(False, "100% semantic coverage cannot be claimed from this basis")
        return HonestyVerdict(True, f"{numerator}/{denominator} ({basis})")

    def record_defect(self, scope: str, category: str, justification: str) -> None:
        """Non-critical defects are recorded, never suppressed (Req 8.7)."""
        self.defects.append((scope, category, justification))


def git_commit(repo: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def now_iso() -> str:
    return datetime.now(UTC).isoformat()

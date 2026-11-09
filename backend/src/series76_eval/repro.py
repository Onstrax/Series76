"""ReproducibilityChecker, artifact integrity, and ConfigArtifactChecker (Spec 6 Req 7, 10).

Structural checks are static and run anywhere. The cold start itself (a clean
clone brought up with only README commands) is ``[EXPERIMENT]``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

#: README topics that must each have a locatable section (Req 7.3).
README_TOPICS: dict[str, tuple[str, ...]] = {
    "setup": ("setup", "quick start"),
    "synchronous endpoint": ("post /api/conversation",),
    "asynchronous endpoint": ("/api/conversation/jobs",),
    "registration": ("registration", "register"),
    "login": ("login",),
    "user vs developer": ("developer",),
    "debug permissions": ("debug",),
    "decisions and tradeoffs": ("decision", "trade-off", "tradeoff"),
    "configurable models": ("agent_model",),
    "budget": ("budget",),
    "security limitations": ("security limitation", "limitations"),
    "fresh extraction vs verified replay": ("verified_replay", "fresh_extraction"),
    "known failures": ("known failures", "known issues"),
}

_SECRET_RX = (
    ("openrouter/openai-style key", re.compile(r"\bsk-(?:or-v1-)?[A-Za-z0-9]{20,}")),
    ("google api key", re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}")),
    ("github token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("aws key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    (
        "assigned secret",
        re.compile(
            # the key NAME ends with the secret word (AUTH_TOKEN_POLICY is not a secret)
            r"(?im)^\s*[A-Z0-9_]*(?:API_KEY|SECRET|PASSWORD|TOKEN|KEK)\s*[=:]\s*"
            r"(?!\s*$)(?!.*(?:CHANGE_ME|change_me|placeholder|<|your-|example|REPLACE))\S{12,}"
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class SecretFinding:
    path: str
    line: int
    kind: str


def scan_secrets(root: Path, *, suffixes: tuple[str, ...] = ()) -> list[SecretFinding]:
    """Scan text files under ``root`` for real-looking secrets (placeholders pass)."""

    findings: list[SecretFinding] = []
    paths = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
    for path in paths:
        if suffixes and path.suffix not in suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            for kind, rx in _SECRET_RX:
                if rx.search(line):
                    findings.append(SecretFinding(str(path), i, kind))
    return findings


@dataclass(frozen=True, slots=True)
class IntegrityResult:
    artifact: str
    expected: str
    actual: str

    @property
    def accepted(self) -> bool:
        return self.expected == self.actual


class ArtifactRejected(Exception):
    """A source artifact failed its SHA-256 check; it must not be published/ingested."""

    def __init__(self, result: IntegrityResult) -> None:
        super().__init__(f"SHA-256 mismatch for {result.artifact}")
        self.result = result


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def check_integrity(artifact: str, data: bytes, trusted_sha256: str) -> IntegrityResult:
    """Compare a digest to its trusted reference; raise on mismatch (Req 7.7, 7.8)."""

    result = IntegrityResult(artifact, trusted_sha256.lower(), hashlib.sha256(data).hexdigest())
    if not result.accepted:
        raise ArtifactRejected(result)
    return result


def guarded_ingest(
    artifact: str, data: bytes, trusted_sha256: str, ingest: object
) -> IntegrityResult:
    """Call ``ingest(data)`` only after the digest matched; never on mismatch."""

    result = check_integrity(artifact, data, trusted_sha256)
    assert callable(ingest)
    ingest(data)
    return result


@dataclass
class StructuralReport:
    problems: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_structure(repo: Path) -> StructuralReport:
    """Static delivery checks (Req 7.1-7.4, 10.1-10.2)."""

    rep = StructuralReport()
    must_exist = {
        "backend": repo / "backend" / "src" / "series76_api",
        "worker": repo / "backend" / "src" / "series76_api" / "worker.py",
        "android app": repo / "android" / "app" / "build.gradle.kts",
        "ingestion pipeline": repo / "backend" / "src" / "series76_data" / "pipeline",
        "Dockerfile": repo / "backend" / "Dockerfile",
        "docker-compose.yml": repo / "backend" / "docker-compose.yml",
        ".env.example": repo / "backend" / ".env.example",
        "migrations": repo / "backend" / "migrations" / "versions",
        "root README": repo / "README.md",
        ".kiro config artifact": repo / ".kiro",
        "ADRs": repo / "backend" / "docs" / "adr",
    }
    for name, path in must_exist.items():
        if not path.exists():
            rep.problems.append(f"missing {name}: {path}")
    compose = repo / "backend" / "docker-compose.yml"
    if compose.exists():
        services = _compose_services(compose.read_text(encoding="utf-8"))
        runtime = services - {"migrate"}
        if runtime != {"db", "api", "worker"}:
            rep.problems.append(
                f"compose runtime services are {sorted(runtime)}, expected db/api/worker"
            )
    env = repo / "backend" / ".env.example"
    if env.exists():
        for f in scan_secrets(env):
            rep.problems.append(f".env.example line {f.line}: {f.kind}")
    readme = repo / "README.md"
    if readme.exists():
        text = readme.read_text(encoding="utf-8").lower()
        for topic, needles in README_TOPICS.items():
            if not any(n in text for n in needles):
                rep.problems.append(f"README lacks a section on {topic}")
        if ".kiro" not in text:
            rep.problems.append("README does not reference the .kiro/ configuration artifact")
    return rep


def _compose_services(text: str) -> set[str]:
    services: set[str] = set()
    inside = False
    for line in text.splitlines():
        if re.match(r"^services:\s*$", line):
            inside = True
            continue
        if inside and re.match(r"^\S", line):
            inside = False
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line) if inside else None
        if m:
            services.add(m.group(1))
    return services


def check_config_artifact(repo: Path) -> list[SecretFinding]:
    """The committed .kiro/ directory contains placeholders only (Req 10.3, 10.4)."""
    return scan_secrets(repo / ".kiro")

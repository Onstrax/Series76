"""AndroidQASuite catalogue and the twelve E2E demo flows (Spec 6 Req 5, 6).

The Android behaviors themselves are verified by the Kotlin tests of Spec 5
(JVM property tests + emulator suite), which must be run with Gradle / an
emulator. This module is the harness side: it enumerates the obligations, ties
each to the Kotlin test (or manual emulator check) that verifies it, and
reports a check group as passed only when an Evidence_Record exists for it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from series76_eval.evidence import EvidenceStore, Result

#: The thirteen UiStates (Req 5.2) and where each is produced in the client.
UI_STATES: dict[str, str] = {
    "loading": "ConversationsUiState.FirstLoad",
    "empty": "ConversationsUiState.Empty",
    "queued": "TurnState.QUEUED",
    "running": "TurnState.RUNNING",
    "error": "ConversationsUiState.RecoverableError",
    "offline-cache": "ConversationsUiState.OfflineCache",
    "no-matches": "RenderItem.Matches",
    "N/A": "state_not_applicable",
    "plan-awaiting-confirmation": "PlanPanel",
    "stale-plan": "plan_stale",
    "session-expired": "ConversationsUiState.SessionExpired",
    "catalog-withdrawn": "CATALOG_WITHDRAWN",
    "deletion-pending": "deleteIndeterminate",
}

#: Android QA check groups -> the client test that verifies each.
CHECK_GROUPS: dict[str, str] = {
    "accessibility-semantics": "RendererSemanticsTest",
    "large-text-200": "EmulatorSuite.rendererKeepsContentAtTwiceFontScale",
    "debug-gate": "property29_debugRevealedOnlyToDeveloper",
    "cache-purge-on-switch": "property14_accountSwitchPurgesAndDiscards",
    "offline-remote-delete": "property19_deleteConfirmReconcileNoResurrection",
    "offline-draft": "property26_offlineNoSendDraftPreserved",
    "server-vs-offline": "property28_offlineVersusServerError",
    "off-main-thread": "property34_pollingStopsWhenScreenStopped",
}


@dataclass(frozen=True, slots=True)
class QAStatus:
    name: str
    status: str  # passed | failed | pending
    detail: str


def ui_state_coverage(android_src: Path) -> dict[str, bool]:
    """Which documented UiStates are produced somewhere in the client sources."""

    text = "\n".join(p.read_text(encoding="utf-8") for p in android_src.rglob("*.kt"))
    text += "\n".join(p.read_text(encoding="utf-8") for p in android_src.rglob("*.xml"))
    return {state: marker.split(".")[-1] in text for state, marker in UI_STATES.items()}


def check_group_status(store: EvidenceStore, android_test_src: Path) -> list[QAStatus]:
    """Passed only with evidence; otherwise pending (failed if the verifying test is missing)."""

    sources = "\n".join(p.read_text(encoding="utf-8") for p in android_test_src.rglob("*.kt"))
    out: list[QAStatus] = []
    for group, test_name in CHECK_GROUPS.items():
        if test_name.split(".")[-1] not in sources:
            out.append(QAStatus(group, "failed", f"verifying test {test_name} is missing"))
            continue
        record = store.latest(f"android:{group}")
        if record is None:
            out.append(
                QAStatus(group, "pending", f"{test_name} not yet executed (needs Gradle/emulator)")
            )
        else:
            out.append(QAStatus(group, record.result.value, record.coverage()))
    return out


@dataclass(frozen=True, slots=True)
class Flow:
    number: int
    title: str
    requirement: str


FLOWS: tuple[Flow, ...] = (
    Flow(1, "Register (role user), logout, login again", "6.1"),
    Flow(
        2,
        "Exact PN for On/Off and Modulating: figures equal verified references, evidence note",
        "6.2",
    ),
    Flow(3, "Filter search: count equals listed PNs, at most three cards", "6.3"),
    Flow(
        4,
        "Incomplete recommendation: interpretation, correction, new plan revision, ranking",
        "6.4",
    ),
    Flow(5, "Compare two models then alternate a third: bars only when comparable", "6.5"),
    Flow(6, "Low-frequency follow-up without PN, backend restart, history order preserved", "6.6"),
    Flow(7, "Developer Debug for own session visible; user role denied", "6.7"),
    Flow(8, "Backend outage: cache recovery, draft kept, reconnect", "6.8"),
    Flow(9, "Two consecutive turns survive app reopen in order", "6.9"),
    Flow(10, "Delete with job in progress: conversation never reappears", "6.10"),
    Flow(
        11,
        "Verified replay with zero Gemini calls; optional fresh extraction with evaluator key",
        "6.11",
    ),
    Flow(12, "Clean clone + Docker Compose + emulator covering all flows", "6.12"),
)


def flow_status(store: EvidenceStore) -> list[QAStatus]:
    """A flow is passed only with a persisted, passing record; else pending."""

    out = []
    for flow in FLOWS:
        record = store.latest(f"e2e:flow-{flow.number:02d}")
        if record is None:
            out.append(
                QAStatus(f"flow-{flow.number:02d}", "pending", "emulator evidence not captured")
            )
        else:
            ok = record.result is Result.PASSED
            out.append(
                QAStatus(f"flow-{flow.number:02d}", "passed" if ok else "failed", record.coverage())
            )
    return out

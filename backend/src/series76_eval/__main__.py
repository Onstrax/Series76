"""Command line of the evaluation harness: ``python -m series76_eval <command>``.

Commands (run from ``backend/``):

* ``levels`` — list the twelve levels with presence / requirements;
* ``run-level <level>`` — execute a pytest-backed level and persist its evidence;
* ``documental-verify`` — compare the published catalog with the audited golden
  dataset (pending until the Spec 1 manual audit exists);
* ``traceability`` — regenerate ``docs/traceability/TRACEABILITY.md``;
* ``repro-check`` / ``config-check`` — static delivery and ``.kiro/`` checks;
* ``integrity`` — SHA-256 of the source PDF vs the handoff's trusted ``SHA256SUMS.txt``;
* ``contract-snapshot [--write]`` — compare (or rewrite) ``docs/contract/openapi.json``;
* ``live-eval`` — the cost-gated live level (refuses without a key and an
  audited golden dataset); ``status`` — summary of evidence and pending items.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from series76_eval.evidence import EvidenceStore, Result
from series76_eval.levels import LEVELS, TestLevel, presence, run_level
from series76_eval.qa import flow_status
from series76_eval.repro import check_config_artifact, check_structure
from series76_eval.traceability import build_artifact

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
STORE = REPO / "docs" / "evidence" / "evidence.jsonl"
GOLDEN = BACKEND / "data" / "golden" / "golden_dataset.json"


def _store() -> EvidenceStore:
    return EvidenceStore(STORE)


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "status"
    out = sys.stdout.write

    if cmd == "levels":
        for level, spec in LEVELS.items():
            present, non_empty = presence(level, BACKEND)
            out(
                f"{level.value}: present={present} non_empty={non_empty}"
                f"{'  requires: ' + spec.requires if spec.requires else ''}\n"
            )
        return 0

    if cmd == "run-level" and len(args) > 1:
        level = TestLevel(args[1])
        res = run_level(level, BACKEND, _store())
        out(
            f"{level.value}: {res.status} ({res.reason})"
            f"{' ' + res.evidence.coverage() if res.evidence else ''}\n"
        )
        return 0 if res.status != "failed" else 1

    if cmd == "integrity":
        from series76_eval.repro import ArtifactRejected, check_integrity

        handoff = REPO / "Series76_Kiro_Handoff_v1.0"
        trusted = {
            name.strip(): digest
            for digest, name in (
                line.split(None, 1)
                for line in (handoff / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        }
        rel = "02_ORIGINAL_SOURCES/series_76_electric_data.pdf"
        try:
            checked = check_integrity(rel, (handoff / rel).read_bytes(), trusted[rel])
        except ArtifactRejected as exc:
            out(f"REJECTED {exc.result.artifact}: {exc.result.actual} != {exc.result.expected}\n")
            return 1
        out(f"accepted {checked.artifact} sha256={checked.actual}\n")
        manifests = sorted((BACKEND / "data" / "verified_replay").glob("*.json"))
        if not manifests:
            out(
                "pending: no verified_replay manifest is committed yet (it is produced by the "
                "Spec 1 manual audit, an [EXPERIMENT]).\n"
            )
        return 0

    if cmd == "contract-snapshot":
        from series76_eval.contract import SNAPSHOT, current_openapi, render, write_snapshot

        if "--write" in args:
            out(f"wrote {write_snapshot()}\n")
            return 0
        same = SNAPSHOT.exists() and SNAPSHOT.read_text(encoding="utf-8") == render(
            current_openapi()
        )
        out(f"contract snapshot {'matches' if same else 'DRIFTED or missing'}: {SNAPSHOT}\n")
        return 0 if same else 1

    if cmd == "documental-verify":
        if not GOLDEN.exists():
            out(
                "pending: the audited golden dataset does not exist yet "
                "(Spec 1 manual audit of series_76_electric_data.pdf is an [EXPERIMENT]).\n"
            )
            return 0
        out("golden dataset present: run the GoldenOracle against the published edition.\n")
        return 0

    if cmd == "traceability":
        store = _store()
        evidence = {
            r.claim_id.split("item:", 1)[1]: f"{r.claim_id}@{r.commit[:8]}"
            for r in store.records()
            if r.claim_id.startswith("item:") and r.result is Result.PASSED
        }
        art = build_artifact(REPO / ".kiro" / "specs", evidence)
        target = REPO / "docs" / "traceability" / "TRACEABILITY.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(art.to_markdown(), encoding="utf-8")
        out(f"wrote {target.relative_to(REPO)}\n")
        return 0

    if cmd == "repro-check":
        rep = check_structure(REPO)
        for p in rep.problems:
            out(f"problem: {p}\n")
        out("structure ok\n" if rep.ok else "structure has problems\n")
        return 0 if rep.ok else 1

    if cmd == "config-check":
        findings = check_config_artifact(REPO)
        for f in findings:
            out(f"secret-like value: {f.path}:{f.line} ({f.kind})\n")
        out("no secrets in .kiro/\n" if not findings else "")
        return 0 if not findings else 1

    if cmd == "live-eval":
        if not os.environ.get("OPENROUTER_API_KEY") or not GOLDEN.exists():
            out(
                "refused: live evaluation needs OPENROUTER_API_KEY and the audited golden dataset; "
                "offline and canary stages must complete first. No call was made.\n"
            )
            return 0
        out("prerequisites present: run the staged evaluation (offline -> canary -> paired A/B).\n")
        return 0

    if cmd == "cold-start-checklist":
        out(
            "pending: execute the README cold-start steps from a clean clone and record evidence.\n"
        )
        return 0

    # status
    store = _store()
    out(f"evidence records: {len(store.records())}\n")
    for s in flow_status(store):
        out(f"{s.name}: {s.status}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

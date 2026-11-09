"""verified_replay artifacts: audit sheets + OCR draft, manifest, golden dataset.

``build`` (run once, after the human audit) turns the audited sheets into:

* ``data/verified_replay/manifest.json`` — the canonical manifest: SHA-256 of
  the source PDF and of every approved artifact, versions, reviewer, audited
  counts, corrections, and the stable ``manifest_digest`` (Spec 1 Req 1.5, 2);
* ``data/golden/golden_dataset.json`` — one golden value per printed cell,
  bound to the edition id and manifest digest (Spec 1 Req 10, Spec 6 Req 2).

``replay`` (run on every deployment) recomputes and compares every artifact
hash with :class:`VerifiedReplayExtractor`, re-derives the catalog from the
verified bytes only, recomputes the manifest digest and checks it, and checks
the golden round trip. It needs neither the PDF nor any network/model call.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from series76_data.errors import IngestionErrorCode
from series76_data.etl.facts import Catalog, GoldenEntry, build_catalog, cell_key
from series76_data.etl.layout import TABLES
from series76_data.etl.sheets import (
    UNSURE,
    AuditProblems,
    parse_notes,
    parse_sheet,
)
from series76_data.golden.exporter import (
    ABSENT_MARKER,
    NA_MARKER,
    NO_UNIT_MARKER,
    GoldenDatasetExporter,
    GoldenValue,
)
from series76_data.pipeline.diagnostics import fail
from series76_data.pipeline.extractor_replay import (
    ReplayArtifact,
    ReplayManifestView,
    VerifiedReplayExtractor,
)
from series76_data.pipeline.manifest_builder import (
    ManifestBuilder,
    VerificationManifestData,
)
from series76_data.pipeline.source_inventory import compute_sha256
from series76_data.pipeline.verifier import OracleCounts

FORMAT = "series76-verified-replay/1"
SOURCE_PDF = "series_76_electric_data.pdf"
SHEET_TRANSFORM = "audit-sheet-csv/1"
DRAFT_TRANSFORM = "ocr-draft-json/1"
CONFIRMABLE = frozenset({SHEET_TRANSFORM, DRAFT_TRANSFORM})
NORMALIZATION_VERSION = "series76-normalizer/1"
RULES_VERSION = "series76-layout/1"
EXTRACTOR_VERSION = "human-audit-sheets/1 (draft: rapidocr-onnxruntime, two reads)"
DRAFT_FILE = "ocr_draft.json"
NOTES_FILE = "notes.csv"
EDITION_NAMESPACE = uuid.UUID("6f1d5f0e-8a3b-5c4e-9d2a-760000000076")

ORACLE = OracleCounts()  # 7 tables / 68 rows / 4 N/A rows in T03 — to be confirmed


def artifact_names() -> list[str]:
    return [f"{t.code}.csv" for t in TABLES] + [NOTES_FILE, DRAFT_FILE]


def edition_id_for(manifest_digest: str) -> uuid.UUID:
    """Deterministic edition id: the same audited package is the same edition."""

    return uuid.uuid5(EDITION_NAMESPACE, manifest_digest)


@dataclass(slots=True)
class Package:
    """An audited, parsed package: the catalog plus its audit trail."""

    catalog: Catalog
    corrections: list[dict[str, str]]
    artifact_shas: dict[str, str]


def parse_package(payloads: Mapping[str, bytes], reviewer: str, source_sha: str) -> Package:
    """Parse audited artifact bytes; raises ``SheetError``/``ValueError`` on problems."""

    problems = AuditProblems()
    sheets = tuple(
        parse_sheet(t.code, payloads[f"{t.code}.csv"].decode("utf-8"), problems) for t in TABLES
    )
    notes = parse_notes(payloads[NOTES_FILE].decode("utf-8"), problems)
    draft = json.loads(payloads[DRAFT_FILE].decode("utf-8"))
    corrections: list[dict[str, str]] = []
    changed_rows: set[tuple[str, int]] = set()
    for sheet in sheets:
        t = sheet.layout.code
        drafted = draft["sheets"].get(t, [])
        for row in sheet.rows:
            before = drafted[row.ordinal - 1] if row.ordinal - 1 < len(drafted) else {}
            pairs = [("pn", row.printed_pn), *row.cells.items()]
            for column, value in pairs:
                prior = str(before.get(column, ""))
                if prior.startswith(UNSURE) or prior != value:
                    if prior != value:
                        changed_rows.add((t, row.ordinal))
                    corrections.append({
                        "cell": cell_key(t, row.ordinal, column),
                        "prior_value": prior.removeprefix(UNSURE),
                        "verified_value": value,
                        "reviewer": reviewer,
                        "justification": row.justification
                        or "OCR candidate confirmed against the PDF image",
                        "source_document_hash": source_sha,
                    })
            if (t, row.ordinal) in changed_rows and not row.justification:
                problems.add(f"{t}.csv row {row.ordinal}",
                             "values were changed: write a short Justification")
    drafted_notes = draft.get("notes", [])
    for note in notes:
        prior = drafted_notes[note.index - 1] if note.index - 1 < len(drafted_notes) else ""
        if prior.removeprefix(UNSURE) != note.printed_text:
            corrections.append({
                "cell": f"{note.tables[0]}#note{note.index}",
                "prior_value": prior.removeprefix(UNSURE),
                "verified_value": note.printed_text,
                "reviewer": reviewer,
                "justification": note.justification or "note text transcribed from the PDF",
                "source_document_hash": source_sha,
            })
    for note in notes:
        if note.rows is None:
            continue
        known = {r.printed_pn for s in sheets if s.layout.code in note.tables for r in s.rows}
        for pn in note.rows:
            if pn not in known:
                problems.add(f"notes.csv note {note.index}",
                             f"row {pn!r} is not a part number of {','.join(note.tables)}")
    if problems.problems:
        raise ValueError("audit sheets are not ready:\n  - " + "\n  - ".join(problems.problems))
    catalog = build_catalog(sheets, notes)
    return Package(catalog, corrections, {n: compute_sha256(b) for n, b in payloads.items()})


def manifest_data(package: Package, source_sha: str) -> VerificationManifestData:
    counts = package.catalog.counts()
    return VerificationManifestData(
        source_shas={SOURCE_PDF: source_sha, **package.artifact_shas},
        normalization_version=NORMALIZATION_VERSION,
        rules_version=RULES_VERSION,
        extractor_version=EXTRACTOR_VERSION,
        canonical_facts=[g.as_dict() for g in package.catalog.golden()],
        corrections=list(package.corrections),
        verification_report={
            "audited_counts": {"tables": counts.tables, "rows": counts.rows,
                               "na_values": counts.na_values},
            "oracle": {"tables": ORACLE.tables, "rows": ORACLE.rows,
                       "na_values": ORACLE.na_values},
            "relevant_cells": len(package.catalog.cells),
            "verified_cells": len(package.catalog.cells),
        },
    )


def golden_values(entries: list[GoldenEntry]) -> list[GoldenValue]:
    """Spec 1 golden values (four non-null attributes, explicit absence markers)."""

    out = []
    for e in entries:
        printed = NA_MARKER if e.not_applicable else (e.printed_value or ABSENT_MARKER)
        out.append(GoldenValue(printed, e.unit or NO_UNIT_MARKER, e.row_ref, e.cell_ref))
    return out


def golden_document(package: Package, digest: str, source_sha: str) -> dict[str, Any]:
    entries = package.catalog.golden()
    exported = GoldenDatasetExporter().export(
        str(edition_id_for(digest)), digest, golden_values(entries)
    )
    return {
        "format": "series76-golden/1",
        "edition_id": exported.edition_id,
        "manifest_digest": exported.manifest_digest,
        "version": exported.version,
        "source": {"filename": SOURCE_PDF, "sha256": source_sha},
        "cells_sha256": cells_sha256(entries),
        "values": [e.as_dict() for e in entries],
    }


def cells_sha256(entries: list[GoldenEntry]) -> str:
    """SHA-256 of the golden cells, byte-identical to ``series76_eval.oracle.dataset_digest``.

    Recomputed here (not imported) because ``series76_data`` is the dependency
    root; a unit test pins the two implementations to the same digest.
    """

    import hashlib

    h = hashlib.sha256()
    for e in sorted(entries, key=lambda x: f"{x.table}:{x.row}:{x.column}"):
        key = f"{e.table}:{e.row}:{e.column}"
        h.update("\x1f".join([key, e.printed_value, e.unit, str(e.not_applicable),
                              e.note]).encode())
        h.update(b"\x1e")
    return h.hexdigest()


def write_json(path: Path, doc: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=1, ensure_ascii=False, sort_keys=True) + "\n",
                    encoding="utf-8")


def build(audit_dir: Path, replay_dir: Path, golden_path: Path, reviewer: str,
          source_pdf: Path, audited_at: str) -> dict[str, Any]:
    """Audited sheets -> manifest + golden dataset. Refuses an incomplete audit."""

    source_bytes = source_pdf.read_bytes()
    source_sha = compute_sha256(source_bytes)
    payloads = {name: (audit_dir / name).read_bytes() for name in artifact_names()}
    package = parse_package(payloads, reviewer, source_sha)
    counts = package.catalog.counts()
    if (counts.tables, counts.rows, counts.na_values) != (ORACLE.tables, ORACLE.rows,
                                                         ORACLE.na_values):
        fail(
            IngestionErrorCode.ROW_COUNT_MISMATCH,
            affected_unit="edition",
            trigger="audited counts differ from the 7/68/4 oracle; resolve by hand",
            detail={"audited": [counts.tables, counts.rows, counts.na_values]},
        )
    built = ManifestBuilder().build(manifest_data(package, source_sha))
    digest = built.manifest_digest
    manifest = {
        "format": FORMAT,
        "manifest_digest": digest,
        "edition_id": str(edition_id_for(digest)),
        "source": {"filename": SOURCE_PDF, "sha256": source_sha,
                   "byte_size": len(source_bytes)},
        "reviewer": reviewer,
        "audited_at": audited_at,
        "versions": {"normalization": NORMALIZATION_VERSION, "rules": RULES_VERSION,
                     "extractor": EXTRACTOR_VERSION},
        "artifacts": [
            {"name": n, "path": f"../audit/{n}", "sha256": package.artifact_shas[n],
             "transformations": [DRAFT_TRANSFORM if n == DRAFT_FILE else SHEET_TRANSFORM]}
            for n in artifact_names()
        ],
        "counts": {"tables": counts.tables, "rows": counts.rows, "na_values": counts.na_values},
        "corrections": len([c for c in package.corrections
                            if c["prior_value"] != c["verified_value"]]),
        "confirmed_ocr_guesses": len([c for c in package.corrections
                                      if c["prior_value"] == c["verified_value"]]),
    }
    write_json(replay_dir / "manifest.json", manifest)
    write_json(golden_path, golden_document(package, digest, source_sha))
    return manifest


@dataclass(slots=True)
class Replayed:
    manifest: dict[str, Any]
    package: Package
    digest: str


def replay(replay_dir: Path) -> Replayed:
    """Verify every artifact hash, re-derive the catalog, re-check the digest."""

    manifest_path = replay_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("format") != FORMAT:
        raise ValueError(f"{manifest_path}: unsupported manifest format")
    artifacts: dict[str, ReplayArtifact] = {}
    for entry in manifest["artifacts"]:
        payload = (replay_dir / entry["path"]).resolve().read_bytes()
        artifacts[entry["name"]] = ReplayArtifact(
            entry["name"], payload, entry["sha256"], tuple(entry["transformations"])
        )
    view = ReplayManifestView(manifest["manifest_digest"], artifacts, CONFIRMABLE)
    VerifiedReplayExtractor().extract(view, decode=lambda _m: [])  # hashes + transforms
    source_sha = manifest["source"]["sha256"]
    package = parse_package({n: a.payload for n, a in artifacts.items()},
                            manifest["reviewer"], source_sha)
    digest = ManifestBuilder().build(manifest_data(package, source_sha)).manifest_digest
    if digest != manifest["manifest_digest"]:
        fail(
            IngestionErrorCode.HASH_MISMATCH,
            affected_unit="manifest",
            trigger="re-derived manifest digest differs from the recorded one",
            detail={"recorded": manifest["manifest_digest"], "recomputed": digest},
        )
    return Replayed(manifest, package, digest)


def check_golden_round_trip(replayed: Replayed, golden_path: Path) -> None:
    """Spec 1 Property 26: the replayed value set must equal the golden set."""

    doc = json.loads(golden_path.read_text(encoding="utf-8"))
    if doc["manifest_digest"] != replayed.digest:
        fail(
            IngestionErrorCode.HASH_MISMATCH,
            affected_unit="golden",
            trigger="golden dataset is bound to a different manifest digest",
        )
    golden = [GoldenEntry(**v) for v in doc["values"]]
    exporter = GoldenDatasetExporter()
    artifact = exporter.export(doc["edition_id"], doc["manifest_digest"], golden_values(golden))
    report = exporter.verify_round_trip(artifact, golden_values(replayed.package.catalog.golden()))
    if not report.equivalent:
        fail(
            IngestionErrorCode.HASH_MISMATCH,
            affected_unit="golden",
            trigger="round-trip mismatch between replayed values and the golden dataset",
            detail={"missing": [list(k) for k in report.missing_from_reconstruction[:20]],
                    "unexpected": [list(k) for k in report.unexpected_in_reconstruction[:20]]},
        )

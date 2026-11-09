"""Series 76 ETL: ``python -m series76_data <command>``.

Commands (run from ``backend/``):

* ``draft``   — local OCR draft of the audit sheets into ``data/audit/`` (needs the
  ``etl-draft`` extra and poppler; refuses to overwrite sheets already being audited
  unless ``--force``). No language model is involved.
* ``check``   — audit progress: rows marked OK, unresolved ``?`` cells, problems.
* ``build --reviewer NAME`` — audited sheets -> ``data/verified_replay/manifest.json``
  and ``data/golden/golden_dataset.json``. Refuses an incomplete audit or counts
  that differ from the 7/68/4 oracle.
* ``publish`` — verified_replay: verify every artifact hash, re-derive the edition,
  check the golden round trip, publish atomically. Idempotent. With no manifest yet
  it prints that the catalog stays empty and exits 0.

Documental verification of the published edition against the golden dataset is
Spec 6's: ``python -m series76_eval documental-verify``.

Database URL: ``--database-url`` or ``SERIES76_MIGRATE_URL`` or ``DATABASE_URL``.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def _data_dir() -> Path:
    """``SERIES76_DATA_DIR``, else the source tree's ``data/``, else ``./data``.

    In the container the package lives in site-packages, so the data shipped
    with the image is found through the working directory (``/app/data``).
    """

    env = os.environ.get("SERIES76_DATA_DIR")
    if env:
        return Path(env)
    tree = BACKEND / "data"
    return tree if tree.is_dir() else Path.cwd() / "data"


DATA = _data_dir()
AUDIT_DIR = DATA / "audit"
REPLAY_DIR = DATA / "verified_replay"
GOLDEN = DATA / "golden" / "golden_dataset.json"
DEFAULT_PDF = (BACKEND.parent / "Series76_Kiro_Handoff_v1.0" / "02_ORIGINAL_SOURCES"
               / "series_76_electric_data.pdf")


def _out(text: str) -> None:
    sys.stdout.write(text + "\n")


def _db_url(arg: str | None) -> str:
    url = arg or os.environ.get("SERIES76_MIGRATE_URL") or os.environ.get("DATABASE_URL") or ""
    if not url:
        raise SystemExit("no database URL: pass --database-url or set SERIES76_MIGRATE_URL")
    return url


def cmd_draft(args: argparse.Namespace) -> int:
    from series76_data.etl.ocr_draft import CONFIDENCE_FLOOR, draft_from_pdf
    from series76_data.etl.replay import DRAFT_FILE, NOTES_FILE
    from series76_data.etl.sheets import (
        draft_rows,
        note_rows_from_lines,
        render_notes,
        render_sheet,
    )

    out: Path = args.out
    if out.exists() and any(out.glob("T0*.csv")) and not args.force:
        _out(f"refusing to overwrite the audit sheets in {out} (use --force to redo the draft)")
        return 2
    sheets, notes, info = draft_from_pdf(args.pdf)
    out.mkdir(parents=True, exist_ok=True)
    snapshot: dict[str, object] = {"engine": info, "sheets": {}, "notes": []}
    star: dict[str, list[str]] = {}
    for sheet in sheets:
        rows = draft_rows(sheet, CONFIDENCE_FLOOR)
        (out / f"{sheet.table}.csv").write_text(render_sheet(sheet.table, rows), encoding="utf-8")
        snapshot["sheets"][sheet.table] = rows  # type: ignore[index]
        for row in rows:
            pn = row["pn"].lstrip("?")
            if "*" in pn:
                for scope in {n.tables for n in notes if sheet.table in n.tables.split(",")}:
                    star.setdefault(scope, []).append(pn.split("|")[0])
    note_rows = note_rows_from_lines(notes, star)
    (out / NOTES_FILE).write_text(render_notes(note_rows), encoding="utf-8")
    snapshot["notes"] = [n[2] for n in note_rows]
    (out / DRAFT_FILE).write_text(json.dumps(snapshot, indent=1, ensure_ascii=False) + "\n",
                                  encoding="utf-8")
    unsure = sum(v.startswith("?") for rows in snapshot["sheets"].values()  # type: ignore[attr-defined]
                 for row in rows for v in row.values())
    _out(f"draft written to {out}: {sum(len(s.rows) for s in sheets)} rows, "
         f"{unsure} unresolved '?' cells, {len(note_rows)} notes")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    from series76_data.etl.layout import TABLES
    from series76_data.etl.replay import NOTES_FILE
    from series76_data.etl.sheets import AuditProblems, SheetError, parse_notes, parse_sheet

    problems = AuditProblems()
    total = unsure = 0
    for t in TABLES:
        path: Path = args.audit_dir / f"{t.code}.csv"
        text = path.read_text(encoding="utf-8")
        try:
            sheet = parse_sheet(t.code, text, AuditProblems())
        except SheetError as exc:
            problems.add(path.name, str(exc))
            continue
        parse_sheet(t.code, text, problems)
        total += len(sheet.rows)
        unsure += sum(v.startswith("?") for r in sheet.rows for v in [r.printed_pn,
                                                                       *r.cells.values()])
    ok = total - sum("row not audited" in p for p in problems.problems)
    try:
        notes = parse_notes((args.audit_dir / NOTES_FILE).read_text(encoding="utf-8"), problems)
    except SheetError as exc:
        problems.add(NOTES_FILE, str(exc))
        notes = ()
    _out(f"rows marked OK: {ok}/{total}; unresolved '?' cells: {unsure}; notes: {len(notes)}")
    if problems.problems:
        _out(f"{len(problems.problems)} problem(s):")
        for p in problems.problems[: args.limit]:
            _out(f"  - {p}")
        if len(problems.problems) > args.limit:
            _out(f"  … and {len(problems.problems) - args.limit} more (use --limit)")
        return 1
    _out("all sheets are fully audited: run `python -m series76_data build --reviewer ...`")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    from series76_data.etl.replay import build

    audited_at = args.audited_at or datetime.date.today().isoformat()
    manifest = build(args.audit_dir, REPLAY_DIR, GOLDEN, args.reviewer, args.pdf, audited_at)
    _out(f"manifest {manifest['manifest_digest']} (edition {manifest['edition_id']})")
    _out(f"counts {manifest['counts']}; corrections {manifest['corrections']}; "
         f"confirmed OCR guesses {manifest['confirmed_ocr_guesses']}")
    _out(f"wrote {REPLAY_DIR / 'manifest.json'} and {GOLDEN}")
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    if not (REPLAY_DIR / "manifest.json").exists():
        _out("no verified_replay manifest yet (the manual audit is pending): "
             "the catalog stays empty and the assistant reports that no data is available")
        return 0
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from series76_data.etl.load import publish_replayed
    from series76_data.etl.replay import check_golden_round_trip, replay

    replayed = replay(REPLAY_DIR)
    check_golden_round_trip(replayed, GOLDEN)
    engine = create_engine(_db_url(args.database_url))
    with Session(engine) as session:
        edition, created = publish_replayed(session, replayed)
    state = "published" if created else "already published (idempotent re-run recorded)"
    _out(f"edition {edition.edition_id} {state}; manifest {replayed.digest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m series76_data", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("draft")
    p.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    p.add_argument("--out", type=Path, default=AUDIT_DIR)
    p.add_argument("--force", action="store_true")
    p = sub.add_parser("check")
    p.add_argument("--audit-dir", type=Path, default=AUDIT_DIR)
    p.add_argument("--limit", type=int, default=40)
    p = sub.add_parser("build")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--audit-dir", type=Path, default=AUDIT_DIR)
    p.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    p.add_argument("--audited-at", default=None)
    p = sub.add_parser("publish")
    p.add_argument("--database-url", default=None)
    args = parser.parse_args(argv)
    handlers = {"draft": cmd_draft, "check": cmd_check, "build": cmd_build,
                "publish": cmd_publish}
    return handlers[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())

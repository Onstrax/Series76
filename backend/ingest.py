#!/usr/bin/env python3
"""Series 76 ingestion: ``series_76_electric_data.pdf`` -> the catalog the tools query.

This is the assessment's ``ingest.py``. It is a thin entry point over the ETL
package (``python -m series76_data``); every step is deterministic and no
language model is involved.

Pipeline (run from ``backend/``)::

    python ingest.py                  # verify the shipped processed data (no DB, no network)
    python ingest.py draft            # 1. local OCR draft of the 7 tables -> data/audit/*.csv
    python ingest.py check            # 2. audit progress / problems of the human-reviewed sheets
    python ingest.py build --reviewer "Name" [--audited-at YYYY-MM-DD]
                                      # 3. audited sheets -> data/verified_replay/manifest.json
                                      #    + data/golden/golden_dataset.json
    python ingest.py publish          # 4. verify hashes, re-derive, publish into PostgreSQL
    python ingest.py all --reviewer "Name"   # 2 + 3 + 4

The PDF tables are images, so step 1 is OCR and step 2 is a person checking every
cell against the PDF (Spec 1, Requirement 3). The audited sheets, the manifest and
the golden dataset are committed, so a fresh clone only needs step 4, which the
Docker Compose ``migrate`` job runs on every start.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))  # works without `pip install`

from series76_data.__main__ import GOLDEN, REPLAY_DIR  # noqa: E402
from series76_data.__main__ import main as etl  # noqa: E402


def verify() -> int:
    """Re-derive the published edition from the shipped artifacts (offline)."""

    from series76_data.etl.replay import check_golden_round_trip, replay

    if not (REPLAY_DIR / "manifest.json").exists():
        print("no verified_replay manifest yet: run `draft`, audit, `check`, then `build`")
        return 1
    replayed = replay(REPLAY_DIR)  # verifies every artifact's SHA-256 and the digest
    check_golden_round_trip(replayed, GOLDEN)
    counts = replayed.package.catalog.counts()
    print(f"verified_replay OK: manifest {replayed.digest}")
    print(f"  {counts.tables} tables, {counts.rows} rows, {counts.na_values} N/A rows (T03)")
    print(f"  processed data: {REPLAY_DIR / 'manifest.json'}")
    print(f"                  {GOLDEN}")
    print("  load it into PostgreSQL with: python ingest.py publish")
    return 0


def run(argv: list[str]) -> int:
    if not argv or argv[0] in ("verify",):
        return verify()
    if argv[0] == "all":
        rest = argv[1:]
        for step in (["check"], ["build", *rest], ["publish"]):
            code = etl(step)
            if code != 0:
                return code
        return 0
    return etl(argv)


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))

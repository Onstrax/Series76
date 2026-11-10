"""Spec 1 ETL: audit sheets, OCR-draft geometry, replay, golden (synthetic data only)."""

from __future__ import annotations

import json
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest
from _etl_fixture import REVIEWER, pn, render, sheet_rows, write_package
from hypothesis import given
from hypothesis import strategies as st

from series76_data.errors import IngestionError, IngestionErrorCode
from series76_data.etl.facts import build_catalog
from series76_data.etl.layout import TABLES, TABLES_BY_CODE
from series76_data.etl.ocr_draft import Rule, Token, _split_token, layout_table, reconcile
from series76_data.etl.replay import (
    build,
    cells_sha256,
    check_golden_round_trip,
    edition_id_for,
    replay,
)
from series76_data.etl.sheets import (
    AuditProblems,
    DraftCell,
    NoteDraft,
    SheetDraft,
    _draft_text,
    note_rows_from_lines,
    parse_sheet,
    suspicious,
)
from series76_data.models.enums import AvailabilityStatus, FrequencyState
from series76_eval.oracle import GoldenCell, dataset_digest


def _build(tmp_path: Path) -> tuple[Path, Path, Path, Path, dict[str, object]]:
    audit, replay_dir = tmp_path / "audit", tmp_path / "verified_replay"
    golden, pdf = tmp_path / "golden" / "golden_dataset.json", tmp_path / "source.pdf"
    write_package(audit, pdf)
    manifest = build(audit, replay_dir, golden, REVIEWER, pdf, "2026-11-09")
    return audit, replay_dir, golden, pdf, manifest


# --- sheets -----------------------------------------------------------------


@pytest.mark.parametrize("text", ["5.300", "06", "763CO0-1133OC0O/A", "761A00-1130O000/A"])
def test_classic_ocr_confusions_are_flagged(text: str) -> None:
    assert suspicious(text)
    assert _draft_text(DraftCell(text, 1.0), 0.9).startswith("?")


@pytest.mark.parametrize(
    "text", ["1,330", "0.7", "17.0", "761A00-11300000/A", "766A00-11320000/A*"]
)
def test_plausible_values_pass_through(text: str) -> None:
    assert not suspicious(text)
    assert _draft_text(DraftCell(text, 0.99), 0.9) == text


def test_low_confidence_and_empty_reads_stay_unresolved() -> None:
    assert _draft_text(DraftCell("40", 0.5), 0.9) == "?40"
    assert _draft_text(DraftCell("", 0.0), 0.9) == "?"


def test_unaudited_unresolved_and_malformed_rows_are_refused() -> None:
    rows = sheet_rows(4, "T04")
    rows[0]["onoff.torque_nm"] = "?70"
    rows[1]["onoff.duty_s4_pct"] = "thirty"
    rows[0]["meas.fla_a"] = "^"  # first row has nothing above
    text = render("T04", rows).replace(",OK,", ",,", 1)
    problems = AuditProblems()
    parse_sheet("T04", text, problems)
    joined = "\n".join(problems.problems)
    assert "row not audited" in joined
    assert "unresolved OCR guess '?70'" in joined
    assert "'thirty' is not a printed number" in joined
    assert "'^' on the first row" in joined


@given(st.lists(st.sampled_from(["1,330", "0.7", "N/A", "", "960", "12.8"]), min_size=8,
                max_size=8))
def test_property_sheet_round_trip_preserves_printed_text(values: list[str]) -> None:
    layout = TABLES_BY_CODE["T05"]
    row = {"pn": pn(5, 1), **dict(zip(layout.column_keys, values, strict=True))}
    sheet = parse_sheet("T05", render("T05", [row]), AuditProblems())
    assert sheet.rows[0].cells == {k: v for k, v in row.items() if k != "pn"}


def test_notes_group_continuations_and_prefill_star_rows() -> None:
    lines = [NoteDraft("T04,T05", "NOTES"), NoteDraft("T04,T05", "Hazardous Location"),
             NoteDraft("T04,T05", "Class I"), NoteDraft("T04,T05", "1. Full load current"),
             NoteDraft("T01,T02", "* Sizes 6 and 7")]
    notes = note_rows_from_lines(lines, {"T01,T02": ["766A00-11320000/A*"]})
    assert [n[1] for n in notes] == ["", "1", "*"]
    assert notes[0][2] == "?Hazardous Location\nClass I"  # every note text starts unresolved
    assert notes[2][3] == "?766A00-11320000/A*"


# --- OCR-draft geometry (pure) ----------------------------------------------


def _tok(text: str, x: float, y: float) -> Token:
    return Token(text, 0.99, x - 8, y - 5, x + 8, y + 5)


def test_layout_merges_only_motor_power_and_never_copies_a_missing_value() -> None:
    layout = TABLES_BY_CODE["T04"]  # 8 columns, Motor Power last
    xs = [100 + 40 * i for i in range(8)]
    ys = [50, 70, 90]
    tokens = [_tok(pn(4, r + 1), 40, y) for r, y in enumerate(ys)]
    for r, y in enumerate(ys):
        for c in range(7):
            if (r, c) == (1, 2):  # the engine missed this cell
                continue
            tokens.append(_tok(str(10 + r * 10 + c), xs[c], y))
    tokens.append(_tok("40", xs[7], 60))  # merged over rows 1-2
    tokens.append(_tok("90", xs[7], 90))
    rules = [Rule(40, ((0, 500),)), Rule(80, ((0, 500),)), Rule(100, ((0, 500),))]
    sheet = layout_table(layout, tokens, rules)
    cells = [[c.text for c in row] for _, row in sheet.rows]
    assert [r[7] for r in cells] == ["40", "^", "90"]
    assert cells[1][2] == ""  # left empty -> drafted as '?', never '^'
    assert all(cells[r][2] != "^" for r in range(3))


def test_layout_na_block_spans_data_columns_but_not_motor_power() -> None:
    layout = TABLES_BY_CODE["T03"]
    k = len(layout.columns)
    xs = [100 + 40 * i for i in range(k)]
    ys = [50, 70, 90]
    tokens = [_tok(pn(3, r + 1), 40, y) for r, y in enumerate(ys)]
    tokens.append(_tok("N/A", 300, 60))  # centred over rows 1-2
    tokens += [_tok(str(5 + c), xs[c], 90) for c in range(k)]
    rules = [Rule(40, ((0, 900),)), Rule(80, ((0, 900),)), Rule(100, ((0, 900),))]
    cells = [[c.text for c in row] for _, row in layout_table(layout, tokens, rules).rows]
    assert cells[0][0] == "N/A" and set(cells[0][1:k - 1]) == {"<"}
    assert set(cells[1][: k - 1]) == {"^"}
    assert cells[0][k - 1] == "" and cells[1][k - 1] == ""  # Motor Power left to the auditor


def test_rule_that_stops_short_of_a_merged_column_does_not_split_it() -> None:
    layout = TABLES_BY_CODE["T04"]
    xs = [100 + 40 * i for i in range(8)]
    ys = [50, 70]
    tokens = [_tok(pn(4, r + 1), 40, y) for r, y in enumerate(ys)]
    tokens += [_tok(str(20 + c), xs[c], y) for y in ys for c in range(7)]
    tokens.append(_tok("700", xs[7], 60))
    # the rule between the rows does NOT cross the Motor Power column
    rules = [Rule(40, ((0, 500),)), Rule(60, ((0, xs[6] + 20),)), Rule(80, ((0, 500),))]
    cells = [[c.text for c in row] for _, row in layout_table(layout, tokens, rules).rows]
    assert [r[7] for r in cells] == ["700", "^"]


def test_reconcile_keeps_agreement_and_flags_disagreement() -> None:
    a = SheetDraft("T04", [(DraftCell("P", 0.99),
                            [DraftCell("1,330", 0.99), DraftCell("40", 0.95)])])
    b = SheetDraft("T04", [(DraftCell("P", 0.98),
                            [DraftCell("1.330", 0.99), DraftCell("40", 0.99)])])
    (pn_cell, cells), = reconcile(a, b).rows
    assert pn_cell == DraftCell("P", 0.98)
    assert cells[0] == DraftCell("1,330|1.330", 0.0) and cells[1] == DraftCell("40", 0.95)


def test_glued_decimals_are_split() -> None:
    parts = _split_token(Token("17.017.0", 0.9, 0, 0, 80, 10))
    assert [p.text for p in parts] == ["17.0", "17.0"] and parts[0].x1 <= parts[1].x0


# --- typed facts --------------------------------------------------------------


def _catalog(tmp_path: Path):  # type: ignore[no-untyped-def]
    _, replay_dir, _, _, _ = _build(tmp_path)
    return replay(replay_dir).package.catalog


def test_counts_match_the_oracle_shape(tmp_path: Path) -> None:
    counts = _catalog(tmp_path).counts()
    assert (counts.tables, counts.rows, counts.na_values) == (7, 68, 4)


def test_service_attribution_follows_the_printed_column_groups(tmp_path: Path) -> None:
    cat = _catalog(tmp_path)
    row = next(r for r in cat.rows if r.table == "T01" and r.row == 1)
    (onoff_label, onoff), (mod_label, mod) = row.services
    by_on, by_mod = {f.field: f for f in onoff}, {f.field: f for f in mod}
    assert (onoff_label, mod_label) == ("On/Off", "Modulating")
    assert by_on["cycles_per_hour"].status is AvailabilityStatus.AVAILABLE
    assert by_on["starts_per_hour"].status is AvailabilityStatus.NOT_DOCUMENTED
    assert by_on["starts_per_hour"].cell is None  # never copied from the other service
    assert by_mod["starts_per_hour"].status is AvailabilityStatus.AVAILABLE
    assert by_mod["cycles_per_hour"].status is AvailabilityStatus.NOT_DOCUMENTED
    assert [c.frequency_hz for c in row.conditions] == [Decimal(60), Decimal(50)]


def test_t03_is_unqualified_and_na_stays_na(tmp_path: Path) -> None:
    cat = _catalog(tmp_path)
    na_row = next(r for r in cat.rows if r.table == "T03" and r.row == 2)
    assert na_row.services == () and na_row.unqualified is not None
    assert {f.status for f in na_row.unqualified} == {AvailabilityStatus.NOT_APPLICABLE}
    assert {f.cell for f in na_row.unqualified} == {"T03#1:unq.torque_inlbs"}  # one merged cell
    assert na_row.motor_power.status is AvailabilityStatus.NOT_DOCUMENTED  # printed nothing
    assert cat.cells["T03#1:unq.torque_inlbs"].rows == [1, 2, 3, 4]


def test_t04_t05_print_no_frequency_and_stay_distinct(tmp_path: Path) -> None:
    cat = _catalog(tmp_path)
    t04 = next(r for r in cat.rows if r.table == "T04")
    t05 = next(r for r in cat.rows if r.table == "T05")
    assert [c.frequency_state for c in t04.conditions] == [FrequencyState.NOT_SPECIFIED]
    assert t04.conditions[0].frequency_hz is None
    assert [s for s, _ in t04.services] == ["On/Off"] and [s for s, _ in t05.services] == [
        "Modulating"]


def test_printed_thousands_are_parsed_exactly(tmp_path: Path) -> None:
    cat = _catalog(tmp_path)
    fields = [f for r in cat.rows for _, fs in r.services for f in fs if "," in f.printed]
    assert fields and all(f.value == Decimal(f.printed.replace(",", "")) for f in fields)


# --- build / replay / golden ----------------------------------------------------


def test_build_is_deterministic_and_binds_golden_to_the_edition(tmp_path: Path) -> None:
    audit, replay_dir, golden, pdf, manifest = _build(tmp_path)
    again = build(audit, replay_dir, golden, REVIEWER, pdf, "2026-11-09")
    assert again["manifest_digest"] == manifest["manifest_digest"]
    doc = json.loads(golden.read_text())
    assert doc["edition_id"] == str(edition_id_for(str(manifest["manifest_digest"])))
    assert doc["manifest_digest"] == manifest["manifest_digest"]
    assert manifest["counts"] == {"tables": 7, "rows": 68, "na_values": 4}
    check_golden_round_trip(replay(replay_dir), golden)


def test_tampered_artifact_halts_replay(tmp_path: Path) -> None:
    audit, replay_dir, _, _, _ = _build(tmp_path)
    path = audit / "T02.csv"
    path.write_text(path.read_text().replace(",OK,", ",OK ,", 1))
    with pytest.raises(IngestionError) as err:
        replay(replay_dir)
    assert err.value.failure.code is IngestionErrorCode.HASH_MISMATCH


def test_golden_round_trip_mismatch_is_rejected(tmp_path: Path) -> None:
    _, replay_dir, golden, _, _ = _build(tmp_path)
    doc = json.loads(golden.read_text())
    doc["values"][1]["printed_value"] = "999999"
    golden.write_text(json.dumps(doc))
    with pytest.raises(IngestionError):
        check_golden_round_trip(replay(replay_dir), golden)


def test_incomplete_audit_and_wrong_counts_are_refused(tmp_path: Path) -> None:
    audit, pdf = tmp_path / "audit", tmp_path / "s.pdf"
    write_package(audit, pdf)
    t05 = audit / "T05.csv"
    original = t05.read_text()
    t05.write_text(original.replace(",OK,", ",,", 1))
    with pytest.raises(ValueError, match="row not audited"):
        build(audit, tmp_path / "r", tmp_path / "g.json", REVIEWER, pdf, "d")
    t05.write_text("\n".join(original.splitlines()[:-1]) + "\n")  # drop a row: 67 rows
    with pytest.raises(IngestionError) as err:
        build(audit, tmp_path / "r", tmp_path / "g.json", REVIEWER, pdf, "d")
    assert err.value.failure.code is IngestionErrorCode.ROW_COUNT_MISMATCH


def test_corrections_need_a_justification_and_are_recorded(tmp_path: Path) -> None:
    audit, pdf = tmp_path / "audit", tmp_path / "s.pdf"
    write_package(audit, pdf)
    draft = json.loads((audit / "ocr_draft.json").read_text())
    draft["sheets"]["T04"][0]["onoff.torque_nm"] = "?7O"  # what the OCR guessed
    (audit / "ocr_draft.json").write_text(json.dumps(draft))
    rows = sheet_rows(4, "T04")
    rows[0]["onoff.torque_nm"] = "71"  # what the auditor read in the PDF
    (audit / "T04.csv").write_text(render("T04", rows))

    with pytest.raises(ValueError, match="write a short Justification"):
        build(audit, tmp_path / "r", tmp_path / "g.json", REVIEWER, pdf, "d")

    text = (audit / "T04.csv").read_text().replace(",OK,\n", ",OK,PDF p3 shows 71\n", 1)
    (audit / "T04.csv").write_text(text)
    build(audit, tmp_path / "r", tmp_path / "g.json", REVIEWER, pdf, "d")
    package = replay(tmp_path / "r").package
    fix = next(c for c in package.corrections if c["cell"] == "T04#1:onoff.torque_nm")
    assert fix == {"cell": "T04#1:onoff.torque_nm", "prior_value": "7O", "verified_value": "71",
                   "reviewer": REVIEWER, "justification": "PDF p3 shows 71",
                   "source_document_hash": fix["source_document_hash"]}


def test_choosing_an_ocr_read_is_a_confirmation_not_a_correction(tmp_path: Path) -> None:
    audit, pdf = tmp_path / "audit", tmp_path / "s.pdf"
    sheets = write_package(audit, pdf)
    value = sheets["T04"][0]["onoff.torque_nm"]
    draft = json.loads((audit / "ocr_draft.json").read_text())
    draft["sheets"]["T04"][0]["onoff.torque_nm"] = f"?{value}|9{value}"  # two OCR reads
    (audit / "ocr_draft.json").write_text(json.dumps(draft))

    build(audit, tmp_path / "r", tmp_path / "g.json", REVIEWER, pdf, "d")  # no justification
    package = replay(tmp_path / "r").package
    fix = next(c for c in package.corrections if c["cell"] == "T04#1:onoff.torque_nm")
    assert fix["verified_value"] == value
    assert fix["justification"] == f"OCR reads {value} / 9{value}: the PDF image shows {value}"


def test_a_leading_zero_is_refused(tmp_path: Path) -> None:
    rows = sheet_rows(4, "T04")
    rows[0]["onoff.torque_nm"] = "0" + rows[0]["onoff.torque_nm"]
    problems = AuditProblems()
    parse_sheet("T04", render("T04", rows), problems)
    assert any("leading zero" in p for p in problems.problems)


def test_a_column_mixing_decimals_and_whole_numbers_is_flagged(tmp_path: Path) -> None:
    rows = sheet_rows(4, "T04")
    key = "onoff.torque_nm"
    assert all("." not in r[key] for r in rows)
    rows[2][key] = rows[2][key].replace(",", ".") if "," in rows[2][key] else rows[2][key] + ".0"
    problems = AuditProblems()
    parse_sheet("T04", render("T04", rows), problems)
    assert any("T04.csv rows 3" in p and "point/comma" in p for p in problems.problems)


def test_golden_cells_digest_matches_the_spec6_oracle(tmp_path: Path) -> None:
    cat = _catalog(tmp_path)
    entries = cat.golden()
    cells = tuple(GoldenCell(e.table, e.row, e.column, e.printed_value, e.unit, e.not_applicable,
                             e.note) for e in entries)
    assert cells_sha256(entries) == dataset_digest(cells)
    assert len(entries) == 68 + sum(len(t.columns) * n for t, n in
                                    zip(TABLES, [11, 16, 11, 5, 5, 10, 10], strict=True)) + 3


def test_replay_imports_no_network_model_or_ocr_client() -> None:
    code = ("import sys, series76_data.etl.replay, series76_data.etl.load; "
            "bad = [m for m in sys.modules if m.split('.')[0] in "
            "{'openai','langchain','httpx','rapidocr_onnxruntime','cv2','google','requests'}]; "
            "print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"


def test_catalog_builder_has_no_hidden_inputs(tmp_path: Path) -> None:
    a = _catalog(tmp_path / "a")
    b = build_catalog(a.sheets, a.notes)
    assert [r.__repr__() for r in a.rows] == [r.__repr__() for r in b.rows]


def test_ingest_entry_point_verifies_the_shipped_processed_data() -> None:
    """`python ingest.py` (the assessment's ingestion script) re-derives the edition."""

    backend = Path(__file__).resolve().parents[2]
    if not (backend / "data" / "verified_replay" / "manifest.json").exists():
        pytest.skip("no audited edition committed")
    proc = subprocess.run([sys.executable, "ingest.py"], cwd=backend, capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "verified_replay OK" in proc.stdout and "7 tables, 68 rows, 4 N/A" in proc.stdout

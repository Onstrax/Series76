# Manual audit of `series_76_electric_data.pdf` (Spec 1, Requirement 3)

The PDF tables are images, so every catalog value must be confirmed by a person.
The files in this folder are an **OCR draft** made by a local OCR engine. No language
model was involved. The draft is only a candidate: nothing in it is published until a
reviewer has confirmed every row against the PDF.

| File | Content |
|---|---|
| `T01.csv` … `T07.csv` | One sheet per printed table. Each sheet has the same rows and columns as the PDF. |
| `notes.csv` | The printed notes, with the tables and rows each note covers. |
| `ocr_draft.json` | The untouched OCR draft. Do not edit it: corrections are computed against it. |

Open the PDF next to a sheet. Edit the sheets in a text editor (or VS Code): spreadsheet
programs rewrite values such as `1,330` or `17.0`. Save as UTF-8. The tables are laid out as follows:

| Sheet | PDF page | Heading |
|---|---|---|
| T01 | 1 (top) | Weatherproof, 110V Single Phase |
| T02 | 1 (bottom) | Weatherproof, 220V Single Phase |
| T03 | 2 | Weatherproof, 220V 3 Phase |
| T04 | 3 (top) | Explosionproof, 24V AC/DC On/Off |
| T05 | 3 (bottom) | Explosionproof, 24V DC Modulating |
| T06 | 4 (top) | Explosionproof, 110V Single Phase |
| T07 | 4 (bottom) | Explosionproof, 220V Single Phase |

## Cell syntax

A cell holds exactly what the PDF prints in it:

| Write | Meaning |
|---|---|
| `1,330` `0.7` `17.0` | The number as printed: same digits, same decimals, thousands commas kept. |
| `N/A` | The PDF prints N/A. |
| *(empty)* | Nothing is printed in that cell. |
| `^` | Same merged printed cell as the cell **above** (for example, one Motor Power value spanning several rows). |
| `<` | Same merged printed cell as the cell **to the left** (the T03 N/A block). |
| `?…` | An OCR guess not yet resolved. `?a\|b` means the two OCR reads disagreed. Replace it with the printed value. |

## For each row

1. Compare the part number character by character. Check `0` against `O`, `1` against `I`,
   and the trailing `*`.
2. Compare every cell with the PDF: digits, decimal places, thousands separators, and N/A
   versus empty.
3. Check the merged cells: Motor Power `^` must cover exactly the rows of its printed group.
4. Resolve every `?` cell.
5. Write `OK` in the `Audit` column.
6. If you wrote a value that no OCR read produced, write a short reason in
   `Justification` (for example, `PDF p1 reads 108`). Choosing one of the reads of a `?`
   cell needs no justification: it is recorded as a confirmation of that read.

For each note in `notes.csv`:

1. Make the text letter-for-letter equal to the PDF, spaces included, and remove the
   leading `?`.
2. Set `Rows`: either `all`, or the exact part numbers it covers, separated by `;`.
3. Write `OK` in `Audit`.

## Mapping decisions to confirm

These decisions are encoded in `series76_data/etl/layout.py`. If you disagree with any of
them, say so before building:

1. In T01, T02, T06 and T07, *Cycles Per Hour* belongs to the **On/Off** service and
   *Starts Per Hour* to the **Modulating** service, following the printed column groups.
2. T03 attributes no service: it is stored without a service, with cycles and starts kept
   as two separate fields.
3. T04 and T05 print no frequency, so it is stored as *not specified* (no Hz value is
   invented). They are two distinct configurations.
4. In the T03 N/A rows, the draft leaves Motor Power as `?`. Write `<` if the printed N/A
   block covers that column, or leave it empty if nothing is printed there.

## Then

```bash
cd backend
.venv/bin/python -m series76_data check                     # progress and remaining problems
.venv/bin/python -m series76_data build --reviewer "<name>"  # manifest + golden dataset
```

`build` refuses the audit in either of these cases:

- a row is not marked `OK`, or a `?` remains;
- a row holds a value that no OCR read produced, and has no justification;
- a value has a leading zero, or a column mixes decimal and whole numbers (usually a
  point read as a comma);
- the counts differ from the expected 7 tables, 68 rows and 4 N/A rows (in that case it
  reports the discrepancy and fixes nothing).

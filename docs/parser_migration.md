# Vendor Parser Migration Guide

This is a project-local playbook for adding vendor parsers. It is not a global
Codex skill and it is not app runtime logic. Its job is to keep each vendor
migration consistent, inspectable, and easy to validate.

## Goal

Each migrated vendor should have:

```text
parsers/<Vendor>/input_schema.json
parsers/<Vendor>/parser.py
data/processed/<Vendor>/<Vendor>.csv
```

The parser should convert a local raw file from `data/inbox/` into normalized
rows that match the approved historical CSV shape for that vendor.

## Boundaries

Vendor parsers must not:

- download files from ShareFile
- upload files to ShareFile
- write approval outputs
- update Django models
- decide file status

Vendor parsers should only do this:

```text
local file path + input schema + output columns -> normalized rows
```

The Django workflow owns validation, preview, approval staging, status changes,
ShareFile upload, and comparison charts.

## Source Material

Start every migration with these files:

- raw source file under `data/inbox/`
- old approved example under `_old/final/<Vendor>.csv`
- any existing vendor parser material under `_old/`

Treat `_old/final/<Vendor>.csv` as the output benchmark. It tells you the
columns, row grain, vendor casing, default values, and whether records are
daily aggregates or more detailed rows.

## Migration Checklist

1. Inspect the old approved CSV.

   Check headers, row count, date range, duplicate dates, totals, and stable
   default values such as `Brand`, `Channel`, and `Platform`.

2. Inspect the raw workbook or CSV.

   For Excel files, list sheets, dimensions, visible tables, header rows,
   total rows, blank separators, merged-looking layout, number formats, and
   any weird values like currency symbols in impression fields.

3. Decide the output grain.

   Match the approved history, not the raw workbook layout. If the raw file has
   separate tables but the approved history has one row per date, aggregate the
   tables into one daily row.

4. Create `input_schema.json`.

   The schema should describe where the data lives, not perform parsing. Include
   sheet name, file type, header row, table definitions, selected columns,
   skip rules, comparison window, and output defaults.

5. Create `parser.py`.

   The parser should expose:

   ```python
   def parse_file(source_path: Path, input_schema: dict[str, Any], output_columns: list[str]) -> list[dict[str, Any]]:
       ...
   ```

   It should parse dates and numbers explicitly, reject bad rows with clear
   errors, skip intentional blanks/totals, and return rows in `output_columns`
   order.

6. Validate against the real source file.

   Confirm row count, period start/end, total spend, total impressions, first
   row, and last row. If totals do not match the source file, stop and inspect
   the raw table again.

7. Validate through the Django parser workflow.

   Confirm parser validation is OK, approved history is found, the preview
   summary is correct, and the comparison chart has the parsed period plus the
   latest approved history periods when available.

8. Add a focused workflow test.

   Build a small workbook fixture that captures the important vendor-specific
   behavior. For example, TVM tests currency-looking impressions, and TAIV tests
   Prime plus Retail aggregation.

9. Update documentation.

   Add the vendor to the README parser list and document any non-obvious rule,
   such as table aggregation or approved-history canonicalization.

## Current Examples

`Loop` is the simple baseline parser:

- one sheet
- one table
- one daily row per source row

`TVM` adds raw-format cleanup:

- one sheet
- one table
- blank separator rows
- impressions may appear with currency formatting

`TAIV` adds multi-table aggregation:

- one sheet
- `Prime` table in columns A:C
- `Retail` table in columns E:G
- combined into one daily row per date to match approved TAIV history

`PodcastOne` adds multi-sheet aggregation:

- BASE daily sheet
- WC daily sheet
- both sheets use `Day`, `Audio Impressions`, and `$ By Day`
- rows are grouped by `Day` across both sheets
- `Audio Impressions` becomes `Impressions`
- `$ By Day` becomes `Spend`

`Octopus` adds multi-table aggregation from one sheet:

- `Daily Spend` sheet
- `DOOH` table in columns A:C
- `Rideshare` table in columns A:C later on the same sheet
- both tables are grouped by date into one daily row
- `Impressions` and `Spend` are summed across both tables

`RallyAdMedia` adds fixed multi-sheet aggregation:

- sheets `BOL`, `SB`, `WC`, and `SS`
- each sheet contributes rows keyed by `DATE_LABEL`
- `Imps.` becomes `Impressions`
- `Total Spend` becomes `Spend`
- all four sheets are grouped by date into one daily row
- the app vendor is `RallyAdMedia`; legacy or mistaken `ReallyAdMedia` rows should be renamed

## App Review Flow

The Parsing page has two explicit review phases:

1. Opening a file row shows raw workbook or CSV contents so the user can verify the source layout before parsing.
2. Clicking `Parse` validates the parser and switches to a generated-output review with four tabs: `Spend`, `Impressions`, `Cost / impression`, and `Final CSV`.

The chart tabs compare the candidate output with up to two previous approved
vendor periods from `data/processed/<Vendor>/`. Chart points are grouped by
date, so parsers that emit multiple rows for the same date still show daily
spend, daily impressions, and daily spend divided by daily impressions.

The `Final CSV` tab is the table the user should visually inspect before
clicking `Approval`. The preview route does not write `data/output/`; the
Approval action reparses, writes the versioned CSV, uploads it to ShareFile
Approval, and records the `ParsedOutput`.

## Validation Commands

Use these after adding or changing a parser:

```bash
.venv/bin/python web/manage.py check
.venv/bin/python web/manage.py makemigrations --check --dry-run
.venv/bin/python web/manage.py test pipeline_dashboard
PYTHONPATH=src .venv/bin/python -m compileall -q scripts src web parsers
git diff --check
```

For a real-file parser check, run the parser directly first, then use the
Django parser workflow. The direct parser check catches raw parsing bugs; the
Django workflow check catches schema, approved-history, and preview integration
bugs.

## Common Failure Modes

- Vendor casing does not match folder names, for example `Taiv` vs `TAIV`.
- The raw workbook has total rows that look like data except for a blank date.
- The raw workbook has multiple tables but the approved history is aggregated.
- Numeric values are stored as strings with `$`, commas, or parentheses.
- The parser returns columns that do not match the approved historical CSV.
- The parser writes files or changes status, which belongs to the workflow.
- A parser passes direct parsing but fails in the app because approved history
  is in the wrong `data/processed/<Vendor>/` folder.

## When To Generalize

Do not build a universal parser too early. Keep vendor logic in
`parsers/<Vendor>/`.

Generalize only when several parsers repeat the same code and the abstraction
does not hide vendor-specific assumptions. Good candidates are date parsing,
decimal parsing, output row ordering, and workbook inspection helpers.

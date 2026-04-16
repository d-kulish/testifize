# Testifize Data Engineer Technical Assessment

This repository contains the assessment write-up, exploratory profiling, vendor-specific parsing scripts, normalized CSV outputs, and reconciliation checks for three unstable Excel inputs that need to be loaded into a shared marketing schema.

## Python setup

Create a local virtual environment and install the project dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
To check how preprocessing works, run ```python3 scripts/vendor_a.py```. 


## Inputs

### Task

- [Assessment brief](Inputs/Data_Engineer_Technical_Assessment.md)

### Limitations

- The source workbooks are not clean machine-friendly tables. They include title rows, side tables, subtotal rows, footer rows, and presentation-style layout.
- Not all target-schema fields are available directly in the source files, so some values had to be derived from workbook context.
- Vendor B and Vendor C are provided at weekly grain, so daily rows had to be proportioned from weekly totals.
- Vendor C contains inconsistent spend fields, so `Total Spend` could not be trusted as the source of truth.

### Input files

- [Vendor_A_MediaWave_Jan2026.xlsx](Inputs/Vendor_A_MediaWave_Jan2026.xlsx): daily CTV file with mixed date formats, mixed brand naming, and non-numeric impressions.
- [Vendor_B_StreetLevel_Jan2026.xlsx](Inputs/Vendor_B_StreetLevel_Jan2026.xlsx): DOOH workbook with weekly `StakePoint` detail plus aggregate spend totals for `WagerLine` and `NeonSpin`.
- [Vendor_C_AudioBlast_Jan2026.xlsx](Inputs/Vendor_C_AudioBlast_Jan2026.xlsx): weekly podcast report with presentation rows, brand-specific spend columns, combined downloads, and unreliable `Total Spend`.

## Write a Python script

The parsing scripts are vendor-specific, use header-based source schema detection from `scripts/schemas/`, and all write into the same standardized output schema.

| Vendor | Script | Output | Parsing summary |
|--------|--------|--------|-----------------|
| Vendor A | [scripts/vendor_a.py](scripts/vendor_a.py) | [csv/vendor_a.csv](csv/vendor_a.csv) | Reads the `MediaWave_*` sheet, finds the expected header dynamically, keeps daily rows, and standardizes dates, brands, channel fields, spend, and impressions. |
| Vendor B | [scripts/vendor_b.py](scripts/vendor_b.py) | [csv/vendor_b.csv](csv/vendor_b.csv) | Reads only the `StakePoint` sheet, expands weekly `StakePoint` detail into 7 daily rows per week, and spreads aggregate `WagerLine` and `NeonSpin` totals across the derived date range. |
| Vendor C | [scripts/vendor_c.py](scripts/vendor_c.py) | [csv/vendor_c.csv](csv/vendor_c.csv) | Reads the weekly detail table, expands each source row into `StakePoint` and `WagerLine`, allocates downloads by brand spend share, and proportions both spend and impressions across 7 daily rows. |

Validation is available in [scripts/validate_outputs.py](scripts/validate_outputs.py), which reconciles the generated CSV files back to the source Excel totals and date ranges.

## Test

Run the reconciliation checks with:

```bash
python3 scripts/validate_outputs.py
```

The validator compares the generated CSV files with the original Excel workbooks in two layers:

1. Global output checks:
   Every CSV is checked against [scripts/schemas/output_schema.json](scripts/schemas/output_schema.json) for exact header order, valid `YYYY-MM-DD` dates, non-negative numeric spend, integer or blank impressions, allowed brand values, allowed marketing channels, and allowed `Spend_Type` values.
2. Vendor-specific reconciliation:
   Each output is then compared back to its source workbook using the same business rules as the parser.
   Vendor A is checked against source row count, net spend total, numeric impressions total, blank-impression count, and date range.
   Vendor B is checked against weekly `StakePoint` spend and impressions, aggregate `WagerLine` and `NeonSpin` totals, the workbook monthly total, and the derived date range.
   Vendor C is checked against brand-specific spend columns, combined downloads, expanded row count, and the derived weekly date range.
3. Warning-only cases:
   Vendor C does not fail when the raw `Total Spend` column disagrees with `StakePoint Spend + WagerLine Spend`, because the parser intentionally treats the brand-specific spend columns as the source of truth. The validator also warns about note-driven edge cases such as `Cancelled` and `Makeweight`.

At the current repo state, the validator returns:

- Vendor A: `PASS`
- Vendor B: `PASS`
- Vendor C: `PASS with WARN`

## Document the issues

## Vendor A - MediaWave

The file is reasonably structured, but it still contains several data quality issues and a few fields that had to be derived in order to match the required output schema.

### Issues found in the source file

1. `Date` is not stored in a single consistent format.
   The same column contains Excel serial dates, `MM/DD/YYYY` strings, and `DD-Mon-YYYY` strings. This required date normalization before loading.

2. `Brand` is inconsistent.
   The file mixes abbreviations and full names, for example: `SP` and `StakePoint`, `WL` and `WagerLine`, `NS` and `NeonSpin`, `MR` and `MegaReels`. These values had to be standardized to the canonical brand names required by the target schema.

3. `Impressions` is not fully numeric.
   The column contains text placeholders such as `N/A` and `Not Available` instead of integers. These values had to be converted to `NULL` in the output.

4. The worksheet contains a footer row that is not data.
   There is a trailing `TOTAL` row at the bottom of the sheet, which must be excluded from ingestion.

5. The file contains extra source data that does not belong to the target schema.
   The `Clicks` column is present in the workbook, but there is no matching field in the target output schema, so it was ignored in the final CSV.

6. The file contains both gross and net spend.
   Both `Gross Spend (USD)` and `Net Spend (USD)` are provided, so a business rule was required. Based on the specification, `Net Spend (USD)` was used for `Daily_Spend`.

### Hardcoded / derived values needed to produce the target schema

1. `Vendor` had to be set to `MediaWave`.
   There is no dedicated vendor column in the sheet, so the vendor value was derived from the file / vendor context.

2. `Marketing_Channel` had to be set to `CTV`.
   The workbook contains `Placement Type`, but not the standardized channel field required by the target schema. Since the assessment describes MediaWave as a CTV vendor, all rows were assigned `CTV`.

3. `Sub_Channel` had to be derived from `Placement Type`.
   The source does not contain a separate `Sub_Channel` field, so `Placement Type` was mapped into that target column.

4. `Spend_Type` had to be set to `Actual`.
   The file is already at daily grain, so no proportioning logic was needed.

### Assumptions made in the parser

1. The relevant worksheet is the one whose name starts with `MediaWave_`.
   This was done to avoid accidentally ingesting unrelated sheets if more tabs are added later.

2. The header row is identified by matching the expected source schema.
   This avoids hardcoding row numbers and makes the parser more resilient if a vendor inserts extra rows above the table.

3. Invalid spend values should not break the load.
   The parser converts invalid or negative spend values to `0`, although no negative spend values were observed in this file.

4. Invalid impression values should not be loaded as text.
   Non-numeric values are converted to `NULL` rather than preserved as strings.

## Vendor B - StreetLevel

This file is more difficult than Vendor A because it is not a single clean daily table. It mixes a weekly detail table for one brand, aggregated totals for two other brands, and a separate invoice sheet that should not be ingested as campaign data.

### Issues found in the source file

1. The workbook contains multiple content regions, not one machine-friendly table.
   The `StakePoint` sheet contains narrative rows, a weekly detail table, a side table for other brands, and a monthly total row. There is also an `Invoice Summary` sheet that is not campaign performance data.

2. The detail data is weekly, not daily.
   The main table uses `Week Starting`, so the source does not satisfy the target schema requirement for daily granularity. The weekly rows had to be proportioned into calendar days.

3. Only `StakePoint` has row-level detail.
   `WagerLine` and `NeonSpin` are only provided as aggregate spend totals in two cells, without daily dates, markets, venue types, campaigns, or impressions.

4. There is no explicit `Campaign` field in the workbook.
   The source file does not identify which campaign the spend belongs to, so the target schema cannot be populated from source data alone.

5. There is no explicit `Vendor` column in the detail table.
   The vendor name had to be derived from the file / vendor context.

6. The file labeled `Jan2026` includes a week that starts in February.
   The detail table contains `2026-02-03` as a week start, so proportioning that row produces daily dates through `2026-02-09`.

7. `WagerLine` and `NeonSpin` do not have impression data.
   Because only aggregate spend totals are provided for these brands, `Daily_Impressions` cannot be populated for them.

8. The workbook includes non-data rows that must be excluded.
   The monthly total row and the invoice sheet are useful for reconciliation, but they should not be loaded as fact rows into the target schema.

### Hardcoded / derived values needed to produce the target schema

1. `Vendor` had to be set to `StreetLevel OOH`.
   There is no vendor column in the source table, so the value was derived from the workbook context.

2. `Brand` for the weekly detail table had to be inferred as `StakePoint`.
   The detail rows do not repeat the brand name on every row; this is implied by the worksheet context.

3. `Campaign` had to be set to `March Madness Awareness`.
   The source file does not contain a campaign column, so this value had to be assumed in order to satisfy the target schema.

4. `Marketing_Channel` had to be set to `DOOH`.
   The file is described as digital out-of-home, but the standardized marketing channel is not explicitly stored in the row-level detail.

5. `Sub_Channel` had to be derived from `Venue Type` and `Market`.
   The source does not provide a dedicated lowest-level sub-channel field, so the combination `Venue Type - Market` was used to preserve the finest available granularity for `StakePoint`.

6. `Spend_Type` had to be set to `Proportioned`.
   The source is weekly, so both spend and impressions were spread across calendar days.

7. `WagerLine` and `NeonSpin` required a placeholder `Sub_Channel`.
   Since only aggregate brand totals were provided, `Sub_Channel` was set to `Aggregated Total` for these rows.

### Assumptions made in the parser

1. Only the `StakePoint` sheet is used for ingestion.
   The `Invoice Summary` sheet was treated as reference / reconciliation data only.

2. The weekly detail table is identified by matching the expected header schema.
   This avoids hardcoding the table position and makes the parser more resilient if extra rows are added above the data.

3. Weekly `StakePoint` rows are split evenly across 7 days.
   Spend and impressions are proportioned day by day while preserving the original weekly totals exactly.

4. `WagerLine` and `NeonSpin` aggregate spend is spread across all unique daily dates created from the `StakePoint` timeline.
   This was necessary because those brands do not have their own weekly or daily date structure in the source file.

5. `Daily_Impressions` for `WagerLine` and `NeonSpin` is left as `NULL`.
   The workbook does not provide impression totals for these two brands.

6. The monthly total row is used as a QA check, not as an input row.
   The `StakePoint` detailed spend plus the `WagerLine` and `NeonSpin` aggregate totals reconcile to the reported monthly total of `239,097.44`, which is a useful validation step.

## Vendor C - AudioBlast

This is the messiest file of the three. It is a presentation-style weekly report, not a clean flat table, and several business fields are encoded indirectly or inconsistently.

### Issues found in the source file

1. The workbook is not a machine-friendly table.
   It contains report title rows, a prepared-for row, a report date row, merged week section headers, subtotal rows, and a grand total banner row.

2. The data is weekly, not daily.
   The source uses values like `Week of Jan 6`, so daily output rows had to be created by proportioning each weekly record into 7 calendar days.

3. Brand is not stored as a single field.
   Instead, the file has two separate spend columns: `StakePoint Spend` and `WagerLine Spend`. This means the source rows must be expanded into two branded outputs.

4. `Total Spend` is not reliable.
   At least two rows have a mismatch between `StakePoint Spend + WagerLine Spend` and `Total Spend`. Example: `StakePoint Spend = 0.00`, `WagerLine Spend = 2660.62`, but `Total Spend = 0.00`. Because of this, `Total Spend` cannot be treated as the source of truth.

5. `Downloads (est.)` is aggregated across both brands.
   The file does not provide brand-level impression / download counts, so downloads had to be allocated proportionally to brand spend.

6. The file contains note-driven edge cases.
   There are cancelled rows with zero spend but non-zero downloads, and makeweight rows where spend and `Total Spend` do not align cleanly.

7. There is no explicit `Campaign` field.
   The workbook is clearly a podcast campaign report, but there is no row-level campaign column matching the target schema.

8. There is no explicit standardized `Marketing_Channel` field.
   The file is clearly podcast / audio data, but the target marketing channel value had to be derived from workbook context.

### Hardcoded / derived values needed to produce the target schema

1. `Vendor` had to be set to `AudioBlast Media`.
   There is no dedicated vendor column in the detail rows, so the value was derived from the report context.

2. `Campaign` had to be set to `Podcast Campaign`.
   The source does not provide a target-schema-ready campaign field, so a standard campaign value had to be assigned.

3. `Marketing_Channel` had to be set to `Podcast/Audio`.
   The channel is implied by the vendor and report type rather than explicitly stored in a standardized field.

4. `Sub_Channel` had to be derived from `Show / Placement` and `Host`.
   The file does not provide a single sub-channel field, so the combination `Show / Placement - Host` was used as the most granular available placement identifier.

5. `Spend_Type` had to be set to `Proportioned`.
   The source is weekly, so spend and downloads had to be allocated across daily dates.

### Assumptions made in the parser

1. Only rows matching the expected detail header and containing a parseable `Week` value are treated as data rows.
   This excludes presentation rows, merged week banners, subtotals, and the grand total label.

2. `StakePoint Spend` and `WagerLine Spend` are treated as the source of truth for spend.
   Because `Total Spend` is inconsistent in some rows, effective total spend is recalculated as `StakePoint Spend + WagerLine Spend`.

3. `Downloads (est.)` is allocated to each brand in proportion to that brand's share of recalculated spend.
   This produces brand-level `Daily_Impressions` even though the source only provides downloads at the combined row level.

4. If both brand spend columns are zero, downloads are split 50/50.
   This neutral fallback is used for cancelled rows where the file provides downloads but no spend signal for either brand.

5. Makeweight rows are preserved rather than dropped.
   The parser keeps them and uses the brand-specific spend columns even when the raw `Total Spend` column is incorrect.

## Produce three clean CSV output files

- [csv/vendor_a.csv](csv/vendor_a.csv)
- [csv/vendor_b.csv](csv/vendor_b.csv)
- [csv/vendor_c.csv](csv/vendor_c.csv)

## Approach

1. Excel files should be treated as row-based inputs, not assumed to be clean database-style tables.
2. Each vendor file should have its own expected input schema so headers can be identified dynamically rather than by hardcoded row numbers.
3. The normalized outputs should be forced into one shared output schema with explicit field-level transformation rules.
4. Reconciliation checks should be run after parsing to compare output totals, row counts, and date ranges back to the source.
5. The processing pipeline should produce a short QA report so data issues are visible immediately.

## Production recommendations

1. The ingestion should be automated and scheduled.
   In production, this is a good fit for Airflow: ingest files on a regular schedule, run vendor-specific parsers, validate outputs, and promote only successful runs downstream.
2. Every run should produce an operational report.
   A short summary should be sent to Slack, Teams, or email with file names, row counts, validation status, warnings, totals, and any rows or files sent for manual review.
3. Normalized outputs should be checked for anomalies.
   After schema validation, the pipeline should also look for unusual patterns such as missing dates, duplicate rows, sudden spend spikes, zero-impression anomalies, or major deviations from historical brand or channel distributions.
4. Data should land in a quarantine or staging layer first.
   Before loading into the final fact table, each run should write to a temporary review table so failed or suspicious records can be inspected and approved without polluting downstream reporting.

## Challenges

1. In production, access to source files has to be organized first, whether they arrive through shared storage, email ingestion, or another upstream system.
2. Some basic data infrastructure is needed for a scalable workflow:
   - workflow orchestration such as Airflow
   - durable storage for inbound files
   - a temporary or operational database for review and QA if needed
   - access to downstream systems such as a DWH or campaign data stores

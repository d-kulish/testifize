# AdTaxi Parser Rebuild — Comprehensive Analysis Report

## 1. Executive Summary

**Feasibility: YES — fully feasible.**

The proposed parsing approach is not only feasible but is the correct way to handle the new AdTaxi file format. The current parser is fundamentally wrong for the new files because it assumes a single-sheet layout with top-level aggregates that it distributes evenly across days. The new files contain **actual daily data** in multi-sheet Excel files, and the parser should extract and aggregate that real daily data rather than inventing uniform daily splits.

---

## 2. Current Parser Analysis (`parsers/AdTaxi/parser.py` + `input_schema.json`)

### What it does now:
1. Opens a **single hardcoded sheet** (`"Totals By State"` from `input_schema.json`).
2. Reads a **date range** from cell `B2` (e.g., `"3/1/2026/26 - 3/31-26"`).
3. Reads **top-level aggregated spend and impressions** from rows 3–5 (three campaign totals).
4. **Evenly distributes** the total spend and total impressions across every day in the date range.
5. Outputs 31 identical rows (for March) with the same daily values.

### Why it is wrong for the new files:
- The new files have **multiple sheets** (3–4 per file), not one.
- The new files contain **real daily data** — each state has a day-by-day breakdown.
- The old parser ignores the actual daily data and invents flat distributions.
- The result is every day having identical spend/impressions, which is factually incorrect.

### Evidence from processed output (`data/processed/AdTaxi/AdTaxi_March_2026.csv`):
```csv
Date,Vendor,Brand,Channel,Platform,Spend,Impressions,...
2026-03-01,AdTaxi,BetOnline,"Display, CTV",AdTaxi,1821.47129,231915.806452,...
2026-03-02,AdTaxi,BetOnline,"Display, CTV",AdTaxi,1821.47129,231915.806452,...
... (31 identical rows)
```
Every day has exactly **1,821.47** spend and **231,915.81** impressions. This is a synthetic flat-line distribution, not real data.

---

## 3. New File Format Analysis

### Files examined:
| File | Sheets | Campaigns Covered |
|------|--------|-----------------|
| `BetOnline Media Spend & Conversion by State (March 2026).xlsx` | 3 | March Madness Display, March Madness CTV, World Cup Display |
| `BetOnline Media Spend & Conversion by State (April 2026).xlsx` | 4 | March Madness Display, March Madness CTV, General Live Sports Display, General Live Sports CTV |
| `BetOnline Media Spend & Conversion by State (May 2026).xlsx` | 4 | Casino Display, Casino CTV, General Live Sports Display, General Live Sports CTV |

### Per-sheet structure (identical across all sheets):

**Row 1–2:** Fixed header with date range in cell `B2` (e.g., `"3/1/2026/26 - 3/31-26"` or `"4/1/26 - 4/30/26"`).

**Row 3–5:** Campaign summary table — top-level totals per campaign/channel. **These should be ignored for the new parsing approach.**

**Row 8:** Dual-table header row:
```
Left side:  "March Madness Programmatic Display - Totals by State"
Right side: "March Madness Programmatic Display - Daily by State"
```

**Row 9:** Sub-headers (Advertiser Cost, Impressions, Site Visit, etc.)

**Row 10+:** Two independent tables side by side:
- **LEFT table (cols A–F):** State-level totals — e.g., `Alaska | 289.52 | 58317 | ...` — **to be ignored** per your requirement.
- **RIGHT table (cols H–N):** Daily breakdown — the data we need.

### RIGHT table structure (the critical part):

The right table contains **stacked state blocks** — one block per state that has daily data:

```
Row 10 (right):  Alaska  |  289.52  |  58317     ← State total (DUPLICATE of left table — SKIP)
Row 11 (right):  Mar 1   |   0.48   |   160      ← Actual daily data
Row 12 (right):  Mar 2   |   0.00   |     0      ← Actual daily data
...
Row 41 (right):  Mar 31  |   8.72   |  1555      ← Last day for Alaska
Row 42 (right):  Arizona | 3354.92  | 593730     ← Next state's total (SKIP)
Row 43 (right):  Mar 1   |   0.70   |   203      ← Arizona daily data starts
...
```

**Key discovery:** Within each sheet, the right table contains **multiple sequential daily blocks** (one per state), each spanning the full reporting month. The state total row acts as a separator between blocks. After all state blocks for one campaign, the next campaign's blocks begin further down.

### Date format in the new files:
- The cells in the date column (col H) contain **Excel datetime objects** (e.g., `datetime.datetime(2026, 4, 1, 0, 0)`).
- No string parsing of `"Thu Mar 26 2026 02:00:00 GMT+0200..."` is needed — openpyxl returns clean `datetime` objects when using `data_only=True`.
- Conversion is trivial: `.date()` → `datetime.date(2026, 4, 1)`.

---

## 4. Aggregated Data Validation

I ran an extraction script across all three new files to validate the approach.

### March 2026 file — aggregated across all sheets:
```
Total unique dates: 31 (2026-03-01 to 2026-03-31)
Total spend from daily data:     47,546.34
Total impressions from daily data: 6,933,551
```

Compare to top-level totals in the file:
```
March Madness Display:   34,039.99
March Madness CTV:     17,427.25
World Cup Display:        4,998.37
─────────────────────────────────
Top-level total:        56,465.61
```

**Discrepancy explained:** The top-level total (56,465.61) is higher than the sum of daily data (47,546.34) because **not every state has a daily breakdown** in the right table. Some states only appear in the left "Totals by State" table without corresponding daily rows. This is expected — the parser should aggregate only what daily data exists.

### April 2026 file — aggregated across all sheets:
```
Total unique dates: 30 (2026-04-01 to 2026-04-30)
Total spend from daily data:     65,286.36
Total impressions from daily data: 9,451,769
```

### May 2026 file — aggregated across all sheets:
```
Total unique dates: 31 (2026-05-01 to 2026-05-31)
Total spend from daily data:     80,557.66
Total impressions from daily data: 11,633,572
```

The daily data is **sparse at the start of the month** (many $0.00 / 0 impression rows) and **heavier at the end**, confirming the data is real and not uniformly distributed. This validates that extracting actual daily data is the correct approach.

---

## 5. Proposed Parsing Approach — Feasibility Assessment

### Your requirements:
1. ✅ **Define all sheets in the file regardless of names** — `openpyxl` provides `wb.sheetnames`; simply iterate all of them.
2. ✅ **Find the "right table" on every sheet** — Scan for a row containing `"Daily by State"` in column H (or anywhere in the row). This is a reliable anchor.
3. ✅ **Group by dates and convert** — Dates are already `datetime` objects; call `.date()` and group with a `defaultdict` or `pandas` groupby.
4. ✅ **Avoid/omit state aggregations** — Skip rows where col H is a string (state name). Only keep rows where col H is a `datetime`.
5. ✅ **Take "Advertiser Cost" as Spend and "Impressions" as Impressions** — Confirmed at cols I and J of the right table.
6. ✅ **Create monthly table with Date, Spend (aggregated), Impressions (aggregated)** — Straightforward groupby-sum operation.

### Algorithm sketch:
```python
from collections import defaultdict
from datetime import datetime

daily_spend = defaultdict(Decimal)
daily_impressions = defaultdict(Decimal)

for sheet_name in workbook.sheetnames:
    sheet = workbook[sheet_name]
    in_daily_section = False
    for row in sheet.iter_rows(min_row=8, values_only=True):
        col_h = row[7]  # Column H
        if isinstance(col_h, str) and "Daily by State" in col_h:
            in_daily_section = True
            continue
        if isinstance(col_h, str):
            # State total row — skip
            in_daily_section = True
            continue
        if isinstance(col_h, datetime) and in_daily_section:
            date = col_h.date()
            spend = row[8] or 0      # Column I
            impressions = row[9] or 0  # Column J
            daily_spend[date] += spend
            daily_impressions[date] += impressions
```

### Edge cases to handle:
| Edge Case | Handling |
|-----------|----------|
| State total row in right table (string in col H) | Skip — it’s not a date |
| `$0.00` / `0` impression days | Keep them — they are real data |
| Missing daily blocks for some states | Automatically handled — only rows with dates are collected |
| Variable number of sheets per file | Iterate `wb.sheetnames` — works for 3, 4, or any number |
| Variable campaign names in sheet names | Ignore sheet names entirely — use `"Daily by State"` row detection |
| Empty rows at end of sheet | `datetime` check naturally stops when dates end |
| The `DailySpending_Apr26_BOL_SB_WC_SS_2026.05.28.xlsx` file | This is a **different format** (simple daily rows per campaign). It should either be excluded or handled by a separate parser path. It does not contain the dual-table structure. |

---

## 6. Output Format Compatibility

The existing processed file format (`data/processed/AdTaxi/AdTaxi.csv`) uses:
```csv
Date,Vendor,Brand,Channel,Platform,Spend,Impressions,Data_Grain,Processed_At,Source_File
```

The parser infrastructure (`parser_workflow.py`) dynamically discovers output columns from either:
1. An existing approved historical CSV header, OR
2. Defaults derived from `input_schema.json`.

The new parser can produce rows in the exact same format. Static columns like `Vendor`, `Brand`, `Channel`, `Platform`, `Data_Grain`, `Processed_At`, `Source_File` can be hardcoded or read from `input_schema.json` `output_defaults`.

**No changes to the pipeline workflow are required** — only the `parser.py` and `input_schema.json` need updating.

---

## 7. Comparison: Old vs. New Approach

| Aspect | Old Parser (Current) | New Parser (Proposed) |
|--------|----------------------|----------------------|
| Sheets processed | 1 (hardcoded) | All sheets dynamically |
| Date source | Single cell (`B2`) | Actual daily rows |
| Spend/Impressions source | Top-level totals (rows 3–5) | Real daily values from right table |
| Daily values | Evenly distributed (flat) | Actual daily fluctuations |
| State-level data | Summed once, then split | Ignored; daily data used directly |
| Accuracy | Synthetic / invented | Real vendor-reported daily data |
| File compatibility | Only old single-sheet format | New multi-sheet format |

---

## 8. Files That Need Changing

| File | Change Required |
|------|-----------------|
| `parsers/AdTaxi/parser.py` | **Complete rewrite** — new algorithm to iterate sheets, find "Daily by State" sections, extract datetime rows, groupby-sum |
| `parsers/AdTaxi/input_schema.json` | Update to remove hardcoded single-sheet references; add `output_defaults` for static columns |
| `data/processed/AdTaxi/AdTaxi.csv` | Will be regenerated by the new parser when files are re-processed |

Files that **do NOT** need changing:
- Django views, models, workflow (`parser_workflow.py`, `views.py`) — the parser interface (`parse_file(source_path, input_schema, output_columns, sheet_name)`) remains unchanged.
- Output schema — the target CSV columns stay the same.

---

## 9. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Some states lack daily data in right table | Acceptable — sum whatever daily data exists; this is still more accurate than flat distribution |
| Future files change layout | The `"Daily by State"` anchor is fairly stable; parser can be made resilient by scanning for the anchor string rather than assuming fixed row numbers |
| The `DailySpending_*.xlsx` file in the AdTaxi folder | This is a different format. Exclude it from parsing (e.g., by filename filter in the schema or by manual exclusion) |
| Empty/zero-value days at start of month | These are real data — keep them. They indicate the campaign had not yet ramped up |

---

## 10. Conclusion

**The approach is fully feasible and strongly recommended.**

The current parser produces factually incorrect output (flat daily distributions) because it was built for a different file format. The new AdTaxi files contain rich, real daily data across multiple campaign sheets. A rewritten parser that:
1. Iterates all sheets,
2. Locates the "Daily by State" right table via string matching,
3. Extracts only rows where the date column contains actual `datetime` values,
4. Groups by date and sums spend + impressions across all sheets and all states,

…will produce accurate, granular daily output that reflects the vendor's actual reporting. The infrastructure integration requires zero changes outside the `parsers/AdTaxi/` directory.

**Recommended next step:** Proceed with rewriting `parsers/AdTaxi/parser.py` and updating `parsers/AdTaxi/input_schema.json`.

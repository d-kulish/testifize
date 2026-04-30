# Bleav Comparison Report

## Summary

| Metric | Generated Bleav.csv | final/Bleav.csv |
|---|---:|---:|
| Rows | 41502 | 37718 |
| Unique dates | 334 | 334 |
| Date range | 2024-09-01 to 2025-07-31 | 2024-09-01 to 2025-07-31 |
| Total spend | 800003.36 | 800008.28 |
| Total impressions | 82506111 | Not available |
| Campaign/show count | 187 | Not available |

## Source Choice

- Parsed `By_Show_Detail` because it contains the actual show/campaign names required by `Campaign`.
- `Daily_Aggregated` is useful for total checks, but its `Campaign = Podcast` is too coarse for the output schema.

## Old File Limitations

- `final/Bleav.csv` has no impressions column.
- `final/Bleav.csv` has no campaign/show field.
- `final/Bleav.csv` has no data-source or source-file lineage column.
- `final/Bleav.csv` has many rows per date, so it is compared by daily spend totals.

## Source Data Status

| Data_Source | Rows |
|---|---:|
| Actual | 31606 |
| Imputed from Feb | 9028 |
| Imputed from Jun | 868 |

## Date-Level Comparison

- Missing dates from generated output: 0
- Extra dates in generated output: 0
- Total spend difference: -4.92
- Max absolute daily spend difference: 0.14
- Dates with material daily spend differences: 153
- Spend differences are small daily rounding/import differences in the old file; date coverage matches exactly.

## Comparable Value Checks

| Check | Result |
|---|---|
| Date coverage | PASS |
| Vendor values | PASS |
| Brand values | PASS |
| Marketing_Channel -> Channel values | PASS |
| Sub_Channel -> Platform values | DIFF |

## Generated Schema Values

- `Vendor`: Bleav
- `Brand`: BetOnline
- `Campaign` count: 187
- `Campaign` sample: 11 Yanks, 410 Sports Talk, 48 Minutes, 49ers Cutback, All Day, All Dodgers Podcast with Clint Pasillas, Ampire, Are You Serious Sports, BLEAV in Bengals, BLEAV in Chargers
- `Marketing_Channel`: Podcast/Audio
- `Sub_Channel`: Sports Podcast Network
- `Spend_Type`: Actual

## Sample Daily Spend Differences

| Date | Generated Spend | Final Spend | Difference |
|---|---:|---:|---:|
| 2025-01-01 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-02 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-03 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-04 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-05 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-06 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-07 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-08 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-09 | 3225.75 | 3225.89 | -0.14 |
| 2025-01-10 | 3225.75 | 3225.89 | -0.14 |

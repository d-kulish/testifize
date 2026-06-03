# Jeff / Cool Prevails Vendor File Analysis

> **Date:** 2026-06-03  
> **Analyst:** Claude Code  
> **Scope:** Excel files received from vendor "Jeff" (identified as Cool Prevails / 760 Media) in `data/inbox/home/jeff/` for the period April–May 2026.  
> **Goal:** Understand file logic, detect coverage gaps, and propose parsing and standardization strategies.

---

## 1. Vendor Identity

| Attribute | Value |
|-----------|-------|
| **Pipeline Vendor Name** | `Cool Prevails` |
| **Agency** | 760 Media |
| **Internal Product Code** | `AX` (appears in most filenames) |
| **Contact** | Jeff Donnelly (from insertion order file) |
| **Brands Managed** | `BetOnline` (BOL / BO) and `Wild Casino` (WC / Wild) |

All files originate from the same agency but use inconsistent naming, sheet structures, and granularity.

---

## 2. File Families

The vendor sends three distinct structural families. Each family reports on different channels and uses different Excel layouts.

### 2.1 AX Channel Files — Programmatic / DSP

**Content:** Daily spend and impressions by channel (CTV, Display).  
**Source platform:** Likely The Trade Desk or similar DSP.  
**Key sheets:**
- Early files: `Sheet2`
- Mid-period files: `BO Channel Data`
- Latest files: `By Channel`

**Structure per row:**
```
Channel | Day | Spend | Impressions | CPM | Clicks | CTR | CPC | Create Accounts | CPA
```

**Important:** These files also contain a `Sheet1` named `Sign Ups` (or similar) which is a **conversion-level log** (individual registration events with timestamps, metros, devices). That sheet is **not** what we need for daily spend/impressions reporting.

**Files in this family:**

| Filename | Brand | Sheet Used | Date Range Inside | Days |
|----------|-------|------------|-------------------|------|
| `BO AX Regs 427-53.xlsx` | BetOnline | `Sheet2` | Apr 27 – May 3 | 7 |
| `WC AX Regs 427-53.xlsx` | Wild Casino | `Sheet2` | Apr 27 – May 3 | 7 |
| `Bet Online AX 54-510.xlsx` | BetOnline | `BO Channel Data` | May 4 – May 10 | 7 |
| `BOL AX wo 511-517.xlsx` | BetOnline | `By Channel` | May 11 – May 17 | 7 |
| `WC AX wo 511-517.xlsx` | Wild Casino | `By Channel` | May 11 – May 17 | 7 |
| `BetOnline ax 511-517.xlsx` | BetOnline | `By Channel` | May 11 – May 17 | 7 |
| `WC ax 511-517.xlsx` | Wild Casino | `By Channel` | May 11 – May 17 | 7 |

**Duplicate / re-send notes:**
- `BetOnline ax 511-517.xlsx` is an exact duplicate of `BOL AX wo 511-517.xlsx`.
- `WC ax 511-517.xlsx` is an exact duplicate of `WC AX wo 511-517.xlsx`.
- The vendor appears to have re-sent the same week with slightly different filenames (lowercase "ax" vs. "AX wo").

### 2.2 Meta / DA Files — Facebook / Meta Ads Manager Exports

**Content:** Daily Meta ad performance (spend, impressions, leads/registrations, etc.).  
**Source platform:** Meta Ads Manager.  
**Key sheet:** `Raw Data Report`

**Header evolution — 4 variants observed:**

| Variant | Header Columns | Period | Brand |
|---------|----------------|--------|-------|
| V1 | `Account name \| Day \| Reach \| Impressions \| Amount spent (USD) \| ...` | Apr 27 – May 3 | Wild Casino |
| V2 | `Campaign name \| Ad set name \| Day \| Impressions \| Amount spent (USD) \| ...` | Apr 27 – Apr 30 | BetOnline |
| V3 | `Day \| Reach \| Impressions \| Amount spent (USD) \| ...` | May 11+ | Wild Casino |
| V4 | `Day \| Reach \| Impressions \| Results \| Amount spent (USD) \| ...` | May 11+ | BetOnline |

**Files in this family:**

| Filename | Brand | Variant | Date Range Inside | Days | Issue |
|----------|-------|---------|-------------------|------|-------|
| `BOL DA weekly April 20-26.xlsx` | BetOnline | V2-ish | Apr 20 – Apr 26 | 7 | Has `Starts`/`Ends` columns |
| `Wild-weekly DA April 20-26.xlsx` | Wild Casino | V1 | Apr 20 – Apr 26 | 7 | Complete |
| `Wild DA-weekly April 13-19.xlsx` | Wild Casino | V1 | Apr 13 – Apr 19 | 7 | Complete |
| `Wild-Meta DA April27-May 3.xlsx` | Wild Casino | V1 | Apr 27 – May 3 | 7 | Complete |
| `BOL DA Meta 427 53 Untitled-report (2).xlsx` | BetOnline | V2 | **Apr 27 – Apr 30** | 4 | **Missing May 1–3** |
| `Wild-weekly DA May 4-10.xlsx` | Wild Casino | V1 | **Apr 27 – May 3** | 7 | **Wrong dates inside** |
| `BOL DA May 4-10.xlsx` | BetOnline | V2-ish | **May 4 – May 8** | 5 | **Missing May 9–10** |
| `Wild-weekly DA May 11-17.xlsx` | Wild Casino | V3 | May 11 – May 17 | 7 | Complete |
| `BOL DA May 11-17.xlsx` | BetOnline | V4 | May 11 – May 17 | 7 | Complete |
| `Wild-weekly da May 25-31.xlsx` | Wild Casino | V3 | May 25 – May 31 | 7 | Complete |

### 2.3 Combined File — One-Off Multi-Sheet Workbook

**Content:** A single file attempting to cover both brands and both channels.  
**Filename:** `BOL _ WILD da report May 18-24.xlsx`  
**Sheets:**

| Sheet | Brand | Channel | Headers | Date Range Inside | Days | Issue |
|-------|-------|---------|---------|-------------------|------|-------|
| `WC - DSP` | Wild Casino | DSP | `Date \| Clicks \| CPC \| Impressions \| Spend \| CPM` | May 18 – May 21 | 4 | **Missing May 22–24** |
| `BOL - DSP` | BetOnline | DSP | Same as above | May 18 – May 20 | 3 | **Missing May 21–24** |
| `Wild - Meta` | Wild Casino | Meta | `Date \| Spend \| Leads \| CPL \| CPM \| CPC \| Purchases \| CPA` | May 18 – May 24 | 7 | Complete; **no Impressions column** |
| `BetOnline - Meta` | BetOnline | Meta | `Date \| Campaign name \| Leads \| Reach \| Cost per lead \| Amount spent (USD) \| Impressions \| CPM \| CPC` | May 18 – May 24 | 7 | Complete |
| `WC - TP` | Wild Casino | TP | `Date \| Installs` | May 18 – May 24 | 7 | No spend/impressions |
| `BOL - TP` | BetOnline | TP | `Date \| Installs` | May 18 – May 24 | 7 | No spend/impressions |
| `Master Spend` | Both | Summary | `Channel \| WC Spend \| BOL Spend` | — | — | Skip (summary) |

**Notes:**
- The `TP` (Traffic Partner / Tracking Partner) sheets contain **only install counts**. No media spend or impressions. These should be **skipped** for the media pipeline.
- The `Wild - Meta` sheet is missing an `Impressions` column. Impressions can be **calculated** from `Spend / (CPM / 1000)`.
- This combined format was **not agreed upon** — it appears to be an ad-hoc vendor decision.

### 2.4 Non-Data File

| Filename | Type | Action |
|----------|------|--------|
| `Wild Casino_ AX_WCASAO Conversion Extension_ 514-615xlsx.xlsx` | Insertion Order / Campaign Plan | **Ignore** for parsing; can be catalogued as `reference` |

This file contains flight dates, budgets, QA checklists, and naming conventions. It has no daily spend or impression data.

---

## 3. Data Coverage & Gaps

### 3.1 Daily Coverage Matrix (Apr 20 – May 31)

For each day and each brand+channel combination, we mark whether data exists.

| Week | BetOnline DSP | BetOnline Meta | Wild Casino DSP | Wild Casino Meta |
|------|---------------|----------------|-----------------|------------------|
| **Apr 20–26** | ❌ Missing | ✅ `BOL DA weekly Apr 20-26` | ❌ Missing | ✅ `Wild-weekly DA Apr 20-26` |
| **Apr 27 – May 3** | ✅ `BO AX Regs 427-53` | ⚠️ Partial (`BOL DA Meta` has only Apr 27–30) | ✅ `WC AX Regs 427-53` | ✅ `Wild-Meta DA Apr27-May3` |
| **May 4–10** | ✅ `Bet Online AX 54-510` | ⚠️ Partial (`BOL DA May 4-10` has only May 4–8) | ❌ Missing | ❌ `Wild-weekly DA May 4-10` has wrong dates inside (Apr 27–May 3) |
| **May 11–17** | ✅ `BOL AX wo 511-517` | ✅ `BOL DA May 11-17` | ✅ `WC AX wo 511-517` | ✅ `Wild-weekly DA May 11-17` |
| **May 18–24** | ⚠️ Partial (combined `BOL - DSP` has only May 18–20) | ✅ Combined `BetOnline - Meta` | ⚠️ Partial (combined `WC - DSP` has only May 18–21) | ✅ Combined `Wild - Meta` |
| **May 25–31** | ❌ Missing | ❌ Missing | ❌ Missing | ✅ `Wild-weekly da May 25-31` |

### 3.2 Consolidated Gap List

| Brand | Channel | Missing Dates | Days | File to Request From Vendor |
|-------|---------|---------------|------|----------------------------|
| BetOnline | DSP/AX | Apr 20–26 | 7 | `BO AX Regs 420-426` is missing `Sheet2` / daily aggregates |
| BetOnline | DSP/AX | May 21–31 | 11 | No file sent |
| BetOnline | Meta | May 1–3 | 3 | `BOL DA Meta 427 53` is incomplete |
| BetOnline | Meta | May 9–10 | 2 | `BOL DA May 4-10` is incomplete |
| BetOnline | Meta | May 25–31 | 7 | No file sent |
| Wild Casino | DSP/AX | Apr 20–26 | 7 | `WC AX Regs 420-426` is missing `Sheet2` / daily aggregates |
| Wild Casino | DSP/AX | May 4–10 | 7 | No file sent |
| Wild Casino | DSP/AX | May 22–31 | 10 | No file sent (combined `WC - DSP` is incomplete) |
| Wild Casino | Meta | May 4–10 | 7 | `Wild-weekly DA May 4-10` has wrong dates inside |

### 3.3 Specific File Issues

| Issue | File(s) | Details |
|-------|---------|---------|
| Missing daily aggregates | `BO AX Regs 420-426.xlsx`, `WC AX Regs 420-426.xlsx` | Only `Sheet1` (conversion log) exists. No `Sheet2` with daily spend/impressions by channel. |
| Incomplete Meta report | `BOL DA Meta 427 53 Untitled-report (2).xlsx` | Filename says Apr 27 – May 3, but data stops at Apr 30. |
| Wrong dates inside | `Wild-weekly DA May 4-10.xlsx` | Filename says May 4–10, but data inside is Apr 27 – May 3. |
| Incomplete Meta report | `BOL DA May 4-10.xlsx` | Filename says May 4–10, but data stops at May 8. |
| Incomplete DSP data in combined | `BOL _ WILD da report May 18-24.xlsx` | `BOL - DSP` sheet stops at May 20; `WC - DSP` sheet stops at May 21. |
| Exact duplicates | `BetOnline ax 511-517.xlsx` vs `BOL AX wo 511-517.xlsx` | Same data, same week, different filenames. |
| Exact duplicates | `WC ax 511-517.xlsx` vs `WC AX wo 511-517.xlsx` | Same data, same week, different filenames. |

---

## 4. Parsing Strategy

### 4.1 Target Output Schema

Based on the existing Loop parser output, every parsed row should map to:

```
Date, Vendor, Brand, Channel, Platform, Spend, Impressions, Data_Grain, Processed_At, Source_File
```

For Cool Prevails:
- **Vendor:** `Cool Prevails`
- **Channel:** `Programmatic` (for DSP/AX) or `Social` (for Meta)
- **Platform:** `DSP` (for AX) or `Meta` (for DA)
- **Data_Grain:** `daily`

### 4.2 Parser Families Required

Because the vendor sends structurally different files, we need **three parser schemas** (or one multi-branch parser):

#### A. `CoolPrevails_AX` — Programmatic Daily Spend

**Sheet selection priority:**
1. `By Channel` (newest files)
2. `BO Channel Data` (mid-period files)
3. `Sheet2` (oldest files)
4. Skip `Sheet1` / `Sign Ups` (conversion logs)

**Header detection:** Look for `Channel`, `Day`, `Spend`, `Impressions`.

**Aggregation rule:** Since you want one row per day, sum all channels (CTV + Display) per day:
```
Spend = SUM(Spend per channel for that day)
Impressions = SUM(Impressions per channel for that day)
```

**Skip rules:**
- Skip rows where `Day` is blank/None.
- Skip subtotal/total rows.

#### B. `CoolPrevails_Meta` — Meta Daily Spend

**Sheet:** Always `Raw Data Report`.

**Header variant detection:** Inspect the header row and map columns dynamically:

| Variant | Date Column | Spend Column | Impressions Column | Aggregation Needed? |
|---------|-------------|--------------|--------------------|---------------------|
| V1 | `Day` (index varies) | `Amount spent (USD)` | `Impressions` | No (already daily) |
| V2 | `Day` | `Amount spent (USD)` | `Impressions` | **Yes** — group by `Day`, sum `Spend` and `Impressions` across campaigns/ad sets |
| V3 | `Day` | `Amount spent (USD)` | `Impressions` | No (already daily) |
| V4 | `Day` | `Amount spent (USD)` | `Impressions` | No (already daily) |

**Skip rules:**
- Skip Row 2 if it is a summary/total row (blank `Day`, populated `Impressions`/`Spend`).
- Skip rows where `Day` is blank/None or not a valid date.
- Skip trailing blank rows.

#### C. `CoolPrevails_Combined` — Multi-Sheet Workbook

**Approach:** Iterate over known sheets, branch by sheet name.

| Sheet | Parser Branch | Notes |
|-------|---------------|-------|
| `WC - DSP` | Same as AX parser | Map `Date`→Date, `Spend`→Spend, `Impressions`→Impressions |
| `BOL - DSP` | Same as AX parser | Same mapping |
| `Wild - Meta` | Meta variant | `Spend` is `Spend`; **calculate Impressions = Spend / (CPM / 1000)** |
| `BetOnline - Meta` | Meta variant | Map `Date`→Date, `Amount spent (USD)`→Spend, `Impressions`→Impressions; group by day if needed |
| `WC - TP` | **Skip** | No media data |
| `BOL - TP` | **Skip** | No media data |
| `Master Spend` | **Skip** | Summary only |

---

## 5. Recommended Standardized Reporting Template

Since the vendor files are chaotic, we recommend sending them a strict template. Ask for **two files per brand per week** (or one combined file with exact structure).

### Option A: Two Files Per Brand Per Week

#### File 1: Programmatic / DSP

**Filename:** `{Brand}_DSP_{YYYY-MM-DD}_to_{YYYY-MM-DD}.xlsx`

**Sheet:** Single sheet, any name (we will detect the first data sheet).

**Header (Row 1):**

| Date | Channel | Spend (USD) | Impressions |
|------|---------|-------------|-------------|
| 2026-05-01 | CTV | 280.59 | 4775 |
| 2026-05-01 | Display | 121.45 | 25332 |
| 2026-05-02 | CTV | 274.48 | 4673 |
| ... | ... | ... | ... |

**Rules:**
- One row per day per channel.
- `Date` must be in `YYYY-MM-DD` format.
- `Channel` must be `CTV` or `Display`.
- Do not include totals, subtotals, or blank rows inside the data block.

#### File 2: Meta / Facebook

**Filename:** `{Brand}_Meta_{YYYY-MM-DD}_to_{YYYY-MM-DD}.xlsx`

**Sheet:** Single sheet.

**Header (Row 1):**

| Date | Spend (USD) | Impressions |
|------|-------------|-------------|
| 2026-05-01 | 255.63 | 2687 |
| 2026-05-02 | 247.20 | 2526 |
| ... | ... | ... |

**Rules:**
- One row per day (aggregated across all campaigns and ad sets).
- `Date` must be in `YYYY-MM-DD` format.
- Do not include `Campaign name`, `Ad set name`, `Reach`, `CPM`, `CTR`, or any other columns.
- Do not include totals or blank rows.

### Option B: One Combined File

**Filename:** `CoolPrevails_{Brand}_Week_{YYYY-MM-DD}_to_{YYYY-MM-DD}.xlsx`

**Required sheets:**

| Sheet Name | Content | Columns |
|------------|---------|---------|
| `BetOnline_DSP` | Daily by channel | `Date \| Channel \| Spend \| Impressions` |
| `BetOnline_Meta` | Daily aggregated | `Date \| Spend \| Impressions` |
| `WildCasino_DSP` | Daily by channel | `Date \| Channel \| Spend \| Impressions` |
| `WildCasino_Meta` | Daily aggregated | `Date \| Spend \| Impressions` |

**Critical rule:** The date range in the filename must match the actual data inside the file.

---

## 6. Vendor Communication — Issues to Report

Below is a concise list of findings to forward to Cool Prevails / Jeff Donnelly.

> **Cool Prevails — Weekly Reporting Issues (Apr 20 – May 31, 2026)**
>
> We are missing daily media data for the following periods. Please re-send the corrected files.
>
> **1. Missing DSP / Programmatic Daily Aggregates**
> - BetOnline: Apr 20–26, May 21–31
> - Wild Casino: Apr 20–26, May 4–10, May 22–31
>
> **2. Missing / Incomplete Meta / Facebook Reports**
> - BetOnline Meta: May 1–3, May 9–10, May 25–31
> - Wild Casino Meta: May 4–10, May 25–31
>
> **3. Specific File Errors**
> - `BO AX Regs 420-426.xlsx` and `WC AX Regs 420-426.xlsx` — these files only contain conversion logs (`Sheet1`). Please re-send with the daily spend/impressions by channel (`Sheet2`).
> - `BOL DA Meta 427 53 Untitled-report (2).xlsx` — says Apr 27 – May 3 but data ends at Apr 30. Missing May 1–3.
> - `Wild-weekly DA May 4-10.xlsx` — says May 4–10 but contains Apr 27 – May 3 data. Wrong dates inside.
> - `BOL DA May 4-10.xlsx` — says May 4–10 but data ends at May 8. Missing May 9–10.
> - `BOL _ WILD da report May 18-24.xlsx` — `BOL - DSP` sheet missing May 21–24; `WC - DSP` sheet missing May 22–24.
>
> **4. Duplicate Files**
> - `BetOnline ax 511-517.xlsx` = duplicate of `BOL AX wo 511-517.xlsx`
> - `WC ax 511-517.xlsx` = duplicate of `WC AX wo 511-517.xlsx`
>
> **5. Format Standardization Request**
> Please see the attached template. Going forward, send us either:
> - Two files per brand per week (`{Brand}_DSP_...` and `{Brand}_Meta_...`), OR
> - One combined file with the exact sheet names and columns specified in the template.
> The date range in the filename must match the data inside.

---

## 7. Next Steps & Action Items

| # | Action | Owner | Priority |
|---|--------|-------|----------|
| 1 | **Create parser schemas** for `CoolPrevails_AX`, `CoolPrevails_Meta`, and `CoolPrevails_Combined` | Dev | High |
| 2 | **Register `Cool Prevails`** as a Vendor in the Django control panel | Dev | High |
| 3 | **Parse all existing files** into consolidated CSVs, marking gap days explicitly | Dev | High |
| 4 | **Send vendor communication** (template + gap list) to Jeff Donnelly | User (PM) | High |
| 5 | **Catalogue and classify all files** in the asset catalogue (`approved`, `superseded`, `ignored`) | Dev | Medium |
| 6 | **Handle duplicates** — mark `BetOnline ax 511-517` and `WC ax 511-517` as `superseded` or `duplicate` | Dev | Medium |
| 7 | **Decide on TP data** — if install tracking becomes relevant later, create a separate parser branch | Future | Low |
| 8 | **Monitor vendor compliance** — once template is sent, check incoming files against the new standard | Ongoing | Medium |

---

## 8. Appendix: File Inventory

All files analyzed in `data/inbox/home/jeff/` for this review:

### Included in analysis

| Filename | Family | Brand | Date Range | Status |
|----------|--------|-------|------------|--------|
| `BO AX Regs 420-426.xlsx` | AX | BetOnline | — | Missing daily aggregates |
| `BO AX Regs 427-53.xlsx` | AX | BetOnline | Apr 27 – May 3 | ✅ OK |
| `WC AX Regs 420-426.xlsx` | AX | Wild Casino | — | Missing daily aggregates |
| `WC AX Regs 427-53.xlsx` | AX | Wild Casino | Apr 27 – May 3 | ✅ OK |
| `Bet Online AX 54-510.xlsx` | AX | BetOnline | May 4 – May 10 | ✅ OK |
| `BOL AX wo 511-517.xlsx` | AX | BetOnline | May 11 – May 17 | ✅ OK |
| `WC AX wo 511-517.xlsx` | AX | Wild Casino | May 11 – May 17 | ✅ OK |
| `BetOnline ax 511-517.xlsx` | AX | BetOnline | May 11 – May 17 | Duplicate |
| `WC ax 511-517.xlsx` | AX | Wild Casino | May 11 – May 17 | Duplicate |
| `BOL DA weekly April 20-26.xlsx` | Meta | BetOnline | Apr 20 – Apr 26 | ✅ OK |
| `Wild-weekly DA April 20-26.xlsx` | Meta | Wild Casino | Apr 20 – Apr 26 | ✅ OK |
| `Wild DA-weekly April 13-19.xlsx` | Meta | Wild Casino | Apr 13 – Apr 19 | ✅ OK |
| `Wild-Meta DA April27-May 3.xlsx` | Meta | Wild Casino | Apr 27 – May 3 | ✅ OK |
| `BOL DA Meta 427 53 Untitled-report (2).xlsx` | Meta | BetOnline | Apr 27 – Apr 30 | Incomplete |
| `Wild-weekly DA May 4-10.xlsx` | Meta | Wild Casino | Apr 27 – May 3 (wrong) | Wrong dates |
| `BOL DA May 4-10.xlsx` | Meta | BetOnline | May 4 – May 8 | Incomplete |
| `Wild-weekly DA May 11-17.xlsx` | Meta | Wild Casino | May 11 – May 17 | ✅ OK |
| `BOL DA May 11-17.xlsx` | Meta | BetOnline | May 11 – May 17 | ✅ OK |
| `BOL _ WILD da report May 18-24.xlsx` | Combined | Both | Mixed | Partial gaps |
| `Wild-weekly da May 25-31.xlsx` | Meta | Wild Casino | May 25 – May 31 | ✅ OK |

### Excluded from analysis (not media spend data)

| Filename | Reason |
|----------|--------|
| `Wild Casino_ AX_WCASAO Conversion Extension_ 514-615xlsx.xlsx` | Insertion order / planning document |
| `DSP2Meta Wild Q4 2025 Export.xlsx` | Historical Q4 2025 export |
| `DSP2 Meta Wild Historical Export 7_25 - 9_25.xlsx` | Historical Jul–Sep 2025 export |
| `Meta (No DSP) Wild January Report.xlsx` | January 2026 report |
| `Meta Wild Q1 2026..xlsx` | Q1 2026 report |
| `Meta Wild Q4 2025..xlsx` | Q4 2025 report |
| `Meta Wild Weekly report 1 February 2026.xlsx` | Feb 2026 report |
| `Meta Wild-Feb-9-2026-to-Feb-15-2026.xlsx` | Feb 2026 report |
| `Wild-16-Feb-22-Feb..xlsx` | Feb 2026 report |
| Various `.csv` files (`DSP1 WC 112-119.csv`, etc.) | DSP1 historical CSVs |
| Various conversion detail `.csv` files | Conversion-level logs |

---

*Document generated by Claude Code on 2026-06-03. If new files arrive or vendor format changes, update this doc and re-run gap analysis.*

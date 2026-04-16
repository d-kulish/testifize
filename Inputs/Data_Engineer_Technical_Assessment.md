# Data Engineer — Technical Assessment

## Context

You are joining a marketing measurement team for a major US online entertainment operator. The company spends approximately $85M/year across 18+ marketing vendors (CTV, podcast, digital out-of-home, display, affiliates, etc.).

Your primary responsibility will be standardising and automating the ingestion of vendor spend data into a unified schema that feeds a Marketing Mix Model (MMM). Currently, vendors deliver data via Excel and CSV files in wildly inconsistent formats — different column names, different date formats, mixed brands, hidden data, summary rows, and more.

We have defined a **target output schema** that all vendor data must conform to. Your job is to get it there.

---

## Target Output Schema

All vendor data must be transformed into the following standardised format:

| Column | Type | Example | Rules |
|--------|------|---------|-------|
| Date | DATE (YYYY-MM-DD) | 2026-01-15 | Daily granularity required. If source is weekly, note in Spend_Type. |
| Vendor | STRING | MediaWave Digital | Standardised vendor name (not abbreviations). |
| Brand | STRING | StakePoint | Must be one of: StakePoint, WagerLine, NeonSpin, MegaReels. Standardise all abbreviations (SP, WL, NS, MR). |
| Campaign | STRING | March Madness Awareness | Campaign name as provided by vendor. |
| Marketing_Channel | STRING | CTV | Must be one of: Broadcast/Radio, CTV, Display, DOOH, Influencer/Social, Podcast/Audio, PR/Other, Sponsorship. |
| Sub_Channel | STRING | Connected TV - Streaming | Vendor-specific sub-classification. |
| Daily_Spend | FLOAT | 4523.50 | USD. Non-negative. Use net spend where both gross and net are available. |
| Daily_Impressions | INT or NULL | 125000 | Integer or NULL if unavailable. Never "N/A" or text. |
| Spend_Type | STRING | Actual | "Actual" for source data. "Proportioned" if weekly/monthly spread across days. |

---

## The Task

You have been given **three vendor Excel files**, each with different structures and different problems. For each file:

1. **Write a Python script** that reads the Excel file, cleans it, and outputs a standardised CSV conforming to the target schema above.

2. **Document the issues** you found in each file — what was messy, what assumptions you made, what you would flag back to the vendor or to the team.

3. **Produce three clean CSV output files** — one per vendor — that are ready to load into a data warehouse.

### The three files:

- **Vendor_A_MediaWave_Jan2026.xlsx** — A CTV vendor. Reasonably structured but has data quality issues you'll need to handle.
- **Vendor_B_StreetLevel_Jan2026.xlsx** — A digital out-of-home (DOOH) vendor. Multiple tabs, different structure, and there's spend data that's easy to miss.
- **Vendor_C_AudioBlast_Jan2026.xlsx** — A podcast vendor. The messiest file. Non-standard layout with merged cells, text-based date references, and multiple brands mixed together.

---

## What We're Evaluating

- **Can you handle messy, real-world data?** These files are representative of what you'll encounter daily. We want to see that you can navigate Excel files that weren't designed for machines to read.

- **Do you catch edge cases?** There are traps in these files — hidden data, summary rows that shouldn't be ingested, text values where numbers should be, inconsistent brand naming. We want to see how many you catch.

- **Is your code production-quality?** Clean, readable, well-structured Python. Not a Jupyter notebook with print statements — something that could be scheduled and run unattended.

- **Do you communicate what you find?** A short writeup per vendor explaining: what issues you found, what assumptions you made, what you'd flag back. This matters as much as the code.

---

## Deliverables

1. **Python script(s)** — one script or one per vendor, your choice on structure.
2. **Three output CSV files** — one per vendor, conforming to the target schema.
3. **A short writeup** (can be in the same file as comments, a separate markdown, or however you prefer) covering:
   - Issues found per vendor
   - Assumptions made
   - What you would flag to the team or back to the vendor
   - Any suggestions for how you'd improve the process going forward
4. **A vendor data delivery specification** — a one-page document that you would send to these vendors telling them exactly how you want their data delivered going forward. Think of it as: "If you could get these vendors to send you the data in a perfect format from next month onwards, what would you ask for?" This should be clear enough that a non-technical account manager at the vendor could follow it.

---

## Time Expectation

This should take **1-2 hours**. Don't over-engineer it. We want to see how you think and whether you catch the problems, not whether you can build a framework.

Good luck.

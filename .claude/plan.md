# Plan: Revert Final chapter to flat table, keep Approval vendor-grouped

## Context
The user only wants vendor grouping in the **Approval** chapter. The **Final** chapter should remain a flat table: `month > file rows` (no vendor groups).

## Files
- `web/pipeline_dashboard/templates/pipeline_dashboard/folders.html`

## Changes

### 1. Revert Final HTML (lines ~1331–1382)
Restore the original flat table structure:
- Add back the `<thead>` with 8 columns: Vendor, File, Version, Period, Modified, Size, Uploader, Action
- Remove vendor group header rows (`data-vendor-group`) and per-vendor column header rows (`data-vendor-head`)
- Restore flat file rows: no `hidden`, no `data-vendor-files`, keep `data-vendor-name` for search, keep Vendor `<td>`

### 2. Split CSS column widths
Current CSS uses shared selectors for both tables. We need to split them:
- **Approval table**: keep the 7-column layout (current, no Vendor column)
- **Final table**: restore the 8-column layout (original, with Vendor column)
- Restore `min-width: 1480px` for Final table

### 3. Revert Final search JS
- `resetFinalSearch`: show all flat `data-final-row` rows (remove vendor-group/head reset logic)
- `performFinalSearch`: iterate flat rows directly, match against name/vendor/month (remove vendor-group hierarchy)

### 4. Keep everything else
- Approval HTML stays with vendor grouping
- Approval search stays with vendor-group logic
- Global vendor toggle handler stays (it just won't find any groups in Final)
- Vendor group CSS stays (won't match Final elements anyway)
- All review-modal fixes stay intact

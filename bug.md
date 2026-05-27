# Bug Report: CSV table in Parse preview overlaps navigation tabs

## Context
- Django app managing vendor-submitted Excel/CSV files.
- Page: `/process/` — Parsing & Approval workflow.
- Modal: review dialog for previewing files before approval.

## Problem Description
When opening the **Parse** preview modal and clicking the **"File CSV"** navigation tab, the CSV table overflows upward and visually covers the 4 navigation buttons (Spend / Impressions / Cost per impression / File CSV) at the top of the modal body. The other 3 chart tabs render correctly and stay within bounds.

**User reported:** The same overflow does **not** happen in the 2nd sub-window (Review / Approval preview), which shares the same CSS but works correctly. This means the DOM structure or how the CSS was applied must differ between the two flows.

## Root Cause Investigation

### Layout Architecture
The modal body (`.review-body`) is a CSS grid:
```css
.review-body {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  min-height: 0;
  overflow: hidden;
}
```

- **Row 1**: `.review-tabs-row` (sheet tabs)
- **Row 2**: content area

When the Parse result appears (after clicking Parse), it replaces the preview:
- `.parse-result` is placed into **grid row 2** via:
  ```css
  .review-body > .parse-result:not([hidden]) { grid-row: 2; }
  ```

### Inside `.parse-result`
```css
.parse-result {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}
```

It contains:
1. `.parse-result-tabs` (the 4 navigation buttons) — `flex: 0 0 auto`
2. `.parse-result-view` — `flex: 1 1 auto; overflow: hidden;`

### Chart tab (works)
The chart is rendered inside `.parse-chart-card`, which has:
```css
.parse-chart-card {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.parse-chart-card canvas {
  display: block;
  width: 100%;
  height: 100%;
}
```
The `<canvas>` element has `height: 100%`, which forces it to fill the container. The container cannot grow beyond its flex bounds.

### CSV tab (broken)
The CSV table is rendered inside `.parse-csv-panel`, which had:
```css
.parse-csv-panel {
  flex: 1 1 auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.parse-csv-table-wrap {
  flex: 1 1 auto;
  min-height: 0;
  overflow: auto;
}
```

#### Why flex fails here but works for charts
In a **flex column container**, when a child has `overflow: auto` and contains content with a large intrinsic height, the flex algorithm sometimes **prioritizes the content's intrinsic size** over the container's flex-basis, especially when the parent is itself a flex item inside another flex container (`.parse-result-view` → `.parse-result` → `.review-body` grid cell).

The chart works because `<canvas height="100%">` explicitly tells the browser: "my height is 100% of my parent, period." There is no intrinsic height to fight against. The browser simply scales the canvas to fit.

The table, however, has a large intrinsic height (many rows). Even with `overflow: auto` on its wrapper, the **flex algorithm** can allow the wrapper to expand beyond the flex-basis to accommodate the table's intrinsic size, because the wrapper itself is a flex item with `flex: 1 1 auto`. This causes the entire `.parse-csv-panel` to grow, pushing it outside the `.parse-result-view` bounds and overlapping the tabs above.

### Why the Review/Approval window works
The Review modal (in `folders.html`) uses the same `.review-body` grid, but its content is a `.review-preview` element:
```css
.review-preview {
  min-height: 0;
  background: var(--panel);
  padding: 12px 28px 0;
  display: grid;
  grid-template-rows: 1fr;
}
.review-preview-scroll {
  min-height: 0;
  overflow: auto;
  padding: 0 0 12px;
}
```

Notice: `.review-preview` uses **CSS Grid** (`display: grid; grid-template-rows: 1fr;`), not flex. Grid is much stricter about sizing than flex. In a grid, `minmax(0, 1fr)` or `1fr` **always** clamps the row to the available space. The child with `overflow: auto` is forced to scroll. This is why the Review modal never overflows.

## Final Fix
Change `.parse-csv-panel` from **flex** to **grid**, matching the successful Review modal pattern:

```css
.parse-csv-panel {
  margin-top: 0;
  flex: 1 1 auto;
  min-height: 0;
  display: grid;
  grid-template-rows: 1fr auto;
  overflow: hidden;
}

.parse-csv-table-wrap {
  min-height: 0;
  overflow: auto;
}
```

### Explanation of the fix
- `display: grid` replaces `display: flex`, eliminating flex's intrinsic-size expansion behavior.
- `grid-template-rows: 1fr auto` creates two rows:
  - Row 1 (`1fr`): the table wrapper takes all remaining space and is strictly clamped.
  - Row 2 (`auto`): the optional note (`.parse-csv-note`) takes only its natural height.
- `overflow: hidden` on the panel prevents any grid blow-out.
- `min-height: 0` on `.parse-csv-table-wrap` allows the wrapper to shrink to zero if needed, then scroll via `overflow: auto`.

## Files Changed
- `web/pipeline_dashboard/templates/pipeline_dashboard/base.html`
  - `.review-body > .parse-result:not([hidden])` — changed `grid-row: 1 / -1` to `grid-row: 2` to ensure it occupies only the second grid row.
  - `.parse-csv-panel` — changed from `display: flex; flex-direction: column;` to `display: grid; grid-template-rows: 1fr auto; overflow: hidden;`
  - `.parse-csv-table-wrap` — removed `flex: 1 1 auto;`, kept `min-height: 0; overflow: auto;`

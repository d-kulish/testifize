---
name: design
description: Use for Testifize repo-local frontend design work, especially Django template/CSS updates for the ShareFile vendor pipeline control panel. Applies the selected "Linear Ops Console" concept to dashboard, files/assets, ShareFile folders, process, parser validation, approvals, vendors, navigation, tables, modals, charts, and status UI. This is a local product design contract for /Users/dkulish/Projects/testifize, not a global Codex skill.
---

# Testifize Design

## Purpose

This is the repo-local design contract for the Testifize Django control panel.
Use it when changing or evaluating the frontend of the internal ShareFile vendor pipeline app.

The selected visual reference is:

```text
skills/design/assets/reference-linear-ops-console.png
```

Open this image with `view_image` before significant frontend implementation. Treat it as the source of truth for layout rhythm, density, tone, and component relationships. Do not copy it pixel-for-pixel if the live app has different data or constraints, but preserve the product language.

## Product Identity

Testifize is not a marketing site and not a generic admin panel. It is expert internal software for vendor file operations:

- scan ShareFile folders;
- catalogue incoming Excel/CSV files;
- assign files to vendors;
- detect duplicates and superseded files;
- preview spreadsheet contents;
- run vendor-specific parsers;
- validate parsed outputs;
- send parsed CSVs to Approval;
- finalize approved outputs into ShareFile Final folders.

The interface should feel like a modern operations cockpit for a small expert team: precise, calm, dense, readable, and trustworthy.

## Source Concept Summary

The reference concept is a light, modern, high-density SaaS operations screen:

- Large left navigation panel with the dark Testifize logo placed on a light surface.
- Thin top utility bar with global search, upload action, notifications, help, and user menu.
- KPI card row across the top of the main work area.
- Main content dominated by a dense `File Queue` table.
- Right-side operational rail with catalogue mix, parser health, and activity feed.
- Spreadsheet preview and validation modal floating over the file queue.
- Mostly white and cool gray surfaces, with blue as primary accent and green/amber/red semantic feedback.

The core impression to preserve: a real production tool, not a theme demo.

## Non-Negotiables

- Keep the app light. The dark Testifize logo must always sit on white or near-white.
- Use a left navigation panel and right main content area as the stable app shell.
- Prioritize dense operational information over decorative empty space.
- Tables, filters, and modals are first-class design surfaces, not afterthoughts.
- Use semantic status colors consistently.
- Preserve clear user workflow: scan -> classify -> process -> validate -> approval -> final export.
- Do not imply unsupported automation or upload actions that the backend does not support.
- Do not hide operational state behind vague labels.

## Anti-Patterns

Avoid:

- old Bootstrap admin-template styling;
- 1990s/2000s beveled panels or primitive HTML table look;
- dark sidebar where the logo disappears;
- oversized marketing hero sections;
- landing-page composition;
- decorative blobs, orbs, bokeh, or unnecessary gradients;
- card-heavy dashboards where every small value gets a floating tile;
- round bubble UI with weak alignment;
- generic SaaS filler content unrelated to vendor files;
- one-note purple or blue-purple gradient palettes;
- beige/cream dashboard themes;
- low-density "pretty" screens that make file operations slower;
- icons or controls that resize rows or shift table layout;
- popups that look detached from the product system.

## App Shell

### Sidebar

The sidebar is the app's navigation spine.

Use:

- width around `220-260px` on desktop;
- white or very light gray background;
- subtle right border;
- Testifize logo at top, large enough to be recognizable;
- active nav item with soft blue background and blue icon/text accent;
- nav items arranged by workflow importance.

Recommended navigation order:

```text
Overview
Files / Assets
Vendors
Parsers
Validations
Approvals
Final Exports
ShareFile Folders
Alerts
Reports
Settings
```

The live app currently has pages like dashboard, assets, folders, process, vendors, and admin. Map labels to live routes conservatively:

- `Overview` -> dashboard
- `Files` or `Assets` -> asset catalogue
- `ShareFile Folders` -> folders page
- `Approvals` and parser validation surfaces -> process page until split into dedicated routes
- `Vendors` -> vendor catalogue
- `Settings/Admin` -> Django Admin

Keep lower sidebar utility items small: Help & Docs, Collapse, version label.

### Top Bar

Use a thin top bar in the main area:

- global search centered or left-of-center;
- quick action such as Upload/Scan only if backend behavior exists;
- notification bell with count badge;
- help icon;
- user chip/menu.

The search placeholder should be domain-specific:

```text
Search files, vendors, folders...
```

Do not add a decorative top nav. The top bar is a utility surface.

## Layout

Desktop layout should follow this hierarchy:

```text
left sidebar | top utility bar
             | KPI strip
             | main queue/table + right operations rail
             | modal/drawer overlay for review and validation
```

Main page width should be used efficiently. Avoid narrow centered dashboards.

Use restrained spacing:

- outer page padding: `20-24px`;
- panel gap: `16-20px`;
- table row height: `38-44px`;
- KPI card height: `88-108px`;
- border radius: usually `6-8px`;
- avoid very large radii.

## Color System

Use a neutral light base:

```text
Page background: #f7f8fb or #f8fafc
Panel background: #ffffff
Subtle panel background: #f3f6fa or #f8fafc
Border: #e1e7ef / #e5e7eb
Text: #101828 / #111827
Muted text: #667085 / #64748b
```

Primary accent:

```text
Blue: #2563eb or #1d4ed8
Blue soft: #eff6ff / #eef4ff
```

Semantic accents:

```text
Green success/ready/approved: #16a34a / #15803d
Amber warning/validation: #d97706 / #b45309
Red error/rejected/failed: #dc2626 / #be123c
Violet duplicate/superseded: #7c3aed / #6d28d9
Cyan optional secondary: #0891b2 / #0e7490
```

Do not let semantic colors dominate. Most of the UI should remain neutral.

## Typography

Use system UI or Inter-like typography.

Rules:

- no negative letter spacing;
- no viewport-scaled font sizes;
- page heading around `28-32px`;
- panel heading around `15-17px`;
- table body around `13-14px`;
- table headers around `11-12px`, uppercase or semibold muted;
- labels and metadata around `12px`;
- status badges around `12px`, bold enough for scanning.

Text should feel operational and direct. Avoid marketing copy.

## KPI Strip

KPI cards in the reference concept are compact, horizontal, and operational.

Use 5-6 cards when useful:

```text
New Files (24h)
Processing
Validation Warnings
Ready for Approval
Approved (7d)
Duplicates Detected
```

Each KPI card should include:

- simple line icon;
- label;
- large value;
- small supporting link or trend.

Keep cards aligned and equal height. Do not nest cards inside another card.

## File Queue

The file queue is the heart of the design.

Use a table-first layout with:

- title: `File Queue`, `Asset Catalogue`, or page-specific equivalent;
- status tabs with counts;
- filter row;
- dense table;
- row status badges;
- stable action column.

Recommended tabs:

```text
All
New
Processing
Parsed
Warnings
Ready
Approved
Rejected
```

Recommended filters:

```text
Search by file or vendor
Vendor
File Type
Status
Date range
Filters button
Settings/columns icon
```

Recommended columns:

```text
File Name
Vendor
File Type
Uploaded / Modified
Status
Parser
Validation
Duplicate
Action
```

For the current Django pages, adapt columns to available data but keep this hierarchy:

- file identity first;
- vendor second;
- source/folder/provenance nearby;
- status and parser state visible without opening a modal;
- edit/admin action last.

Long filenames must ellipsize but preserve full value in `title` attributes where possible.

## Status Design

Status badges should be pill-like but compact.

Suggested mapping:

```text
New -> blue
Queued / Processing -> blue or cyan
Downloaded / Parsed / Ready -> green
Warnings / Validation Warnings -> amber
Review / Approval -> violet or blue
Approved / Uploaded / Processed -> green
Duplicate / Superseded -> violet or gray-violet
Rejected / Failed -> red
Ignored -> gray
```

Use both color and text. Do not rely on color alone.

## Right Operations Rail

The right rail is for live operational context, not random dashboard filler.

Use panels like:

- `Catalogue Mix`: horizontal bars by file type or status.
- `Parser Health`: parser name plus compact progress bar and percentage.
- `Activity Feed`: timestamped recent actions.
- `Vendor Load`: vendors with pending/processing/approval counts.

This rail should be narrower than the main queue, roughly `280-340px`.

Do not duplicate the main table. The rail should answer "what needs attention?"

## Charts

Use compact, embedded charts:

- horizontal bars for mix and health;
- small trend line only when time matters;
- avoid large decorative charts;
- no fake 3D, no gradients, no chartjunk.

Charts should use visible labels and numbers. A chart without readable values is not useful for this app.

## Preview And Validation Modal

The spreadsheet preview modal is the signature interaction from the concept.

Use it for:

- reviewing a file before processing;
- validating parser output;
- confirming approval handoff.

Recommended modal structure:

```text
Header:
  Preview & Validate
  filename
  status badge
  expand icon
  close icon

Tabs:
  Source Preview
  Parsed Output
  Validation
  File Info
  Activity

Body:
  spreadsheet-like grid with sticky-ish headers

Footer / Summary:
  Parsing Summary
  Validation Summary
  Duplicate Check
  Actions dropdown
  primary action button
  close button
```

Summary blocks should be compact and data-rich:

```text
Parser
Rows Parsed
Columns Mapped
Parse Time
Warnings
Errors
Passed
Duplicate status
```

The primary modal action should match the workflow stage:

- `Move to Processing`
- `Parse`
- `Send to Approval`
- `Approved`

Do not use browser-native `confirm()` as the final UX for important workflow actions if a styled modal pattern exists.

## Buttons And Controls

Buttons:

- primary: solid blue;
- success/final approval: solid green only when action is final/positive;
- secondary: white with border;
- danger: red but use sparingly;
- small table buttons should not change row height.

Controls:

- filters should be compact and aligned;
- selects should visually match inputs;
- action buttons should be explicit;
- icon-only controls need accessible labels/tooltips in implementation.

Use familiar icons from a library if/when frontend dependencies permit it. If not, use CSS/text labels rather than custom decorative SVGs.

## Page Mapping

### `base.html`

Owns:

- global app shell;
- sidebar;
- logo;
- top utility bar if shared;
- typography tokens;
- button, badge, table, panel, modal primitives.

Move most inline style from template into a maintainable static CSS file if feasible.

### `dashboard.html`

Should resemble the reference overview:

- KPI strip;
- primary file/review queue;
- right operations rail;
- recent activity or parser health;
- fast links to scan/update/admin only where supported.

### `assets.html`

Should be the dense file queue/catalogue version:

- tabs/filters at top;
- high-density table;
- clear status and provenance;
- action column;
- no oversized cards.

### `folders.html`

Should preserve folder grouping but modernize:

- folder summary rows;
- file table inside expanded folder;
- compact pagination;
- review modal aligned to the same Preview & Validate design.

### `process.html`

Should become the strongest workflow page:

- processing files grouped by vendor;
- approval queue;
- parser preview/validation modal;
- parser comparison chart styled like the concept;
- final approve/cancel actions with consistent modal treatment.

### `vendors.html`

Can stay table-first, but add scorecard-like information only if it helps:

- vendor;
- parser key;
- active status;
- folders;
- assets;
- notes;
- parser health or pending count if available.

Do not turn this page into decorative vendor cards unless the data supports it.

## Implementation Guidance

When implementing:

1. Open the reference image.
2. Inspect current Django templates and views for available data.
3. Start with shared shell and component CSS.
4. Apply to the most important operational page first, usually dashboard or process.
5. Keep behavior stable unless the user explicitly asks for UX behavior changes.
6. Verify at desktop and mobile widths.
7. Check that the logo remains readable.
8. Check long filenames, empty states, and dense tables.

Implementation should usually be incremental:

- first: shell, typography, tokens, buttons, badges, panels, tables;
- second: dashboard and assets;
- third: folders/process modals;
- fourth: vendor-specific refinements.

## Responsive Behavior

Desktop is primary, because this is an internal operations tool.

Still support narrower widths:

- sidebar can stack or collapse;
- KPI row wraps;
- right rail moves below main table;
- tables scroll horizontally rather than crushing columns;
- modal width uses `min()` and leaves viewport padding.

Do not make mobile design drive the desktop experience.

## Validation Checklist

Before calling frontend work done:

- logo visible on a light surface;
- left nav and top utility surfaces are aligned;
- table rows are dense but readable;
- status badges are semantically colored;
- primary workflow action is visually obvious;
- modal has header, tabs/body, summary, and footer actions;
- right rail contains useful operational context;
- empty states are calm and short;
- no old admin-template look;
- no decorative gradients/orbs/blobs;
- text does not overflow buttons or badges;
- `git diff --check` passes;
- run relevant Django checks/tests if templates or view behavior changed.

## Suggested Language

Use concise product text:

```text
File Queue
Preview & Validate
Source Preview
Parsed Output
Validation
Ready for Approval
Validation Warnings
Duplicates Detected
Parser Health
Catalogue Mix
Activity Feed
Send to Approval
Move to Processing
Final Export
```

Avoid vague text:

```text
Manage things
Beautiful analytics
Advanced dashboard
Next-gen insights
```

The app should sound like it knows the work.

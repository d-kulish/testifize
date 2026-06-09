# Vendor Details Tab — Analysis & Implementation Roadmap

## Context

The `/vendors/` page has a modal popup with two tabs: **Reporting** and **Details**.  
The **Reporting** tab is reserved for pipeline-centric data (coverage matrix, KPIs, etc.).  
The **Details** tab is the place to surface everything known about a single vendor: who they are, where their files live, who uploads them, what has happened recently, and what needs attention next.

This document captures the data inventory (what exists today), what can be fetched live from ShareFile, and a phased build plan for populating the Details tab without blocking on the larger `docs/vendors.md` redesign.

---

## 1. Data Inventory — What Exists Today (Zero New Models)

### 1.1 Vendor Identity & Health

| Field | Source | Notes |
|-------|--------|-------|
| Name, parser key, notes, active flag | `Vendor` model | Already shown on cards |
| Parser health (schema + parser `.py` present?) | `vendor_dashboard.parser_health()` | Returns `has_schema`, `has_parser`, `schema_path`, `parser_path` |
| Linked folders | `vendor.folders.all()` | `ShareFileFolder` rows with role (`input`/`output`/`both`) |
| Folder count | `vendor.folders.count()` | Already computed in `vendor_summary()` |

### 1.2 Observed People / Uploaders

| Field | Source | Notes |
|-------|--------|-------|
| Name, email, upload count, last upload | `Asset.objects.filter(vendor=…)` grouped by `created_by_name`/`created_by_email` | `vendor_dashboard.observed_people()` already does this |
| Resolved SF user metadata | `data/state/sharefile_users_latest.json` | Maps `LastModifiedByUserID` → full name, email, company. Populated by `sync_sharefile_users.py`. |

### 1.3 Raw Files (Inbox / Discovery)

| Field | Source | Notes |
|-------|--------|-------|
| File name, size, extension, created/modified dates | `Asset` model + SF snapshot | `remote_created_at`, `remote_modified_at`, `file_size` |
| Sheet count | `data/state/inbox_profile_latest.json` | `profile.get("sheet_count")` |
| Current status | `Asset.status` | `new` → `processing` → `review` → `processed` → `uploaded` |
| Duplicate role | `Asset.duplicate_role` / `duplicate_group` | `original` vs `duplicate` |
| Is active flag | `Asset.is_active` | Files can be manually deactivated |
| Local path / remote path | `Asset.local_path`, `remote_path` | |
| Source folder | `Asset.source_folder` or `source_folder_label` | |
| Content hash | `Asset.content_hash` | For integrity checks |
| Raw SF metadata | `Asset.raw_metadata` | Full ShareFile API response blob |

### 1.4 Parsed / Approval / History Files

| Field | Source | Notes |
|-------|--------|-------|
| Parsed output path | `ParsedOutput` | `output_path`, `approved_path` |
| Reporting period | `ParsedOutput.reporting_period` | e.g. `May_2026` |
| Period start/end dates | `ParsedOutput.period_start`, `period_end` | Used for the 12-month coverage matrix |
| Row count, total spend, impressions | `ParsedOutput` | |
| Comparison status | `ParsedOutput.comparison_status` | `pending`, `sent_for_approval`, `approved`, `cancelled` |
| Version | `ParsedOutput.version` | Incremented on re-parse |
| Comparison summary (JSON) | `ParsedOutput.comparison_summary` | Includes `sharefile_item_id`, `final_sharefile_path`, etc. |
| Created at | `ParsedOutput.created_at` | |

### 1.5 Event / Activity Stream

| Field | Source | Notes |
|-------|--------|-------|
| Event type | `AssetEvent` | `discovered`, `rediscovered`, `status`, `review_started`, `vendor_changed`, `approval_sent`, `final_approved`, `processing_cancelled`, `parsed_output_cancelled` |
| From / to status | `AssetEvent.from_status`, `to_status` | |
| Message | `AssetEvent.message` | Human-readable description |
| Timestamp | `AssetEvent.created_at` | |
| Metadata (JSON) | `AssetEvent.metadata` | e.g. `{"vendor_id": 3, "previous_vendor": "Loop"}` |
| Actor | — | **Not yet populated.** `docs/vendors.md` plans to add `AssetEvent.actor` FK to `PipelineUser`. |

### 1.6 ShareFile Mirror Data (JSON snapshots)

`scripts/mirror_sharefile.py` produces `data/state/sharefile_snapshot_latest.json` with:
- All files visible to the service account
- `remote_item_id`, `name`, `size`, `created_at`, `modified_at`
- `source_folder_id`, `source_folder_path`
- `raw_metadata` including `LastModifiedByUserID`, `Creator`, `ProgenyEditDate`, etc.
- `sharefile_hash`

`scripts/sync_sharefile_users.py` resolves user IDs to:
- `full_name`, `short_name`, `first_name`, `last_name`, `email`, `username`, `company`

---

## 2. What Can Be Pulled Live from ShareFile API (Ad-Hoc)

The `ShareFileClient` (`src/testifize_pipeline/sharefile/client.py`) already exposes these methods:

### 2.1 Folder Access Controls / Permissions
```python
client.list_access_controls(folder_id)
```
Returns principals with levels:
- `CanView`, `CanDownload`, `CanUpload`, `CanDelete`, `CanManagePermissions`
- `NotifyOnUpload`, `NotifyOnDownload`

**Use case:** Show a mini matrix of who has access to this vendor's folders. Highlight missing required permissions.

### 2.2 Full Folder Tree
```python
client.list_children(folder_id)
```
**Use case:** Render a tree view of the vendor's folder hierarchy and file counts per subfolder.

### 2.3 Individual File Metadata
```python
client.get_item(item_id)
```
**Use case:** Deep metadata for a selected file: creator, modifier, parent folder, size, dates.

---

## 3. Proposed Layout for the "Details" Tab

### Panel A: Vendor Health & Parser (Easiest)
Already computed in `vendor_dashboard.py`. Show as a compact status bar:
- **Parser status**: `Ready` (green) / `Missing schema` / `Missing parser` — with clickable paths.
- **Folder list**: `Input: home/.../josh` | `Output: home/.../output` — linked to SF.
- **Health badges**: "Parser missing", "No folders", "Review pending", "No observed users", "Healthy".

### Panel B: Upload Activity Histogram (GitHub-Style)
Use `Asset.objects.filter(vendor=vendor, remote_created_at__isnull=False)` to build a daily upload histogram.
- Render: a grid of small squares (like GitHub contributions), one square per day, color-intensity = number of files uploaded.
- Tooltip: "3 files on Jun 5, 2026".
- Range: last 90 days or 1 year.

**Query pattern:**
```python
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta

cutoff = timezone.now() - timedelta(days=90)
histogram = (
    Asset.objects.filter(vendor=vendor, remote_created_at__gte=cutoff)
    .values("remote_created_at__date")
    .annotate(count=Count("remote_item_id"))
    .order_by("remote_created_at__date")
)
```

### Panel C: Observed Uploaders / Contacts
Reuse `vendor_dashboard.observed_people()`:
- Table: Name | Email | Upload count | Last upload | Company (from SF user cache if resolved).
- "Promote to contact" affordance (stub until `VendorContact` model exists).

### Panel D: Recent Raw Files
Compact table of the vendor's latest `Asset` rows (not yet processed):
- Name | Status badge | Size | Uploaded | Uploader | Folder.
- Status badges: `New`, `Processing`, `Review`, `Processed`, `Failed`, `Duplicate`.
- Click → opens parse/review modal.

**Query pattern:**
```python
recent_assets = (
    Asset.objects.filter(vendor=vendor)
    .select_related("source_folder")
    .order_by("-remote_modified_at")[:20]
)
```

### Panel E: Files in Approval
Show `ParsedOutput` rows where `comparison_status="sent_for_approval"`:
- Output path | Period | Version | Rows | Spend | Impressions | Age.
- "Review" button (reuse existing modal from `/process/`).

**Query pattern:**
```python
approval_files = (
    ParsedOutput.objects.filter(vendor=vendor, comparison_status="sent_for_approval")
    .select_related("asset")
    .order_by("-created_at")
)
```

### Panel F: Approved History
Show `ParsedOutput` rows where `comparison_status="approved"`:
- Same columns as Panel E plus "Download" button.
- Include the 12-month coverage matrix already computed for the vendor card.

**Query pattern:**
```python
history_files = (
    ParsedOutput.objects.filter(vendor=vendor, comparison_status="approved")
    .select_related("asset")
    .order_by("-created_at")
)
```

### Panel G: Activity Stream / Event Log
Show `AssetEvent` rows for this vendor's assets:
- Timestamp | File | Event type | From → To | Message.
- Filter chips: `discovered`, `status_change`, `parse`, `approval`, `upload`, `cancelled`.

**Query pattern:**
```python
events = (
    AssetEvent.objects.filter(asset__vendor=vendor)
    .select_related("asset")
    .order_by("-created_at")[:50]
)
```

### Panel H: Permission Snapshot (Live API Call)
For each of the vendor's folders, call `client.list_access_controls()` and render:
- **Folder**: `home/.../josh`
- **Principals**: Service account | Vendor uploader | Internal operators
- **Effective rights**: View ✓ | Download ✓ | Upload ✗ | Delete ✗
- **Drift indicator**: Red if a required permission is missing (requires `PermissionTemplate` model from `docs/vendors.md` for full automation; can be eyeballed without it).

**Implementation note:** This is a **button-triggered probe**, not a background job. The `ShareFileClient` call is live and already available in `client.py`.

### Panel I: Duplicate File Analysis
Use `Asset.duplicate_group` and `duplicate_role`:
- Group files by `duplicate_group`.
- Show: Original file + all duplicates.
- Highlight which duplicate is active vs inactive.
- Action: "Keep this one, deactivate others".

### Panel J: Expected vs Observed Reporting Pattern
Requires new heuristic logic:
- Based on `reporting_period` values from `ParsedOutput`, infer the vendor's **expected cadence** (e.g. "monthly by the 15th").
- Compare against `Asset.remote_created_at` dates.
- Highlight: "Expected May report — missing" or "June report uploaded early".

**Status:** No explicit "expected reporting date" field exists yet. Build only after Panels A–I are solid.

---

## 4. Data Requiring New Models (Per `docs/vendors.md`)

| Entity | What it enables for Details tab |
|--------|--------------------------------|
| `VendorContact` (promoted from `Asset.created_by_email`) | Confirmed contacts with roles, not just "observed". Link/unlink actions. |
| `PipelineUser` (operators) | Shows *who on our team* manages this vendor. Adds `actor` to events. |
| `DistributionGroup` | Shows vendor-side groups and their members. |
| `PermissionTemplate` + `FolderPermission` | Renders the required-vs-actual permission matrix with drift highlighting. |
| `Asset.resolved_contact` FK | Replaces raw `created_by_name/email` with a confirmed contact identity. |
| `AttentionItem` | Central "needs action" queue — e.g. "Vendor X has no uploads in 14 days". |
| `NotificationRule` | Read-only list: "Who gets notified when this vendor uploads?" |

**Guideline:** Do **not** block the Details tab on these new models. Build the tab with **existing data first** (Phase 1), then upgrade individual panels as new models land.

---

## 5. Build Order

### Phase 1 — Populate Details Tab with Existing Data (No New Models)

1. **Vendor context endpoint**: Ensure `build_vendor_page_context()` or a new helper passes all per-vendor data needed for the modal. Currently the modal is JS-only and receives only the vendor name. We need a server-side endpoint or richer context.
2. **Panel A (Health + Parser)**: Compact status bar at the top of the Details tab.
3. **Panel B (Upload histogram)**: Daily squares, last 90 days. Pure CSS grid + data attributes.
4. **Panel C (Observed uploaders)**: Mini-table, reuse `observed_people()`.
5. **Panel D (Recent raw files)**: Last 10–20 assets.
6. **Panel E (Approval files)**: Last 5 `sent_for_approval` outputs.
7. **Panel F (History files)**: Last 5 `approved` outputs + coverage matrix.
8. **Panel G (Activity stream)**: Last 20 events with type filter chips.

### Phase 2 — Live ShareFile Integration

9. **Permission probe button**: "Check folder permissions" calls `client.list_access_controls()` via an API endpoint and renders the matrix in a sub-panel. Endpoint: `POST /vendors/<id>/probe-permissions/`.
10. **Folder tree expansion**: Optional — list children of each folder for a quick "what's in there" view.

### Phase 3 — Upgrade When `docs/vendors.md` Models Land

11. Replace "observed uploaders" with `VendorContact` table (confirmed contacts, roles, promote flow).
12. Add `AttentionItem` feed (e.g. "No activity in 14 days", "Parser failing repeatedly").
13. Add permission drift highlighting using `PermissionTemplate` (red = missing required, green = OK, amber = excess).
14. Add `NotificationRule` preview (read-only: "Who gets notified on upload?").
15. Build Panel J (expected vs observed reporting pattern).

---

## 6. API / Query Cheat-Sheet

```python
# Upload histogram (last 90 days)
cutoff = timezone.now() - timedelta(days=90)
histogram = (
    Asset.objects.filter(vendor=vendor, remote_created_at__gte=cutoff)
    .values("remote_created_at__date")
    .annotate(count=Count("remote_item_id"))
    .order_by("remote_created_at__date")
)

# Observed people (already in vendor_dashboard.py)
people = observed_people(vendor)

# Recent raw files
recent_assets = (
    Asset.objects.filter(vendor=vendor)
    .select_related("source_folder")
    .order_by("-remote_modified_at")[:20]
)

# Approval queue
approval_files = (
    ParsedOutput.objects.filter(vendor=vendor, comparison_status="sent_for_approval")
    .select_related("asset")
    .order_by("-created_at")
)

# History
history_files = (
    ParsedOutput.objects.filter(vendor=vendor, comparison_status="approved")
    .select_related("asset")
    .order_by("-created_at")
)

# Event stream
events = (
    AssetEvent.objects.filter(asset__vendor=vendor)
    .select_related("asset")
    .order_by("-created_at")[:50]
)

# SF permissions (live API call — ad-hoc)
from testifize_pipeline.sharefile.client import ShareFileClient, ShareFileConfig
# client.list_access_controls(folder.folder_id)
```

---

## 7. Next Immediate Step

The modal currently opens via pure JS and only receives the **vendor name**. To populate the Details tab with real data, the next technical task is to:

1. Create a new API endpoint (e.g. `GET /vendors/<id>/details/`) that returns a JSON payload with all Phase 1 panels' data.
2. Wire the modal's JS to fetch this payload when opened.
3. Render each panel in the `data-vendor-tab-panel="details"` container using the returned JSON.

This keeps the modal lightweight (no full page reload) and gives us a clean separation between data fetching and presentation.

---

*Document created: 2026-06-09*
*Based on: `docs/vendors.md`, current models (`Vendor`, `Asset`, `AssetEvent`, `ParsedOutput`, `ShareFileFolder`), and existing `ShareFileClient` capabilities.*

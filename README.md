# Testifize ShareFile Vendor Pipeline

This project is being reshaped into an automated pipeline for vendor report processing:

1. connect to ShareFile with the service account;
2. scan configured ShareFile folders for new or changed vendor files;
3. download Excel/CSV inputs locally;
4. parse vendor-specific formats into the shared target schema;
5. validate and reconcile the parsed outputs;
6. upload normalized results, logs, or reports back to ShareFile.

The old technical-assessment README has been removed because it described a one-off parsing task. Some old directories still exist in the repository, but they should be treated as historical source material until the new project structure is implemented.

## Current Status

ShareFile API access has been validated from this machine.

Validated capabilities:

- OAuth password-grant authentication works with the ShareFile service account when using a ShareFile app password.
- The service account can list folders visible to it.
- The service account can upload a tiny CSV into a test ShareFile folder after explicit folder permissions are granted.

Validated service account:

```text
svc.sfdataccess@ptytechnologies.com
```

Validated tenant:

```text
https://ppfcorp.sharefile.eu
subdomain: ppfcorp
API base after authentication: https://ppfcorp.sharefile.com
```

Validated write target:

```text
Shared Folders/test_upload
folder id: foefd961-ff1d-42b0-a27b-9616cd09dcef
```

Validated upload probe:

```text
testifize_upload_probe_20260507T094214Z.csv
file id: fi992540-e129-3f6e-a3be-936da6d5ef4c
```

## ShareFile Credentials

The API flow needs an app-specific password, not the normal interactive login password.

Required `.env` keys:

```env
SHAREFILE_SUBDOMAIN=ppfcorp
SHAREFILE_USER=svc.sfdataccess@ptytechnologies.com
SHAREFILE_CLIENT_ID=...
SHAREFILE_CLIENT_SECRET=...
SHAREFILE_APP_PASSWORD=...
```

Legacy or unrelated keys should not be used by the new downloader:

```env
SHAREFILE_PWD=...
SHAREFILE_PASSWORD=...
SMTP_*
```

`SHAREFILE_PWD` may still be useful for manual browser login, but the automation should authenticate with `SHAREFILE_APP_PASSWORD`.

## How ShareFile Access Was Proven

### 1. OAuth Client Was Required

A first direct token request using only username and password failed because ShareFile required an OAuth client:

```text
invalid_request: missing client_id
```

The previous engineer's handover folder contained the missing OAuth client information in:

```text
/Users/dkulish/Documents/Work/Testifize/BOL_Matias_Handover_20260422/01_scripts/05_vendor_onboarding/local.settings.json
```

That file proved the expected credential shape:

```text
SHAREFILE_CLIENT_ID
SHAREFILE_CLIENT_SECRET
SHAREFILE_SUBDOMAIN
SHAREFILE_USER
SHAREFILE_PASSWORD
```

The old stored password was stale, so it produced:

```text
invalid_grant: invalid username or password
```

### 2. App Password Was Required

The service account has multi-factor authentication enabled. For custom API scripts, a ShareFile app password must be generated under the same service account:

```text
svc.sfdataccess@ptytechnologies.com
```

The app password was generated from:

```text
Personal settings -> Sign in options -> Multi-factor authentication -> App passwords -> Generate
```

App name used:

```text
testifize_vendor_downloader
```

After adding the generated value as `SHAREFILE_APP_PASSWORD`, OAuth authentication succeeded:

```text
token_status=200
token=<present>
expires_in=28800
token_type=bearer
```

### 3. Folder Listing Was Proven

After authentication, the pipeline can call ShareFile API endpoints with:

```text
Authorization: Bearer <access_token>
```

The root listing returned:

```text
Personal Folders
Shared Folders
Favorites
```

The service account initially saw folders under `home`, but `Shared Folders/test_upload` returned `403 Forbidden` until the service account was explicitly added to that folder.

### 4. Folder Permissions Were Required

The test upload folder initially failed with:

```text
403 Forbidden
You do not have permission to access the selected item: foefd961-ff1d-42b0-a27b-9616cd09dcef
```

After adding `svc.sfdataccess@ptytechnologies.com` to the folder, ShareFile displayed the user as:

```text
Team, Data
```

Required folder permissions for this automation:

```text
View
Download
Upload
```

Delete/Admin are not required for the normal downloader/parser/uploader flow unless the pipeline will clean up remote files or manage permissions.

### 5. Upload Was Proven

The upload probe used this flow:

1. Authenticate with `SHAREFILE_APP_PASSWORD`.
2. `GET /sf/v3/Items(<folder_id>)` to confirm folder access.
3. `POST /sf/v3/Items(<folder_id>)/Upload?...` to prepare a standard raw upload.
4. `POST` the CSV bytes to the returned `ChunkUri`.
5. `GET /sf/v3/Items(<folder_id>)/Children` to verify the uploaded file exists.

The successful probe returned:

```text
folder_status=200 name=test_upload
upload_prepare_status=200
upload_chunk_status=200 response='OK'
upload_verified=True
```

## Target Project Shape

The current `final/`, `test/`, and `vendors/` folders came from the older assessment/vendor-parser work. They can still be mined for parser examples, schemas, and sample files, but they should not define the long-term architecture.

The first new project layer now lives under:

```text
src/testifize_pipeline/sharefile/
src/testifize_pipeline/assets/
```

`sharefile/` owns API communication. `assets/` owns the local catalogue of remote files, statuses, provenance, and processing state.

Recommended structure:

```text
testifize/
  README.md
  requirements.txt
  .env
  .gitignore

  config/
    sharefile_folders.example.json
    vendors.example.json

  schemas/
    target_schema.json
    vendor_inputs/

  src/
    testifize_pipeline/
      __init__.py
      cli.py
      config.py
      state.py

      assets/
        __init__.py
        catalog.py

      sharefile/
        __init__.py
        client.py
        downloader.py
        uploader.py
        scanner.py

      parsers/
        __init__.py
        base.py
        registry.py
        adtaxi.py
        loop.py
        tvm.py

      validation/
        __init__.py
        schema.py
        reconciliation.py

      io/
        __init__.py
        excel.py
        csv.py
        paths.py

  web/
    manage.py
    testifize_web/
    pipeline_dashboard/

  data/
    inbox/
    processed/
    output/
    state/

  docs/
    sharefile_access.md
    vendor_onboarding.md
    operations.md

  tests/
    fixtures/
    unit/
    integration/
```

### Core Concepts

`sharefile/client.py`

Owns OAuth token acquisition, token refresh if needed, low-level GET/POST/PATCH calls, retries, and safe error messages.

`sharefile/scanner.py`

Lists configured folders, filters files by extension and modification time, and compares remote files against local state.

`sharefile/downloader.py`

Downloads remote Excel/CSV files into a deterministic local folder, preserving remote metadata such as ShareFile item ID, file name, modified timestamp, and source folder.

`parsers/`

Contains one parser module per vendor or vendor-format family. Each parser should take a local input file and return rows in the target schema.

`validation/`

Checks exact target headers, required fields, numeric types, date formats, and optional vendor-specific reconciliation rules.

`sharefile/uploader.py`

Uploads normalized CSVs, validation reports, or pipeline logs back to a configured output folder.

`state.py`

Provides shared filesystem/path helpers for pipeline state. The canonical catalogue is now the Django database, not a separate hand-rolled state file.

`assets/catalog.py`

Historical plain-Python catalogue work. Keep it as source material for CLI compatibility, but do not treat `data/state/asset_catalog.sqlite` as the production source of truth.

## Current Pipeline Flow

The current Django workflow is centered on a local ShareFile mirror, a parsing queue, parser preview, generated CSV review, and a ShareFile Approval handoff:

```text
SF folders -> Review -> Parsing Files -> Parse -> chart/CSV review -> Approval upload -> external review
```

The older CLI command surface remains useful for low-level checks and future automation:

```bash
python -m testifize_pipeline scan
python -m testifize_pipeline download
python -m testifize_pipeline process
python -m testifize_pipeline upload
python -m testifize_pipeline run
```

Recommended dry-run behavior:

```bash
python -m testifize_pipeline run --dry-run
```

Dry run should authenticate, list candidate files, and report intended downloads/uploads without mutating ShareFile.

## ShareFile Folder Configuration

Folder mapping should be configuration-driven, not hardcoded inside parser code.

Example shape:

```json
{
  "vendors": {
    "AdTaxi": {
      "input_folder_id": "fo...",
      "output_folder_id": "fo...",
      "parser": "adtaxi",
      "file_patterns": ["*.xlsx", "*.csv"]
    }
  }
}
```

Use folder IDs rather than display paths where possible. ShareFile item IDs are stable even if folders are renamed.

## Local File Policy

Recommended local layout:

```text
data/inbox/<vendor>/<sharefile_item_id>/<original_filename>
data/output/<vendor>/<run_id>/<normalized_csv>
data/processed/<vendor>/<run_id>/<reports>
data/state/testifize_web.sqlite3
```

The `data/` directory should be ignored by git unless a small fixture is intentionally committed for tests.

## Asset Catalogue

The Django asset catalogue is the answer to the overlap problem: there may be many remote files that look similar, cover the same period, or were uploaded more than once. The pipeline should not silently choose or skip files based only on a filename.

Catalogue every matching ShareFile file first, then make processing decisions from local state.

Tracked fields include:

```text
remote_item_id
vendor
status
name
sharefile_folder_id
source_folder_label
remote_path
file_size
remote_created_at
remote_modified_at
created_by_name
created_by_email
local_path
output_path
uploaded_item_id
parser
parser_version
content_hash
duplicate_group
duplicate_role
is_active
status_reason
first_seen_at
last_seen_at
updated_at
raw_metadata_json
```

Initial statuses:

```text
discovered
new
queued
downloading
downloaded
processing
review
processed
uploading
uploaded
superseded
ignored
failed
```

`superseded` is important for overlapping files. It lets the pipeline say: "we saw this file, but a newer or more authoritative file replaced it." That is much better than making the file disappear from the workflow.

### Duplicate Detection

Files with the same normalized name are tagged as **Original** (the earliest ShareFile `created_at` in that group) or **Dup** (all uploaded copies). This applies to both the live JSON mirror and synced `Asset` records; the `duplicate_role` field is stored in the Django database and backfilled by the `reconcile_duplicates` management command.

### Active Flag

Every file in the catalogue has an `is_active` boolean, defaulting to **Active**. In the SF folders UI, each file row has an Active toggle:

- **Active** (default): file behaves normally, Review button is available, row has a light green background when the status is new/active/review
- **Inactive**: file row background turns grey and faded, Review button is disabled
- **Processed** and **Deleted** files are visually identical to inactive files (grey background, disabled Review button) because they are already out of the workflow

The `is_active` field is a database-level toggle, so setting a file to Inactive excludes it from processing and persists across mirror refreshes. The toggle saves to the Django database via an async POST, automatically creating an Asset record for files that only exist in the mirror and don't have one yet.

See [docs/asset_catalog.md](docs/asset_catalog.md) for the catalogue design.

## Current CLI Skeleton

The first CLI commands are intentionally low-level:

```bash
PYTHONPATH=src python -m testifize_pipeline.cli scan --folders config/sharefile_folders.json
PYTHONPATH=src python -m testifize_pipeline.cli assets
PYTHONPATH=src python -m testifize_pipeline.cli upload-test --folder-id foefd961-ff1d-42b0-a27b-9616cd09dcef
```

Use [config/sharefile_folders.example.json](config/sharefile_folders.example.json) as the template for the local, untracked `config/sharefile_folders.json`.

## Django Control Panel

The project now includes a local Django control panel under `web/`.
Django owns the operational catalogue going forward; the earlier `data/state/asset_catalog.sqlite` file is historical scratch state.

Install dependencies and create the local Django database:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
python web/manage.py migrate
python web/manage.py createsuperuser
```

Start the local app:

```bash
./start_dev.sh
```

The app opens at:

```text
http://127.0.0.1:8000/
```

If port `8000` is busy, `start_dev.sh` automatically moves to the next available port and prints the URL.

App pages:

```text
/          dashboard
/folders/  ShareFile folder catalogue with two chapters: Loaded Folders (file search, status sorting, review entrypoint) and Approval (read-only browser of ShareFile Approval CSVs grouped by month and vendor)
/process/  Parsing page with three chapters: Parsing Files queue, Approval review queue, and approved-file History
/admin/    Django Admin back office
```

The app pages are operational views for the normal workflow. Admin remains available for back-office catalogue edits and exceptional recovery actions.

The `/folders/` **Approval** chapter surfaces every CSV that the pipeline has uploaded to ShareFile `Approval/<Month_Year>/<Vendor>/`. Months are listed newest-first, vendors are alphabetical, and each file row exposes a `Review` button (read-only preview) and a `Download` button (serves the local file under `data/inbox/...`). Files that exist in the mirror but not locally are flagged as missing. This chapter is read-only by design; approve / cancel actions remain on the `/process/` Approval queue where the `ParsedOutput` rows live.

First v1 workflow:

1. Create `Vendor` rows for each vendor.
2. Create `ShareFileFolder` rows with the ShareFile folder ID, role, file patterns, and optional vendor.
3. Open `SF folders` and click `Update` to refresh the local ShareFile mirror.
4. Review mirrored folders sorted by new-file count. Files with the same normalized name are tagged as **Original** (the earliest ShareFile `created_at` in that group) or **Duplicate** (all uploaded copies). This applies to both the live JSON mirror and synced `Asset` records; the `duplicate_role` field is stored in the Django database and backfilled by the `reconcile_duplicates` management command.
5. Use the search bar in the header to find files by name or uploader email. Matching folders auto-expand and matching file names are highlighted.
6. Inside each folder, files are sorted into three tiers: active under-review files at the top (light green), active finished files in the middle (grey), and inactive files at the bottom (grey). Within each tier files are sorted by modified timestamp, newest first.
7. Open a file row, assign an allowed vendor, and move it to `Parsing`.
8. On `Parsing`, open the file row, inspect raw workbook sheets, click `Parse`, and review the parsed charts plus final CSV preview.
9. Click `Approval` only after the generated CSV preview and KPI charts look correct.

The SF folders review modal can restrict the vendor dropdown by source folder. The current rule for `home/josh` allows only:

```text
PodcastOne, Octopus, Loop, TVM, TAIV
```

The current rule for `allshared/May_2026_Internal_folders` allows only:

```text
RallyAdMedia, AdTaxi
```

The current rule for `home/pm` allows only:

```text
S2
```

The same rule is enforced server-side when moving a file from SF folders into Processing, so bypassing the UI cannot assign a disallowed vendor.

Downloaded files land under:

```text
data/inbox/<vendor-or-unassigned>/<sharefile_item_id>/<original_filename>
```

The Django database lives at:

```text
data/state/testifize_web.sqlite3
```

Local admin user setup is machine-specific. Do not commit local users or the SQLite database.

Development checks:

```bash
.venv/bin/python web/manage.py check
.venv/bin/python web/manage.py test pipeline_dashboard
PYTHONPATH=src .venv/bin/python -m compileall -q src web
git diff --check
```

## Parser Policy

Detailed vendor migration steps live in `docs/parser_migration.md`.

Vendor parsers should not know about ShareFile. They should only handle local files and target-schema rows.

Good parser boundary:

```text
local file path -> normalized rows + parser diagnostics
```

Bad parser boundary:

```text
ShareFile folder -> download -> parse -> upload
```

Keeping ShareFile outside the parser layer makes it easier to test vendors independently and rerun parsers on local files.

Tracked vendor parser definitions live under:

```text
parsers/<Vendor>/input_schema.json
parsers/<Vendor>/parser.py
```

Historical approved CSVs from `_old/final/` are imported into local, ignored runtime storage:

```bash
PYTHONPATH=src .venv/bin/python scripts/import_approved_history.py
```

The app uses approved files as comparison baselines directly under each vendor folder:

```text
data/processed/<Vendor>/
```

Approval-review parser outputs are versioned under the approval period, defined
as the month after the parsed reporting period:

```text
data/output/<Vendor>/<Vendor>_<Mon>_<Year>_vN.csv
```

The first migrated parsers are `Loop`, `TVM`, `TAIV`, `PodcastOne`, `Octopus`, `RallyAdMedia`, `AdTaxi`, and `S2`. TAIV combines the Prime and Retail tables on `Spend By Day` into one daily row per date, matching the approved TAIV history shape. PodcastOne combines the BASE daily sheet and WC daily sheet by `Day`. Octopus combines the `DOOH` and `Rideshare` tables on `Daily Spend` into one daily row per date. RallyAdMedia combines the `BOL`, `SB`, `WC`, and `SS` sheets by `DATE_LABEL`, summing `Imps.` into `Impressions` and `Total Spend` into `Spend`. AdTaxi reads the March 2026 date range from the `Dates` row, sums the three top-level `Advertiser Cost` and `Impressions` cells, and distributes each total across every date in that range. S2 parses the `April.26` sheet, reads the four horizontal daily tables (`BOL`, `Wild Casino`, `Sportsbetting`, `Superslots`) starting at row 31, aggregates `Spend` and `Video Plays` by `Day` into one daily row per date, and outputs `Brand=BetOnline`, `Channel=CTV`, `Platform=S2 Network`.

On the `/process/` Parsing page, opening a file first shows raw workbook sheets. Clicking `Parse` switches into a parsed-review state with four tabs: `Spend`, `Impressions`, `Cost / impression`, and `Final CSV`. The chart tabs compare the generated candidate against up to two latest approved vendor periods, grouping spend and impressions by date. The `Final CSV` tab shows the generated normalized rows for visual inspection before the user sends anything for ShareFile approval. This parse preview does not write the output CSV.

The approved-history importer canonicalizes `_old/final/Taiv.csv` into `data/processed/TAIV/TAIV.csv` so the parser workflow can find TAIV history by the app vendor name.

The modal `Approval` action writes the versioned parsed CSV under `data/output/<Vendor>/`, uploads that same versioned CSV to ShareFile `Approval/<Approval_Period>/<Vendor>/`, stores the ShareFile item ID, creates a `ParsedOutput` record, and moves the source `Asset` into Review.

`data/processed/<Vendor>/` is reserved for files that have actually been approved. The ShareFile Approval upload is only an external review request, so it does not create or update `data/processed/<Vendor>/`.

The Approval table tracks sent review files. Each entry now includes a **blue, centered Review button** in its own column to reopen the parsed CSV review without re-running the original parser. `Cancel` cancels that parsed output and returns the source asset to Processing Files. `Approved` copies the parsed CSV into `data/processed/<Vendor>/<Vendor>_<Reporting_Period>.csv`, uploads that final-named CSV to ShareFile `Final/<Reporting_Period>/`, stores the final ShareFile item ID, and moves the source asset from Review to Processed.

ShareFile approval upload defaults to the ShareFile `allshared` root, so approved CSVs are uploaded under Shared Folders unless overridden. To use a different root folder, set:

```text
SHAREFILE_APPROVAL_ROOT_ID=<folder-id-or-alias>
```

The app ensures this path under the selected root before approval upload:

```text
Approval/<Approval_Period>/<Vendor>/<Vendor>_<Mon>_<Year>_vN.csv
```

For example, rows dated in March 2026 are submitted for review under
`Approval/April_2026/<Vendor>/` with a filename like
`<Vendor>_Apr_2026_v1.csv`.

When a review file is approved, the app ensures this final path under the selected root:

```text
Final/<Reporting_Period>/<Vendor>_<Reporting_Period>.csv
```

## Recent Changes

### SF Folders page (2026-05-15)

- **Column renames and reorder**: "Total Files" → "Total", "Deleted in SF" → "Deleted". Column order changed to `New | Active | Review | Processed | Deleted | Total`.
- **Inactive file exclusion**: toggled-off (inactive) files are no longer counted in New, Active, Review, or Processed folder totals. Total and Deleted counts remain unchanged.
- **Search reset fix**: clearing the search input now re-applies the active "with-files" filter, so empty folders stay hidden.
- **Folder row styling**: folder names and file stat text increased from 14px to 16px for better readability.
- **Expand/collapse icon**: replaced `+`/`-` text symbols with a CSS chevron (`>` / `v`) and reduced size by ~15%.
- **File table header**: the header row inside an expanded folder now uses a light-blue background (`#dbeafe`) with solid black column text, matching the chapter header palette.

### S2 vendor parser (2026-05-20)

- **New parser `S2`**: added `parsers/S2/input_schema.json` and `parsers/S2/parser.py` to handle the `pm` folder's Connected-TV Excel files.
- **Sheet target**: `April.26` (configurable for other monthly sheets).
- **Table layout**: four horizontal 3-column tables (`Day`, `Spend`, `Video Plays`) starting at row 31 — one per brand (`BOL`, `Wild Casino`, `Sportsbetting`, `Superslots`).
- **Aggregation**: all four tables are aggregated by date into a single daily row with summed `Spend` and `Impressions`.
- **Output defaults**: `Vendor=S2`, `Brand=BetOnline`, `Channel=CTV`, `Platform=S2 Network`, `Data_Grain=daily`.
- **Folder vendor assignment**: added `pm` to `FOLDER_VENDOR_RULES` with a single allowed vendor `S2`, and added migration `0009_seed_s2_vendor.py` to create the vendor and bind existing `pm` folders.
- **Auto-assignment fallback**: `_source_folder_for_file` now auto-assigns a vendor when a folder has exactly one allowed vendor and no vendor is currently set.

### Parsing page (2026-05-20)

- **Chapter header restyle**: replaced the plain `.panel-header` with a blue bar (`#3b6cb4`) matching the SF folders "Loaded Folders" header, containing the chapter title, subtitle with file count, and a real-time search input.
- **Search by file name**: added a search bar that filters parsing files by name across all vendor groups, with yellow highlight on matching text and auto-expansion of groups containing matches.
- **Vendor row KPIs**: removed static placeholder text ("Parsing", "Click file", "Per row"). Each vendor row now shows actual **Files** count, **Size** (sum of file sizes in the group), and **Oldest** file age.
- **Expand/collapse icon**: replaced the default `+`/`-` with the same CSS chevron used on SF folders.
- **Inner table header**: the file table inside an expanded vendor group uses the same light-blue header (`#dbeafe`) as SF folders.

### Parsing review charts (2026-05-20)

- **Old final CSV baseline**: `approved_csv_paths()` now falls back to `_old/final/{Vendor}.csv` when `data/processed/{Vendor}/` has no approved CSVs. This gives S2 and other migrated vendors a usable comparison baseline from the historical export.
- **Artifact month filtering**: `latest_approved_period_series()` now requires at least 5 rows per month before including that month as a baseline. This prevents sparse future-dated artifact rows (e.g. 2026-01 with a single row) from being selected over real historical periods.
- **Comparison panel**: added a generated-vs-approved comparison panel below the summary on parse review, showing Spend, Impressions, and date-mismatch notes.
- **Chart tab bar moved below chart**: the `Spend / Impressions / Cost / impression / Final CSV` tab buttons now render below the chart/table view instead of above it, so they are not occluded by the sticky modal header.
- **Circle markers on chart lines**: each data point now renders a small circle marker, making individual days visible.
- **Tab button cursor**: added `cursor: pointer` to chart tab buttons for clearer interactivity.
- **Grid layout fix**: `.review-body > .parse-result:not([hidden])` now spans `grid-row: 1 / -1`, so the chart area fills the available modal height.

### CSV table overflow fix (2026-05-27)

- **Problem**: clicking the "File CSV" tab in the parse-review modal caused the CSV table to overflow upward and visually cover the 4 navigation buttons (Spend / Impressions / Cost / impression / File CSV).
- **Root cause**: `.parse-result` used `display: flex; flex-direction: column`. In nested flex contexts, a child with large intrinsic content (a tall table) can expand beyond its allocated space and spill over siblings. Charts worked because `<canvas height="100%">` has no intrinsic height to fight against.
- **Fix**: changed `.parse-result` to `display: grid; grid-template-rows: auto 1fr auto;`. This creates three isolated, rigid rows:
  - Row 1 (`auto`): the navigation buttons
  - Row 2 (`1fr`): the chart / table view — strictly clamped to remaining space, forced to scroll internally
  - Row 3 (`auto`): the KPI summary pills
- **File**: `web/pipeline_dashboard/templates/pipeline_dashboard/base.html`

### Folders Approval chapter (2026-06-01)

- **Goal**: make ShareFile `Approval/` CSVs visible from the `/folders/` page without forcing the user to navigate to `/process/`. The `/process/` Approval queue reads from the Django `ParsedOutput` table, but the ShareFile mirror itself already lists every CSV uploaded under `allshared/Approval/<Month_Year>/<Vendor>/`. The new chapter surfaces the same files directly from the mirror, grouped by month and vendor.
- **Chapter shape**:
  - Mirror head uses the same blue `Loaded Folders` styling; subtitle shows the total file and month counts.
  - Outer `<details>` per `Month_Year` (newest first). Summary shows the month label plus the number of vendors and files.
  - Inner `<details>` per `Vendor` (alphabetical). Summary shows the vendor name and file count.
  - Inner table per vendor with columns: `File`, `Version`, `Period`, `Modified`, `Size`, `Uploader`, `Action`. Version is extracted from the filename (`_v<N>.csv`).
  - Search input filters by file name, vendor, or month. Matching months/vendors auto-expand.
  - Files missing locally (e.g. mirror references a file that was deleted) get a red `is-missing` row with a disabled download button.
- **Read-only by design**: the chapter only exposes `Review` and `Download` actions. The `Approved` / `Cancel` actions that move a parsed output to ShareFile `Final/` and back to `Processing/` stay on the `/process/` Approval queue, where the `ParsedOutput` row is the source of truth.
- **Review modal**: reuses the existing modal from the `Loaded Folders` chapter in a new `data-mode="approval"`. The modal hides the `Vendor` select and `Parsing` button via CSS, and shows only `Close`. Behind the scenes it calls a new `review_approval_file` view that streams the local CSV preview through `build_file_preview` (no parser invocation).
- **Download**: new `download_approval_output` view streams the local CSV with the original filename, mirroring the existing `download_approved_output` on `/process/`. Returns 404 if the remote item is not in the current ShareFile Approval mirror.
- **Backend**:
  - `sharefile_mirror.py`: added `load_approval_mirror()` that walks only `allshared/Approval/...` (and the `home/Approval/...` equivalent) and returns a `MirrorData` of `months -> vendors -> files`. Excludes `Final/`. Existing `load_sharefile_mirror()` is unchanged so the `Loaded Folders` chapter still hides internal workflow folders.
  - `views.py`: new `_approval_file_row(remote_item_id)` helper, new `review_approval_file` and `download_approval_output` GET views. The `folders` view also passes `approval_months` and `approval_summary` to the template.
  - `urls.py`: added `folders/approval/<remote_item_id>/review/` and `folders/approval/<remote_item_id>/download/`.
- **Frontend**:
  - `folders.html`: new section below `Loaded Folders` (`folders-approval-panel`), new CSS scope (kept distinct from `process.html`'s `approval-panel` to avoid cross-talk), new `[data-approval-review-button]` and `[data-approval-folders-search]` handlers. The existing review modal gets a `data-mode` attribute that toggles between the `Loaded Folders` review (`Parsing` button + vendor select visible) and the new `Approval` review (both hidden).
- **Tests** (in `pipeline_dashboard/tests/test_views.py`):
  - `test_load_approval_mirror_groups_newest_first_alphabetical` confirms month order, vendor order, version extraction, `exists_locally` flag, and that `Final/` plus normal vendor folders are excluded.
  - `test_folders_page_renders_approval_chapter` confirms the chapter renders with newest months first, alphabetical vendors, version column populated, `Download` and `Review` buttons, no `Approve` / `Cancel` buttons in the chapter, and the missing-file marker.
  - `test_review_approval_file_returns_preview` and `test_review_approval_file_returns_404_for_unknown`.
  - `test_download_approval_output_returns_csv` and `test_download_approval_output_404_for_unknown`.
  - `test_download_approval_output_excludes_final_folder` confirms the `Final/` files are still hidden from the Approval download endpoint.
- **Files**: `web/pipeline_dashboard/sharefile_mirror.py`, `web/pipeline_dashboard/views.py`, `web/pipeline_dashboard/urls.py`, `web/pipeline_dashboard/templates/pipeline_dashboard/folders.html`, `web/pipeline_dashboard/tests/test_views.py`.

### Folders Final chapter (2026-06-02)

- **Goal**: add a 3rd chapter `Final` on `/folders/` that mirrors the `Approval` chapter but shows files from ShareFile `Final/<Month_Year>/`. These are the approved CSVs that have been promoted out of the Approval queue.
- **Chapter shape**: identical to Approval — blue mirror head, month groups newest-first, vendor groups alphabetical, file table with columns `Vendor`, `File`, `Version`, `Period`, `Modified`, `Size`, `Uploader`, `Action`.
- **Folder structure difference** (important for parser logic):
  - Approval stores files under `allshared/Approval/<Month_Year>/<Vendor>/file.csv` (vendor in the folder path).
  - Final stores files **directly** under `allshared/Final/<Month_Year>/file.csv` with no vendor subfolder. The vendor name is embedded in the filename (`<Vendor>_<Month>_<Year>.csv`).
  - `_final_split_folder()` handles this by using the filename stem minus the month label when the path only has two parts (`Final/<month>/`).
- **Parsed-output review**: when a `ParsedOutput` is linked to the final file (via `Asset.uploaded_item_id` or `comparison_summary__sharefile_item_id`), the green `Review` button opens the rich parsed-output modal — the same 3 charts, summary pills, and CSV table that `/process/` shows. Otherwise it falls back to a raw CSV preview. The `Review` button is green; the `Download` button is orange, matching the `/process/` palette.
- **Search**: filters by file name, vendor, or month label. Matching months auto-expand.
- **Backend**:
  - `sharefile_mirror.py`: added `load_final_mirror()` and `_final_split_folder()`; `FINAL_FOLDER_NAMES = {"final"}`. The existing `load_sharefile_mirror()` continues to hide internal workflow folders, and `load_approval_mirror()` continues to exclude `Final/`.
  - `views.py`: `_final_file_row()`, `review_final_file()`, `download_final_output()`. The `folders()` view passes `final_months` and `final_summary` to the template.
  - `urls.py`: added `folders/final/<remote_item_id>/review/` and `folders/final/<remote_item_id>/download/`.
- **Frontend**:
  - `folders.html`: new section below Approval, `.final-table` CSS (compact right-aligned columns matching `.approval-table`), `[data-final-search]` and `[data-final-review-button]` handlers. The review modal hides vendor select / Parsing button when `data-mode="final"`.
- **Files**: `web/pipeline_dashboard/sharefile_mirror.py`, `web/pipeline_dashboard/views.py`, `web/pipeline_dashboard/urls.py`, `web/pipeline_dashboard/templates/pipeline_dashboard/folders.html`.

### ShareFile upload notifications for Approval and Final folders (2026-06-04)

- **Problem**: when parsed CSV files were uploaded to ShareFile `Approval/<Month>/<Vendor>/` and `Final/<Month>/`, no upload notifications were sent to folder subscribers. Two root causes:
  1. The app explicitly passed `notify=False` to the ShareFile upload API on every upload, suppressing native notifications.
  2. Dynamically created month and vendor sub-folders did not reliably inherit the parent folder's notification subscriber settings (`NotifyOnUpload`).
- **Solution**:
  - Changed `notify=False` → `notify=True` in both `upload_approved_output()` and `finalize_approved_output()` in `parser_workflow.py`.
  - Extended `ShareFileClient.ensure_folder_path()` with an optional `copy_access_controls=True` parameter. When enabled and a new folder is created, the client copies the parent folder's AccessControls (including `NotifyOnUpload`) to the newly created child folder via the ShareFile API.
  - The `ensure_folder_path` call in `upload_approved_output` now passes `copy_access_controls=True` so that every new `Approval/<Month>` and `Approval/<Month>/<Vendor>` folder carries the same notification subscribers as the parent `Approval` folder.
  - The `ensure_folder_path` call in `finalize_approved_output` also passes `copy_access_controls=True` so that every new `Final/<Month>` folder carries the same notification subscribers as the parent `Final` folder.
- **Files**: `src/testifize_pipeline/sharefile/client.py`, `web/pipeline_dashboard/parser_workflow.py`, `web/pipeline_dashboard/tests/test_views.py`, `web/pipeline_dashboard/tests/test_sharefile_client.py`.

### Approval Review button (2026-05-26)

- **Review parsed output without re-running the parser**: each row in the Approval queue now has a **Review** button (blue, in its own column between *Version* and *Source File*).
- **Identical result view**: clicking it opens the same modal used after parsing — header, 4 navigation tabs (Spend / Impressions / Cost per impression / Final CSV), Chart.js charts compared against approved baselines, up to 200 preview rows, and the 5 summary KPI tablets.
- **Reconstructs from saved CSV**: the backend reads the already-generated parsed CSV (`ParsedOutput.output_path` / `Asset.output_path`) and rebuilds the full review payload without touching the original parser, Excel/CSV source, or vendor parser code.
- **Read-only**: only the **Cancel** button is shown in the footer when reviewing from Approval — Parse, Validate, and Approval actions are hidden.
- **Backend**: added `build_review_payload()` in `parser_workflow.py` and `review_parsed_output` GET view at `process/approval/<id>/review/`.
- **Frontend**: updated approval table layout (centered values for Period, Version, Review, Rows, Spend, Impressions, Comparison, Age, and Action) and added `[data-review-button]` event handler in `process.html`.

### Parser resilience and removal of manual validation (2026-06-04)

- **Problem**: May 2026 vendor files arrived with format drift. PodcastOne renamed its daily summary sheets (`BASE MAY DLY SUMM. 5.1-5.31` instead of `Week 1-5 BASE DLY 4.1-4.30`) and dropped the `Campaign` column from the WC sheet, shifting the remaining columns left. Octopus inserted an extra subtotal row before the Rideshare section, pushing the hardcoded header row from 34 to 35, and added a `Totals` row at the end that crashed the date parser.
- **Old approach**: a partially implemented `Validate` button let users manually probe individual sheets against the schema. It was never fully functional (it did not support multi-worksheet schemas like PodcastOne's, and it could not fix column reordering or row shifts). It has been removed entirely.
- **New approach**: parsers now discover structure automatically instead of relying on hardcoded names and positions.

**PodcastOne**
- `input_schema.json`: replaced exact `sheet_name` with `match_keywords` arrays (`["BASE", "DLY"]`, `["WC", "DLY"]`). Replaced fixed column letters with `columns_by_header` — the parser scans the header row for expected text (`"Day"`, `"Audio Impressions"`, `"$ By Day"`) and discovers the actual column letters. Removed hardcoded `header_row` and `first_data_row`; the parser now discovers the header row dynamically by scanning for a row that contains all expected header texts.
- `parser.py`: added `resolve_sheet_name()` for keyword matching, `discover_columns()` for header-text column discovery, and `_find_header_row()` for dynamic header-row scanning.

**Octopus**
- `input_schema.json`: replaced fixed `header_row: 34` for the Rideshare table with `match_anchor: "Rideshare"` and `anchor_column: "A"`. Added `header_names` for validation at the discovered row.
- `parser.py`: added `resolve_table_bounds()` to scan column A for the `"Rideshare"` anchor text and compute the data row dynamically. Added `header_names` support in `validate_table_header()`. Wrapped date parsing in try/except so non-date rows (e.g. `"Totals"`) are skipped instead of crashing.

**Generic validation**
- `parser_workflow.py`: updated `validate_excel_schema()` and `validate_excel_schema_probe()` to support `match_keywords`, `columns_by_header`, `match_anchor`, `anchor_column`, and `_find_header_row()`. Removed `probe_sheet_validation()` entirely and simplified `parse_asset_rows()` — the extra probe-validation branch is gone.

**UI cleanup**
- `process.html`: removed the `Validate` button, `parseValidate` JS variable, `showParserCorrect()`, and all related event listeners. The parse modal now only shows sheets and the `Parse` button.
- `views.py`: removed `parse_sheet_probe` view.
- `urls.py`: removed `process/<str:remote_item_id>/parse/probe/` route.

**Tests**
- `test_views.py`: updated fixtures to simulate May drift — PodcastOne sheets use May naming and a WC sheet without the Campaign column, with an extra title row shifting the header from row 5 to row 6; Octopus inserts a subtotal row shifting Rideshare from row 34 to 35. Removed the two probe-specific test methods. All 13 parser-related tests pass, backward compatibility confirmed against April files.

**Vendor guidelines**
- Created `docs/vendor_report_guidelines.md` with general structural stability recommendations (sheet/tab stability, column consistency, header row stability, section boundaries, data granularity, file format guidance). These are structural rules, not specific wording requirements.

**Result**
- `PODCASTONE MAY 2026 FINAL REPORT.xlsx`: 31 rows parsed
- `T-MOBILE MAY 2026 FINAL REPORT.xlsx`: 31 rows parsed
- April files continue to parse correctly (30 rows each).

### Octopus UPDATED file rejection (2026-06-05)

- **Problem**: Josh resubmitted `UPDATED T-MOBILE MAY 2026 FINAL REPORT.xlsx` after the initial May file had already been parsed. The UPDATED file removed the `"Daily Spend"` sheet entirely and replaced it with eight new detail sheets (`DOOH Venue Types`, `Rideshare Engagement`, `DOOH Media Owner`, `State`, `State by Day`, `Creatives`, `Raw Data 1`, `Raw Data 2`). The parser failed with `"Sheet 'Daily Spend' was not found"`.
- **Analysis**: The `"Raw Data 2"` sheet (10,321 rows) contains the same combined daily DOOH + Rideshare data at the raw placement level. When aggregated by date, the totals are mathematically identical to the already-processed `Octopus_May_2026.csv`. However, the file structure is fundamentally different — no `"Daily Spend"` sheet, no pre-aggregated daily summary, dates in text format (`"May 1, 2026"`), and multiple overlapping data sources with inconsistent splits between DOOH and Rideshare.
- **Decision**: We **rejected** the structural change. Josh was asked to keep the standard `"Daily Spend"` sheet (with DOOH and Rideshare sections) for automated parsing, and to add any extra detail sheets as *additional* tabs rather than replacements. No parser or schema changes were made to accommodate the UPDATED layout.
- **Rationale**: The vendor guidelines explicitly require sheet/tab stability. Rewriting the parser for a one-off format experiment would set a dangerous precedent, introduce ambiguity about which sheet is authoritative, and add unnecessary complexity. The data was not actually "updated" — the combined daily totals matched the original file exactly. The only change was the vendor experimenting with their reporting tool.

### Vendors page rebuild (2026-06-08)

- **Goal**: replace the old `/vendors/` operational management page (Create Vendor, Vendor Directory, Folder Ownership) with a clean, high-level overview of all configured vendors.
- **Old chapters removed**: `Create Vendor`, `Vendor Directory`, and `Folder Ownership` were removed entirely. The corresponding CRUD routes and forms remain in `urls.py` and `views.py` for future back-office use, but the public page no longer renders them.
- **Header metrics**: the five compact tablets remain, reordered to `Vendors | People | Folders | Active | Parsers`. Each tablet shows a count and a short note.
- **Vendor card grid**: a 4-column responsive grid (`4 → 3 → 2 → 1` on smaller screens) with one card per vendor.
- **Card layout**:
  - **Vendor name** at the top, bold 22px.
  - **Uploader badges** — one pill per observed person (`created_by_name`); shows `No observed uploaders` if empty.
  - **12-month coverage matrix** pinned to the bottom of the card. A row of 12 small boxes (`18px` tall, `2px` radius, `1px` gap) showing `covered` (green), `current` (blue), or `missing` (white). Month labels sit beneath the boxes, truncated to 3 letters (`Jul`, `Aug`, etc.).
- **Coverage logic**: copied from the `/process/` History chapter. `vendor_dashboard.py` now computes a rolling 12-month window and marks each month as covered if any approved `ParsedOutput` overlaps that month. The same `_compute_vendor_coverage()` helper is used.
- **Search bar**: a full-width white panel between the header metrics and the card grid. Filters cards by vendor name or uploader badge text in real time. The counter on the right updates from "8 vendors" to "2 vendors" as matches narrow. Non-matching cards are hidden and the grid reflows. A "No vendors match your search" empty state appears when the query filters everything out.
- **Backend**: `build_vendor_page_context()` now returns `history_months` and `history_coverage` alongside the existing `metrics` and `vendor_rows`.
- **Files**: `web/pipeline_dashboard/vendor_dashboard.py`, `web/pipeline_dashboard/templates/pipeline_dashboard/vendors.html`.

### Vendor Details tab — Phase 1 (2026-06-09)

- **Goal**: populate the existing vendor modal's **Details** tab with real data from the Django catalogue, without creating any new models.
- **Design source**: `docs/vendor_details.md` ( Panels A–G from the phased build plan).
- **New backend endpoint**: `GET /vendors/<id>/details/` returns a single JSON payload with all Phase 1 panel data.
  - `build_vendor_detail_payload(vendor)` in `vendor_dashboard.py` reuses existing helpers (`parser_health`, `observed_people`, `health_badges`) and runs targeted queries for the remaining panels.
- **Panels implemented**:
  - **Panel A — Health & Parser**: compact badge bar showing `Inactive`, `Parser missing`, `No folders`, `Review pending`, `No observed users`, or `Healthy`; plus parser readiness (schema + `.py` present) and folder tags with roles.
  - **Panel B — Upload histogram (90 days)**: GitHub-style contribution grid — 13 weeks × 7 days of 10 px squares with 4-level blue color intensity (`#e5e7eb` → `#1e40af`). Tooltip on each square shows the date and file count.
  - **Panel C — Observed uploaders**: table of `Name | Email | Uploads | Last upload`.
  - **Panel D — Recent raw files**: last 20 `Asset` rows with status badge (`New`, `Processing`, `Review`, `Failed`, etc.), size, modified date, uploader, and source folder.
  - **Panel E — Approval queue**: last 5 `ParsedOutput` rows with `comparison_status="sent_for_approval"`, showing period, version, row count, spend, impressions, and age.
  - **Panel F — Approved history**: last 5 `ParsedOutput` rows with `comparison_status="approved"`, same columns plus a **Download** button linking to the existing `download_approved_output` view.
  - **Panel G — Activity stream**: last 20 `AssetEvent` rows with timestamp, file name, event type, from→to status transition, and message. Includes filter chips (`All`, `Discovered`, `Status`, `Parse`, `Approval`, `Cancelled`) that hide non-matching rows client-side.
- **Frontend wiring**:
  - Each vendor card now exposes `data-vendor-id`.
  - The modal JS stores the current `vendorId`, pre-fetches details on open, and caches the payload per session so switching between **Reporting** and **Details** tabs does not re-fetch.
  - All rendering is done in vanilla JS inside the existing `vendors.html` inline script, matching the page's current architecture.
- **Styling**: scoped CSS added to the existing `<style>` block for `.detail-panel`, `.detail-health-bar`, `.upload-histogram`, `.detail-grid-2`, and `.detail-table`, reusing base.html badge/table variables.
- **Tests** (in `pipeline_dashboard/tests/test_views.py`):
  - `test_vendor_details_returns_all_panels` — full happy path with assets, events, parsed outputs.
  - `test_vendor_details_404_for_missing_vendor`.
  - `test_vendor_details_empty_panels_for_fresh_vendor`.
  - `test_vendor_details_histogram_90_day_cutoff` — confirms the histogram window excludes uploads older than 90 days.
- **Files**: `web/pipeline_dashboard/vendor_dashboard.py`, `web/pipeline_dashboard/views.py`, `web/pipeline_dashboard/urls.py`, `web/pipeline_dashboard/templates/pipeline_dashboard/vendors.html`, `web/pipeline_dashboard/tests/test_views.py`.

## Immediate Next Steps

1. Define the shared target schema location and validation rules for final approved outputs.
2. Add anomaly/comparison summaries beyond the current overlapping Spend, Impressions, and cost-per-impression charts.
3. Decide whether finalized ShareFile uploads should fail on duplicate names, overwrite them, or create explicit new versions.

## Historical Material

The existing directories are not the final architecture:

```text
final/
test/
vendors/
```

They contain useful examples, existing vendor files, old outputs, and parser experiments. During the reshaping phase, treat them as source material to migrate from, not as the structure to preserve forever.

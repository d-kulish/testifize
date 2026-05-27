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
/folders/  ShareFile folder catalogue, file search, status sorting, and review entrypoint
/process/  Parsing page, parser preview, generated CSV review, approval queue
/admin/    Django Admin back office
```

The app pages are operational views for the normal workflow. Admin remains available for back-office catalogue edits and exceptional recovery actions.

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

### Approval Review button (2026-05-26)

- **Review parsed output without re-running the parser**: each row in the Approval queue now has a **Review** button (blue, in its own column between *Version* and *Source File*).
- **Identical result view**: clicking it opens the same modal used after parsing — header, 4 navigation tabs (Spend / Impressions / Cost per impression / Final CSV), Chart.js charts compared against approved baselines, up to 200 preview rows, and the 5 summary KPI tablets.
- **Reconstructs from saved CSV**: the backend reads the already-generated parsed CSV (`ParsedOutput.output_path` / `Asset.output_path`) and rebuilds the full review payload without touching the original parser, Excel/CSV source, or vendor parser code.
- **Read-only**: only the **Cancel** button is shown in the footer when reviewing from Approval — Parse, Validate, and Approval actions are hidden.
- **Backend**: added `build_review_payload()` in `parser_workflow.py` and `review_parsed_output` GET view at `process/approval/<id>/review/`.
- **Frontend**: updated approval table layout (centered values for Period, Version, Review, Rows, Spend, Impressions, Comparison, Age, and Action) and added `[data-review-button]` event handler in `process.html`.

### Sheet probe and parser validation (2026-05-25)

- **Problem**: vendor Excel files sometimes rename sheets or move data to a new sheet. The parser expects a hardcoded `sheet_name` from `input_schema.json`, so the parse preview immediately fails with "Incorrect parser" and the user never sees the other sheets that exist in the file.
- **Solution**: the Parse modal now shows **all sheets** as clickable tabs. A new **Validate** button lets the user probe any selected sheet against the parser schema before running the actual parse.

**How it works**

1. Open a file on the Parsing page. The modal lists every sheet in the Excel file as tabs, not just the schema target.
2. If the default schema sheet is present and validates, the modal behaves exactly as before: the default sheet is pre-selected, `Parse` is active, and `Validate` is hidden.
3. If the default sheet is missing or the headers do not match, the preview shows "Incorrect parser" and `Parse` is disabled. A `Validate` button appears.
4. Click any sheet tab to preview its contents. Then click `Validate`. The app calls the backend probe endpoint (`GET /process/<id>/parse/probe/?sheet_name=<name>`) which checks the selected sheet's header row and columns against the schema.
5. If the probe passes, the preview switches to a green "Parser is correct" message, `Parse` becomes active, and the selected sheet name is remembered.
6. Click `Parse`. The actual parse POST now includes the selected `sheet_name`, and the parser uses that sheet instead of the hardcoded default.

**Backend changes**

- `parser_workflow.py`:
  - Added `validate_excel_schema_probe(source_path, schema, probe_sheet_name)` which validates a candidate sheet's headers against the schema without touching the hardcoded `sheet_name`.
  - Added `probe_sheet_validation(asset, sheet_name)` which returns a full validation payload for a candidate sheet (same shape as the existing validator).
  - Modified `parse_asset_rows(asset, sheet_name=None)` so that when a `sheet_name` override is provided, it probes that sheet first, then passes the override to the parser module.
  - Modified `build_parse_result_preview(asset, sheet_name=None)` to thread the override through.
- `views.py`:
  - Added `parse_sheet_probe(request, remote_item_id)` — a GET endpoint that takes `sheet_name` and optional `vendor_id` query parameters, runs `probe_sheet_validation`, and returns the validation payload.
  - Modified `parse_process_file` to read `sheet_name` from the POST body and pass it to `build_parse_result_preview`.
- `urls.py`:
  - Added route `process/<str:remote_item_id>/parse/probe/`.
- All 8 vendor `parser.py` modules (`Loop`, `AdTaxi`, `S2`, `Octopus`, `TAIV`, `TVM`, `PodcastOne`, `RallyAdMedia`):
  - Updated `parse_file(source_path, input_schema, output_columns, sheet_name=None)` signature.
  - Changed `workbook[input_schema["sheet_name"]]` to `workbook[sheet_name or input_schema["sheet_name"]]` so the override is respected.

**Frontend changes**

- `process.html`:
  - `renderSheets()` now renders every sheet in `file.sheets` as a tab, matching the Review modal tab pattern.
  - Extracted `showIncorrectParser(errors)` and `showParserCorrect()` helper functions for the overlay messages.
  - Added a `Validate` button in the footer (`data-parse-validate`), shown only when validation fails.
  - Sheet tab clicks set `activeParse.selectedSheet` and re-render the preview.
  - `Validate` click fetches the probe endpoint for the selected sheet. On success, it enables `Parse`. On failure, it re-shows "Incorrect parser" with the specific errors.
  - `Parse` click sends `sheet_name` in the POST body if a sheet was selected during probing.
  - `truncateSheetName()` helper added to keep tab labels consistent with the Review modal.

**Limitations**

- Multi-worksheet schemas (`schema["worksheets"]`) are not yet supported by the probe. The probe returns an error immediately if the schema uses the `worksheets` array format. Single `sheet_name` schemas are fully supported.
- CSV files cannot be probed because they do not have named sheets.

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

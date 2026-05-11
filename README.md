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
status_reason
first_seen_at
last_seen_at
updated_at
raw_metadata_json
```

Initial statuses:

```text
new
queued
downloading
downloaded
processing
processed
uploading
uploaded
superseded
ignored
failed
```

`superseded` is important for overlapping files. It lets the pipeline say: "we saw this file, but a newer or more authoritative file replaced it." That is much better than making the file disappear from the workflow.

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
/folders/  ShareFile folder catalogue and review entrypoint
/process/  Parsing page, parser preview, generated CSV review, approval queue
/admin/    Django Admin back office
```

The app pages are operational views for the normal workflow. Admin remains available for back-office catalogue edits and exceptional recovery actions.

First v1 workflow:

1. Create `Vendor` rows for each vendor.
2. Create `ShareFileFolder` rows with the ShareFile folder ID, role, file patterns, and optional vendor.
3. Open `SF folders` and click `Update` to refresh the local ShareFile mirror.
4. Review mirrored folders sorted by new-file count and use duplicate badges to identify repeated file names across folders.
5. Open a file row, assign an allowed vendor, and move it to `Parsing`.
6. On `Parsing`, open the file row, inspect raw workbook sheets, click `Parse`, and review the parsed charts plus final CSV preview.
7. Click `Approval` only after the generated CSV preview and KPI charts look correct.

The SF folders review modal can restrict the vendor dropdown by source folder. The current rule for `home/josh` allows only:

```text
PodcastOne, Octopus, Loop, TVM, TAIV
```

The current rule for `allshared/May_2026_Internal_folders` allows only:

```text
RallyAdMedia, AdTaxi
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

Approval-review parser outputs are versioned under:

```text
data/output/<Vendor>/<Vendor>_<Month>_<Year>_vN.csv
```

The first migrated parsers are `Loop`, `TVM`, `TAIV`, `PodcastOne`, `Octopus`, and `RallyAdMedia`. TAIV combines the Prime and Retail tables on `Spend By Day` into one daily row per date, matching the approved TAIV history shape. PodcastOne combines the BASE daily sheet and WC daily sheet by `Day`. Octopus combines the `DOOH` and `Rideshare` tables on `Daily Spend` into one daily row per date. RallyAdMedia combines the `BOL`, `SB`, `WC`, and `SS` sheets by `DATE_LABEL`, summing `Imps.` into `Impressions` and `Total Spend` into `Spend`.

On the `/process/` Parsing page, opening a file first shows raw workbook sheets. Clicking `Parse` switches into a parsed-review state with four tabs: `Spend`, `Impressions`, `Cost / impression`, and `Final CSV`. The chart tabs compare the generated candidate against up to two latest approved vendor periods, grouping spend and impressions by date. The `Final CSV` tab shows the generated normalized rows for visual inspection before the user sends anything for ShareFile approval. This parse preview does not write the output CSV.

The approved-history importer canonicalizes `_old/final/Taiv.csv` into `data/processed/TAIV/TAIV.csv` so the parser workflow can find TAIV history by the app vendor name.

The modal `Approval` action writes the versioned parsed CSV under `data/output/<Vendor>/`, uploads that same versioned CSV to ShareFile `Approval/<Current_Month>/<Vendor>/`, stores the ShareFile item ID, creates a `ParsedOutput` record, and moves the source `Asset` into Review.

`data/processed/<Vendor>/` is reserved for files that have actually been approved. The ShareFile Approval upload is only an external review request, so it does not create or update `data/processed/<Vendor>/`.

The Approval table tracks sent review files. `Cancel` cancels that parsed output and returns the source asset to Processing Files. `Approved` copies the parsed CSV into `data/processed/<Vendor>/<Vendor>_<Reporting_Period>.csv`, uploads that final-named CSV to ShareFile `Final/<Reporting_Period>/`, stores the final ShareFile item ID, and moves the source asset from Review to Processed.

ShareFile approval upload defaults to the ShareFile `allshared` root, so approved CSVs are uploaded under Shared Folders unless overridden. To use a different root folder, set:

```text
SHAREFILE_APPROVAL_ROOT_ID=<folder-id-or-alias>
```

The app ensures this path under the selected root before approval upload:

```text
Approval/<Current_Month>/<Vendor>/<Vendor>_<Current_Month>_<Current_Year>_vN.csv
```

When a review file is approved, the app ensures this final path under the selected root:

```text
Final/<Reporting_Period>/<Vendor>_<Reporting_Period>.csv
```

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

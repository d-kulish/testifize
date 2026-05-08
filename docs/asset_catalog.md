# Asset Catalogue

The asset catalogue is the local source of truth for files discovered in ShareFile.
It answers operational questions that ShareFile alone does not answer cleanly for this pipeline:

- Which remote files have we already seen?
- Which ones are new or changed?
- Which vendor/folder does a file belong to?
- Who uploaded or created the file when ShareFile exposes that metadata?
- Which file is downloaded, processing, processed, uploaded, superseded, ignored, or failed?
- Which output file was produced from which input file?

The canonical catalogue is now the Django database:

```text
data/state/testifize_web.sqlite3
```

It is intentionally ignored by git. The older `data/state/asset_catalog.sqlite` file can remain locally as historical scratch state, but new operational work should use the Django models.

The Django app owns these catalogue models:

```text
Vendor
ShareFileFolder
Asset
AssetEvent
```

The local app pages are:

```text
/          dashboard
/assets/   asset catalogue
/folders/  ShareFile folder catalogue
/vendors/  vendor catalogue
/admin/    Django Admin back office for edits and actions
```

The `/folders/` page is limited to incoming vendor-file locations. Internal workflow
destinations under ShareFile `Approval/` and `Final/` are excluded, including their
subfolders, because those folders hold review and final output CSVs rather than raw
incoming Excel files.

## Statuses

Supported asset statuses:

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

`new` means the remote file is new to the catalogue or its remote modified timestamp changed since the last scan.

`superseded` should be used when a newer overlapping file replaces an older one.

`ignored` should be used for files that match folder access but should never be processed, such as notes, templates, bad test uploads, or historical duplicates.

`review` means a parsed CSV has been uploaded to ShareFile `Approval/<Current_Month>/<Vendor>/` and is waiting for external approval. The `/process/` Approval table shows only parsed outputs with `comparison_status="sent_for_approval"`.

When an Approval row is green-lighted, the `Approved` action uploads the final CSV to ShareFile:

```text
Final/<Reporting_Period>/<Vendor>_<Reporting_Period>.csv
```

The action then marks the source asset `processed`, stores the final ShareFile item metadata on the parsed output, and removes the row from the Approval table.

## Core Fields

Each asset stores:

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

The remote ShareFile item ID is the primary key because ShareFile IDs are stable across renames.

## Overlapping Files

Overlaps should not be solved inside the ShareFile downloader.

Recommended approach:

1. Catalogue every matching remote file.
2. Group possible overlaps by vendor, date period, source folder, filename tokens, and eventually file content hash.
3. Mark the chosen file as `queued` or `downloaded`.
4. Mark older/duplicate files as `superseded` with a `status_reason`.

This keeps auditability: we can explain why a file was skipped instead of silently ignoring it.

## Commands

For the current Django workflow, configure folders in Admin and run the `Scan selected folders` action from the `ShareFileFolder` changelist.

The older CLI commands are useful for low-level checks and compatibility work:

```bash
PYTHONPATH=src python -m testifize_pipeline.cli scan --folders config/sharefile_folders.json
```

List catalogued assets:

```bash
PYTHONPATH=src python -m testifize_pipeline.cli assets
```

Upload a tiny probe CSV:

```bash
PYTHONPATH=src python -m testifize_pipeline.cli upload-test --folder-id foefd961-ff1d-42b0-a27b-9616cd09dcef
```

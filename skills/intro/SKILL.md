---
name: intro
description: Start-of-session orientation for the Testifize ShareFile vendor pipeline repo. Use at the beginning of sessions in /Users/dkulish/Projects/testifize, before touching ShareFile access, Django control panel work, asset catalogue models, vendor parser architecture, local credentials, or Git sync.
---

# Intro

## Purpose

Use this skill to orient quickly before working in the Testifize repo. The project is becoming a local/internal ShareFile vendor pipeline:

1. scan ShareFile folders;
2. catalogue incoming vendor files;
3. download new or queued Excel/CSV files;
4. assign files to vendors;
5. parse vendor-specific inputs into the target schema;
6. validate results;
7. upload normalized outputs back to ShareFile.

The main product challenge is file chaos: many overlapping vendor uploads, unclear freshness, duplicated periods, and manual status tracking. The system should make every file visible, auditable, and explicitly classified instead of silently choosing by filename.

## First Pass

At session start:

1. Work from `/Users/dkulish/Projects/testifize`.
2. Check `git status --short` before editing.
3. Read `README.md`, `docs/asset_catalog.md`, `start_dev.sh`, and files directly related to the request.
4. Treat `.env`, `data/`, local SQLite databases, downloaded files, tokens, and passwords as local-only.
5. Do not print secret values from `.env`. It is fine to confirm whether required keys are present.
6. Prefer `.venv/bin/python` for checks and tests.

## Current App Shape

The repo now has two layers:

- Plain Python pipeline code under `src/testifize_pipeline/`.
- Local Django control panel under `web/`.

Django owns the operational catalogue. The old `data/state/asset_catalog.sqlite` file is historical scratch state, not canonical.

Canonical Django database:

```text
data/state/testifize_web.sqlite3
```

Important Django models:

```text
Vendor
ShareFileFolder
Asset
AssetEvent
```

Local app pages:

```text
/          dashboard
/assets/   asset catalogue
/folders/  ShareFile folder catalogue
/vendors/  vendor catalogue
/admin/    Django Admin back office for edits and actions
```

Start locally:

```bash
./start_dev.sh
```

`start_dev.sh` applies migrations and starts Django on `127.0.0.1:8000`, falling forward to the next free port if needed.

## ShareFile Access

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

Required `.env` keys for automation:

```env
SHAREFILE_SUBDOMAIN=ppfcorp
SHAREFILE_USER=svc.sfdataccess@ptytechnologies.com
SHAREFILE_CLIENT_ID=...
SHAREFILE_CLIENT_SECRET=...
SHAREFILE_APP_PASSWORD=...
```

Use the ShareFile app password for automation, not the normal interactive password. Ignore old or unrelated credentials such as:

```env
SHAREFILE_PWD=...
SHAREFILE_PASSWORD=...
SMTP_*
```

The app password was generated in ShareFile under:

```text
Personal settings -> Sign in options -> Multi-factor authentication -> App passwords
```

App name used:

```text
testifize_vendor_downloader
```

Do not commit, echo, or paste the app password, client secret, tokens, or `.env` values.

## Proven ShareFile Capabilities

ShareFile API access has been validated from this machine:

- OAuth password-grant authentication works with the service account plus app password.
- The service account can list folders visible to it.
- The service account can upload after explicit folder permissions are granted.

Validated test upload target:

```text
Shared Folders/test_upload
folder id: foefd961-ff1d-42b0-a27b-9616cd09dcef
```

The service account appeared in ShareFile permissions as:

```text
Team, Data
```

Normal folder permissions needed by the pipeline:

```text
View
Download
Upload
```

Delete/Admin are not required unless the pipeline is later asked to clean up remote files or manage permissions.

## Architecture Rules

- Keep ShareFile API logic in `src/testifize_pipeline/sharefile/`.
- Keep orchestration/review state in Django under `web/pipeline_dashboard/`.
- Do not duplicate ShareFile API calls inside Django views or templates. Django services should call the plain-Python ShareFile client/scanner/downloader modules.
- Vendor parsers should not know about ShareFile. Parser boundary: local input file -> normalized rows + diagnostics.
- Catalogue every matching remote file first, then decide status.
- Use `superseded` for older overlapping files instead of hiding or deleting them.
- Use `ignored` for files that should never be processed.
- Keep upload actions out of the app UI until parser-result and validation-review models are designed.

## Key Files

```text
README.md
docs/asset_catalog.md
start_dev.sh
requirements.txt
src/testifize_pipeline/config.py
src/testifize_pipeline/sharefile/client.py
src/testifize_pipeline/sharefile/scanner.py
src/testifize_pipeline/sharefile/downloader.py
src/testifize_pipeline/sharefile/uploader.py
web/testifize_web/settings.py
web/testifize_web/urls.py
web/pipeline_dashboard/models.py
web/pipeline_dashboard/admin.py
web/pipeline_dashboard/services.py
web/pipeline_dashboard/views.py
web/pipeline_dashboard/templates/pipeline_dashboard/
web/pipeline_dashboard/tests/
```

## Checks

Before committing Django or pipeline changes, run:

```bash
.venv/bin/python web/manage.py check
.venv/bin/python web/manage.py makemigrations --check --dry-run
.venv/bin/python web/manage.py test pipeline_dashboard
PYTHONPATH=src .venv/bin/python -m compileall -q src web
git diff --check
```

For low-level CLI compatibility checks:

```bash
PYTHONPATH=src .venv/bin/python -m testifize_pipeline.cli assets
PYTHONPATH=src .venv/bin/python -m testifize_pipeline.cli upload-test --folder-id foefd961-ff1d-42b0-a27b-9616cd09dcef
```

Only run live ShareFile operations when the user expects network/API access.

## Git And Safety

- Never commit `.env`, `data/`, downloaded vendor files, local SQLite databases, app passwords, tokens, or generated caches.
- Check staged diffs for secret-looking values before committing.
- Do not revert user changes unless explicitly asked.
- If syncing to GitHub, commit only intentional project changes and verify `git status --short` before and after.

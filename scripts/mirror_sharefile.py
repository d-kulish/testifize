from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from testifize_pipeline.config import load_dotenv
from testifize_pipeline.sharefile.client import ShareFileClient, ShareFileConfig


DEFAULT_ROOTS = [("home", "home"), ("allshared", "allshared"), ("favorites", "favorites")]
DEFAULT_EXTENSIONS = {".xlsx", ".xls", ".xlsm", ".csv"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Mirror visible ShareFile spreadsheet files into data/inbox.")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--inbox-root", type=Path)
    parser.add_argument("--state-root", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    inbox_root = args.inbox_root or repo_root / "data" / "inbox"
    state_root = args.state_root or repo_root / "data" / "state"
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    state_root.mkdir(parents=True, exist_ok=True)
    inbox_root.mkdir(parents=True, exist_ok=True)
    previous_snapshot = load_previous_snapshot(state_root)

    env = load_dotenv(repo_root / ".env")
    client = ShareFileClient(ShareFileConfig.from_env(env))
    client.authenticate()

    folders, files, scan_errors = collect_files(client)
    downloaded: list[dict] = []
    failures: list[dict] = []

    print(f"run_id={run_id} folders={len(folders)} files={len(files)} scan_errors={len(scan_errors)}")
    for index, record in enumerate(files, 1):
        try:
            updated = mirror_file(
                client,
                record,
                previous_snapshot,
                repo_root,
                inbox_root,
                dry_run=args.dry_run,
            )
            downloaded.append(updated)
            print(f"[{index}/{len(files)}] {updated['download_status']} {updated.get('local_path', record['remote_path'])}")
        except Exception as exc:  # noqa: BLE001 - keep batch moving and snapshot the failure.
            record["download_status"] = "failed"
            record["download_error"] = str(exc)
            failures.append(record)
            print(f"[{index}/{len(files)}] failed {record['remote_path']}: {exc}")

    carried_versions = carry_forward_superseded_versions(previous_snapshot, downloaded)
    snapshot_files = downloaded + carried_versions + failures
    snapshot = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dry_run": args.dry_run,
        "roots": [path for _, path in DEFAULT_ROOTS],
        "folder_count": len(folders),
        "remote_file_count": len(files),
        "file_count": len(snapshot_files),
        "downloaded_count": sum(1 for row in downloaded if row.get("download_status") == "downloaded"),
        "skipped_existing_count": sum(
            1 for row in downloaded if row.get("download_status", "").startswith("skipped")
        ),
        "overwritten_count": sum(1 for row in downloaded if row.get("download_status") == "overwritten"),
        "failed_count": len(failures),
        "versioned_count": sum(1 for row in downloaded if row.get("version_status") == "current_version"),
        "carried_version_count": len(carried_versions),
        "total_remote_bytes": sum(row.get("size") or 0 for row in files),
        "folders": folders,
        "files": snapshot_files,
        "scan_errors": scan_errors,
    }

    run_snapshot_path = state_root / f"sharefile_snapshot_{run_id}.json"
    run_snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
    latest_snapshot_path = state_root / "sharefile_snapshot_latest.json"
    if not args.dry_run:
        latest_snapshot_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")

    print(f"snapshot={run_snapshot_path.relative_to(repo_root)}")
    if args.dry_run:
        print(f"latest=unchanged ({latest_snapshot_path.relative_to(repo_root)})")
    else:
        print(f"latest={latest_snapshot_path.relative_to(repo_root)}")
    print(
        "summary "
        f"downloaded={snapshot['downloaded_count']} "
        f"skipped={snapshot['skipped_existing_count']} "
        f"overwritten={snapshot['overwritten_count']} "
        f"failed={snapshot['failed_count']}"
    )
    return 2 if failures or scan_errors else 0


def collect_files(client: ShareFileClient) -> tuple[list[dict], list[dict], list[dict]]:
    queue = deque((root_id, root_path, 0) for root_id, root_path in DEFAULT_ROOTS)
    seen: set[str] = set()
    folders: list[dict] = []
    files: list[dict] = []
    errors: list[dict] = []

    while queue:
        folder_id, path, depth = queue.popleft()
        if folder_id in seen:
            continue
        seen.add(folder_id)

        try:
            children = client.list_children(folder_id)
        except Exception as exc:  # noqa: BLE001 - surface inaccessible folders in the snapshot.
            errors.append({"path": path, "folder_id": folder_id, "error": str(exc)})
            continue

        folders.append({"path": path, "folder_id": folder_id, "depth": depth, "children": len(children)})
        for item in children:
            item_path = f"{path}/{item.name}"
            if item.is_folder:
                queue.append((item.id, item_path, depth + 1))
                continue

            extension = Path(item.name).suffix.lower()
            if item.is_file and extension in DEFAULT_EXTENSIONS:
                files.append(
                    {
                        "remote_item_id": item.id,
                        "name": item.name,
                        "remote_path": item_path,
                        "parent_id": item.parent_id or folder_id,
                        "source_folder_path": path,
                        "source_folder_id": folder_id,
                        "extension": extension,
                        "size": item.size or 0,
                        "created_at": item.created_at,
                        "modified_at": item.modified_at,
                        "sharefile_hash": item.raw.get("Hash", "") if isinstance(item.raw, dict) else "",
                        "creator": creator_from_raw(item.raw),
                        "raw_metadata": item.raw,
                    }
                )

    return folders, files, errors


def mirror_file(
    client: ShareFileClient,
    record: dict,
    previous_snapshot: dict,
    repo_root: Path,
    inbox_root: Path,
    dry_run: bool,
) -> dict:
    previous = previous_record_for(record, previous_snapshot)
    default_local_path = local_path_for(inbox_root, record["remote_path"])
    previous_signature = file_signature(previous) if previous else {}
    current_signature = file_signature(record)
    changed_existing = bool(previous and previous_signature != current_signature)
    same_path_new_item = bool(not previous and default_local_path.exists())
    local_path = (
        next_version_path(inbox_root, record, previous_snapshot)
        if changed_existing or same_path_new_item
        else default_local_path
    )
    record["local_path"] = str(local_path.relative_to(repo_root))
    record["version_status"] = "current_version" if changed_existing or same_path_new_item else "current"
    if previous:
        record["previous_local_path"] = previous.get("local_path", "")
        record["previous_signature"] = previous_signature

    if dry_run:
        record["download_status"] = "dry_run"
        return record

    local_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        previous
        and previous_signature == current_signature
        and previous.get("local_path")
        and (repo_root / previous["local_path"]).exists()
    ):
        local_path = repo_root / previous["local_path"]
        record["local_path"] = previous["local_path"]
        record["local_size"] = local_path.stat().st_size
        record["local_sha256"] = sha256_file(local_path)
        record["download_status"] = "skipped_existing_same_metadata"
        record["version_status"] = previous.get("version_status") or "current"
        return record

    if (
        not changed_existing
        and not same_path_new_item
        and local_path.exists()
        and record["size"]
        and local_path.stat().st_size == record["size"]
    ):
        record["local_size"] = local_path.stat().st_size
        record["local_sha256"] = sha256_file(local_path)
        record["download_status"] = "skipped_existing_same_size"
        return record

    tmp_path = local_path.with_name(local_path.name + ".part")
    if tmp_path.exists():
        tmp_path.unlink()

    existed = local_path.exists()
    client.download_file(record["remote_item_id"], tmp_path)
    os.replace(tmp_path, local_path)

    record["local_size"] = local_path.stat().st_size
    record["local_sha256"] = sha256_file(local_path)
    record["download_status"] = (
        "downloaded_version" if changed_existing or same_path_new_item else ("overwritten" if existed else "downloaded")
    )
    return record


def load_previous_snapshot(state_root: Path) -> dict:
    path = state_root / "sharefile_snapshot_latest.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def previous_record_for(record: dict, previous_snapshot: dict) -> dict | None:
    remote_item_id = record.get("remote_item_id")
    for previous in previous_snapshot.get("files", []):
        if previous.get("remote_item_id") == remote_item_id and previous.get("version_status") != "superseded_local_version":
            return previous
    return None


def file_signature(record: dict | None) -> dict:
    if not record:
        return {}
    return {
        "size": record.get("size"),
        "modified_at": record.get("modified_at"),
        "sharefile_hash": record.get("sharefile_hash"),
    }


def carry_forward_superseded_versions(previous_snapshot: dict, current_records: list[dict]) -> list[dict]:
    changed_remote_ids = {
        record.get("remote_item_id")
        for record in current_records
        if record.get("version_status") == "current_version" and record.get("previous_local_path")
    }
    current_local_paths = {record.get("local_path") for record in current_records}
    carried = []
    for previous in previous_snapshot.get("files", []):
        if previous.get("remote_item_id") not in changed_remote_ids:
            continue
        if previous.get("local_path") in current_local_paths:
            continue
        row = dict(previous)
        row["version_status"] = "superseded_local_version"
        row["download_status"] = "carried_forward_superseded_version"
        carried.append(row)
    return carried


def next_version_path(inbox_root: Path, record: dict, previous_snapshot: dict) -> Path:
    base_path = local_path_for(inbox_root, record["remote_path"])
    remote_item_id = record.get("remote_item_id")
    version_number = 2
    for previous in previous_snapshot.get("files", []):
        if previous.get("remote_item_id") == remote_item_id:
            version_number = max(version_number, int(previous.get("version_number") or 1) + 1)

    while True:
        candidate = base_path.with_name(f"{base_path.stem}__v{version_number}__{timestamp_slug(record)}{base_path.suffix}")
        if not candidate.exists():
            record["version_number"] = version_number
            return candidate
        version_number += 1


def timestamp_slug(record: dict) -> str:
    value = record.get("modified_at") or datetime.now(timezone.utc).isoformat()
    return (
        value.replace(":", "")
        .replace("-", "")
        .replace(".", "")
        .replace("+", "")
        .replace("Z", "Z")
    )


def local_path_for(inbox_root: Path, remote_path: str) -> Path:
    parts = [safe_path_part(part) for part in remote_path.split("/") if part]
    return inbox_root.joinpath(*parts)


def safe_path_part(value: str) -> str:
    cleaned = value.strip().replace("\\", "_").replace("/", "_")
    cleaned = "".join("_" if ord(ch) < 32 else ch for ch in cleaned)
    return cleaned or "_unnamed"


def creator_from_raw(raw: dict) -> str:
    if not isinstance(raw, dict):
        return ""
    first = raw.get("CreatorFirstName") or ""
    last = raw.get("CreatorLastName") or ""
    short = raw.get("CreatorNameShort") or ""
    return " ".join(value for value in [first, last] if value).strip() or short


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

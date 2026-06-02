from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from django.conf import settings

from .models import Asset, AssetStatus


MIRROR_STATE_PATH = Path("data/state/file_processing_state.json")
PROFILE_PATH = Path("data/state/inbox_profile_latest.json")
SNAPSHOT_PATH = Path("data/state/sharefile_snapshot_latest.json")
SYNC_STATE_PATH = Path("data/state/sharefile_sync_state.json")
USERS_PATH = Path("data/state/sharefile_users_latest.json")
INTERNAL_WORKFLOW_FOLDERS = {"approval", "final"}


@dataclass(frozen=True)
class MirrorData:
    folders: list[dict[str, Any]]
    summary: dict[str, Any]


def load_sharefile_mirror() -> MirrorData:
    snapshot = _load_json(SNAPSHOT_PATH, default={})
    profile = _load_json(PROFILE_PATH, default={})
    processing_state = _load_json(MIRROR_STATE_PATH, default={})
    sync_state = _load_json(SYNC_STATE_PATH, default={})
    user_cache = _load_json(USERS_PATH, default={})
    assets_by_local_path = {
        asset.local_path: asset
        for asset in Asset.objects.exclude(local_path="")
    }
    assets_by_remote_item_id = {
        asset.remote_item_id: asset
        for asset in Asset.objects.exclude(remote_item_id="")
    }

    remote_by_local_path = {
        row.get("local_path"): row
        for row in snapshot.get("files", [])
        if row.get("local_path")
    }
    profile_by_local_path = {
        row.get("local_path"): row
        for row in profile.get("files", [])
        if row.get("local_path")
    }
    local_paths = set(remote_by_local_path) | set(profile_by_local_path)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for local_path in sorted(local_paths):
        remote = remote_by_local_path.get(local_path, {})
        profile_row = profile_by_local_path.get(local_path, {})
        folder_path = _folder_path_for(local_path, remote)
        if _is_internal_workflow_folder(folder_path):
            continue
        status = _file_status(
            local_path,
            remote,
            processing_state,
            assets_by_local_path,
            assets_by_remote_item_id,
        )
        remote_item_id = remote.get("remote_item_id") or ""
        asset = assets_by_remote_item_id.get(remote_item_id) or assets_by_local_path.get(local_path)
        file_row = _file_row(
            local_path,
            remote,
            profile_row,
            status,
            user_cache,
            duplicate_role=getattr(asset, "duplicate_role", "") or "",
            duplicate_group=getattr(asset, "duplicate_group", "") or "",
            is_active=getattr(asset, "is_active", True),
            asset=asset,
        )
        file_row["folder_path"] = folder_path
        file_row["folder_display_name"] = _display_folder_name(folder_path)
        grouped[folder_path].append(file_row)

    annotate_duplicate_names(grouped)

    # Ensure every folder from the snapshot appears (even if empty)
    for folder_info in snapshot.get("folders", []):
        folder_path = folder_info.get("path", "")
        if not folder_path or _is_internal_workflow_folder(folder_path):
            continue
        if folder_path not in grouped:
            grouped[folder_path] = []

    folders = []
    for folder_path, files in grouped.items():
        counts = {
            "total": len(files),
            "new": sum(1 for row in files if row["status"] == "new" and row.get("is_active", True)),
            "active": sum(1 for row in files if row["status"] == "active" and row.get("is_active", True)),
            "review": sum(1 for row in files if row["status"] == "review" and row.get("is_active", True)),
            "processed": sum(1 for row in files if row["status"] == "processed" and row.get("is_active", True)),
            "deleted": sum(1 for row in files if row["status"] == "deleted_remote"),
            "duplicate_names": duplicate_name_count(files),
        }
        folders.append(
            {
                "path": folder_path,
                "display_name": _display_folder_name(folder_path),
                "counts": counts,
                "files": newest_first(files),
            }
        )

    folders.sort(key=lambda row: (-row["counts"]["new"], row["display_name"].lower()))
    summary = {
        "run_id": snapshot.get("run_id", ""),
        "snapshot_created_at": snapshot.get("created_at", ""),
        "folder_count": len(folders),
        "file_count": sum(row["counts"]["total"] for row in folders),
        "new_count": sum(row["counts"]["new"] for row in folders),
        "active_count": sum(row["counts"]["active"] for row in folders),
        "review_count": sum(row["counts"]["review"] for row in folders),
        "processed_count": sum(row["counts"]["processed"] for row in folders),
        "deleted_count": sum(row["counts"]["deleted"] for row in folders),
        "duplicate_name_count": sum(row["counts"]["duplicate_names"] for row in folders),
        "last_sync_at": sync_state.get("finished_at") or snapshot.get("created_at", ""),
        "last_sync_status": sync_state.get("status", ""),
        "has_snapshot": bool(snapshot),
        "has_profile": bool(profile),
    }
    return MirrorData(folders=folders, summary=summary)


def _file_row(
    local_path: str,
    remote: dict[str, Any],
    profile: dict[str, Any],
    status: str,
    user_cache: dict[str, Any],
    duplicate_role: str = "",
    duplicate_group: str = "",
    is_active: bool = True,
    asset: Asset | None = None,
) -> dict[str, Any]:
    uploader = _uploader_for(remote, user_cache)
    uploaded_by = (asset.created_by_name or uploader["name"]) if asset else uploader["name"]
    uploader_email = (asset.created_by_email or uploader["email"]) if asset else uploader["email"]
    return {
        "status": status,
        "status_label": _status_label(status),
        "status_sort": {"new": 0, "active": 1, "review": 2, "processed": 3, "deleted_remote": 4}.get(status, 9),
        "review_enabled": status == "new" and is_active,
        "name": remote.get("name") or profile.get("name") or Path(local_path).name,
        "extension": remote.get("extension") or profile.get("extension") or Path(local_path).suffix.lower(),
        "size": remote.get("size") or profile.get("size") or 0,
        "created_at": remote.get("created_at") or "",
        "modified_at": remote.get("modified_at") or "",
        "modified_sort": modified_sort_value(remote.get("modified_at") or ""),
        "uploaded_by": uploaded_by,
        "uploader_email": uploader_email,
        "remote_item_id": remote.get("remote_item_id") or "",
        "remote_path": remote.get("remote_path") or "",
        "source_folder_id": remote.get("source_folder_id") or "",
        "source_folder_path": remote.get("source_folder_path") or "",
        "local_path": local_path,
        "profile_kind": profile.get("kind") or "",
        "profile_status": profile.get("status") or "",
        "sheet_count": profile.get("sheet_count"),
        "sharefile_hash": remote.get("sharefile_hash") or "",
        "duplicate_role": duplicate_role,
        "duplicate_group": duplicate_group,
        "is_active": is_active,
    }


def _file_status(
    local_path: str,
    remote: dict[str, Any],
    processing_state: dict[str, Any],
    assets_by_local_path: dict[str, Asset],
    assets_by_remote_item_id: dict[str, Asset],
) -> str:
    remote_item_id = remote.get("remote_item_id")
    processed_ids = set(processing_state.get("processed_remote_item_ids", []))
    processed_paths = set(processing_state.get("processed_local_paths", []))
    if not remote:
        return "deleted_remote"
    asset = assets_by_local_path.get(local_path) or assets_by_remote_item_id.get(remote_item_id or "")
    if asset:
        if asset.status == AssetStatus.PROCESSING:
            return "active"
        if asset.status == AssetStatus.REVIEW:
            return "review"
        if asset.status in {AssetStatus.PROCESSED, AssetStatus.UPLOADED}:
            return "processed"
    if local_path in processed_paths:
        return "processed"
    if not processed_paths and remote_item_id in processed_ids:
        return "processed"
    return "new"


def _folder_path_for(local_path: str, remote: dict[str, Any]) -> str:
    if remote.get("source_folder_path"):
        return remote["source_folder_path"]

    parts = Path(local_path).parts
    if len(parts) >= 4 and parts[0:2] == ("data", "inbox"):
        return "/".join(parts[2:-1])
    return str(Path(local_path).parent)


def _display_folder_name(folder_path: str) -> str:
    for prefix in ("home/", "allshared/"):
        if folder_path.startswith(prefix):
            return folder_path.removeprefix(prefix)
    return folder_path


def _is_internal_workflow_folder(folder_path: str) -> bool:
    normalized = folder_path.strip("/")
    for prefix in ("home/", "allshared/"):
        if normalized.casefold().startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    first_part = normalized.split("/", 1)[0].casefold()
    return first_part in INTERNAL_WORKFLOW_FOLDERS


def _status_label(status: str) -> str:
    return {
        "new": "New",
        "active": "Active",
        "review": "Review",
        "processed": "Processed",
        "deleted_remote": "Deleted",
    }.get(status, status.replace("_", " ").capitalize())


def duplicate_name_count(files: list[dict[str, Any]]) -> int:
    return sum(1 for row in files if row.get("duplicate_role") == "duplicate" and row.get("is_active", True))


def annotate_duplicate_names(grouped: dict[str, list[dict[str, Any]]]) -> None:
    # Build a name index so we can detect duplicates even when DB roles are absent.
    name_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for files in grouped.values():
        for row in files:
            key = duplicate_name_key(row.get("name", ""))
            if key:
                name_groups[key].append(row)

    # For groups with 2+ files and NO pre-existing DB roles, compute roles from
    # ShareFile created_at (earliest = original).  If ANY file in the group already
    # has a DB role we skip the snapshot-based assignment entirely and trust the DB.
    for rows in name_groups.values():
        if len(rows) < 2:
            continue
        has_db_role = any(row.get("duplicate_role") for row in rows)
        if has_db_role:
            continue
        rows.sort(key=lambda r: _created_sort(r.get("created_at", "")))
        rows[0]["duplicate_role"] = "original"
        rows[0]["duplicate_group"] = duplicate_name_key(rows[0].get("name", ""))
        for dup in rows[1:]:
            dup["duplicate_role"] = "duplicate"
            dup["duplicate_group"] = duplicate_name_key(dup.get("name", ""))

    # Set display flags and hints
    for files in grouped.values():
        for row in files:
            row["duplicate_name"] = bool(row.get("duplicate_role"))
            row["duplicate_hint"] = _duplicate_hint(row)


def _duplicate_hint(row: dict[str, Any]) -> str:
    role = row.get("duplicate_role")
    group = row.get("duplicate_group")
    if not role or not group:
        return ""
    if role == "original":
        return "Original file"
    if role == "duplicate":
        return "Duplicate copy"
    return ""


def _created_sort(value: str) -> float:
    if not value:
        return float("inf")  # files without created_at sort to the end (treated as newer)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("inf")


def duplicate_name_key(name: str) -> str:
    return " ".join(name.casefold().strip().split())


FINISHED_STATUSES = {"processed", "deleted_remote"}


def newest_first(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _sort_key(row: dict[str, Any]) -> tuple[int, float, str]:
        is_active = row.get("is_active", True)
        status = row.get("status", "")
        if not is_active:
            tier = 2
        elif status in FINISHED_STATUSES:
            tier = 1
        else:
            tier = 0
        modified_sort = row.get("modified_sort", 0)
        return (tier, -modified_sort, row.get("name", "").lower())

    return sorted(files, key=_sort_key)


def modified_sort_value(value: str) -> float:
    if not value:
        return 0
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0


def _uploader_for(remote: dict[str, Any], user_cache: dict[str, Any]) -> dict[str, str]:
    raw_metadata = remote.get("raw_metadata") if isinstance(remote.get("raw_metadata"), dict) else {}
    user_id = raw_metadata.get("LastModifiedByUserID", "")
    user = (user_cache.get("users_by_id") or {}).get(user_id, {}) if user_id else {}
    return {
        "name": user.get("full_name") or remote.get("creator") or "",
        "email": user.get("email") or "",
    }


def _load_json(relative_path: Path, default: Any) -> Any:
    path = settings.REPO_ROOT / relative_path
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


APPROVAL_FOLDER_NAMES = {"approval"}
FINAL_FOLDER_NAMES = {"final"}
APPROVAL_VERSION_PATTERN = re.compile(r"_v(\d+)(?=\.csv$)", re.IGNORECASE)


def load_approval_mirror() -> MirrorData:
    snapshot = _load_json(SNAPSHOT_PATH, default={})
    profile = _load_json(PROFILE_PATH, default={})
    sync_state = _load_json(SYNC_STATE_PATH, default={})
    user_cache = _load_json(USERS_PATH, default={})
    assets_by_local_path = {
        asset.local_path: asset
        for asset in Asset.objects.exclude(local_path="")
    }
    assets_by_remote_item_id = {
        asset.remote_item_id: asset
        for asset in Asset.objects.exclude(remote_item_id="")
    }

    remote_by_local_path = {
        row.get("local_path"): row
        for row in snapshot.get("files", [])
        if row.get("local_path")
    }
    profile_by_local_path = {
        row.get("local_path"): row
        for row in profile.get("files", [])
        if row.get("local_path")
    }
    local_paths = set(remote_by_local_path) | set(profile_by_local_path)

    month_groups: dict[tuple[int, int, str], dict[str, Any]] = {}
    file_count = 0

    for local_path in sorted(local_paths):
        remote = remote_by_local_path.get(local_path, {})
        profile_row = profile_by_local_path.get(local_path, {})
        folder_path = _folder_path_for(local_path, remote)
        month_label, vendor_name, sort_key = _approval_split_folder(folder_path)
        if not month_label or not vendor_name:
            continue

        status = _file_status(
            local_path,
            remote,
            processing_state={},
            assets_by_local_path=assets_by_local_path,
            assets_by_remote_item_id=assets_by_remote_item_id,
        )
        remote_item_id = remote.get("remote_item_id") or ""
        asset = assets_by_remote_item_id.get(remote_item_id) or assets_by_local_path.get(local_path)
        file_row = _file_row(
            local_path,
            remote,
            profile_row,
            status,
            user_cache,
            asset=asset,
        )
        file_row["month_label"] = month_label
        file_row["vendor_name"] = vendor_name
        file_row["version"] = _extract_version(file_row.get("name", ""))
        file_row["exists_locally"] = (settings.REPO_ROOT / local_path).exists()

        month_entry = month_groups.setdefault(
            sort_key,
            {
                "label": month_label,
                "year": sort_key[0],
                "month": sort_key[1],
                "sort_key": sort_key,
                "vendors": {},
            },
        )
        vendor_entry = month_entry["vendors"].setdefault(
            vendor_name.casefold(),
            {
                "name": vendor_name,
                "files": [],
            },
        )
        vendor_entry["files"].append(file_row)
        file_count += 1

    months: list[dict[str, Any]] = []
    vendor_count = 0
    for sort_key in sorted(month_groups.keys(), reverse=True):
        entry = month_groups[sort_key]
        vendor_list = sorted(entry["vendors"].values(), key=lambda v: v["name"].casefold())
        for vendor in vendor_list:
            vendor["files"] = newest_first(vendor["files"])
            vendor["file_count"] = len(vendor["files"])
            vendor_count += 1
        entry["vendors"] = vendor_list
        entry["vendor_count"] = len(vendor_list)
        entry["file_count"] = sum(v["file_count"] for v in vendor_list)
        months.append(entry)

    summary = {
        "run_id": snapshot.get("run_id", ""),
        "snapshot_created_at": snapshot.get("created_at", ""),
        "month_count": len(months),
        "vendor_count": vendor_count,
        "file_count": file_count,
        "last_sync_at": sync_state.get("finished_at") or snapshot.get("created_at", ""),
        "last_sync_status": sync_state.get("status", ""),
        "has_snapshot": bool(snapshot),
    }
    return MirrorData(folders=months, summary=summary)


def load_final_mirror() -> MirrorData:
    snapshot = _load_json(SNAPSHOT_PATH, default={})
    profile = _load_json(PROFILE_PATH, default={})
    sync_state = _load_json(SYNC_STATE_PATH, default={})
    user_cache = _load_json(USERS_PATH, default={})
    assets_by_local_path = {
        asset.local_path: asset
        for asset in Asset.objects.exclude(local_path="")
    }
    assets_by_remote_item_id = {
        asset.remote_item_id: asset
        for asset in Asset.objects.exclude(remote_item_id="")
    }

    remote_by_local_path = {
        row.get("local_path"): row
        for row in snapshot.get("files", [])
        if row.get("local_path")
    }
    profile_by_local_path = {
        row.get("local_path"): row
        for row in profile.get("files", [])
        if row.get("local_path")
    }
    local_paths = set(remote_by_local_path) | set(profile_by_local_path)

    month_groups: dict[tuple[int, int, str], dict[str, Any]] = {}
    file_count = 0

    for local_path in sorted(local_paths):
        remote = remote_by_local_path.get(local_path, {})
        profile_row = profile_by_local_path.get(local_path, {})
        folder_path = _folder_path_for(local_path, remote)
        file_name = remote.get("name") or profile_row.get("name") or Path(local_path).name
        month_label, vendor_name, sort_key = _final_split_folder(folder_path, file_name)
        if not month_label or not vendor_name:
            continue

        status = _file_status(
            local_path,
            remote,
            processing_state={},
            assets_by_local_path=assets_by_local_path,
            assets_by_remote_item_id=assets_by_remote_item_id,
        )
        remote_item_id = remote.get("remote_item_id") or ""
        asset = assets_by_remote_item_id.get(remote_item_id) or assets_by_local_path.get(local_path)
        file_row = _file_row(
            local_path,
            remote,
            profile_row,
            status,
            user_cache,
            asset=asset,
        )
        file_row["month_label"] = month_label
        file_row["vendor_name"] = vendor_name
        file_row["version"] = _extract_version(file_row.get("name", ""))
        file_row["exists_locally"] = (settings.REPO_ROOT / local_path).exists()

        month_entry = month_groups.setdefault(
            sort_key,
            {
                "label": month_label,
                "year": sort_key[0],
                "month": sort_key[1],
                "sort_key": sort_key,
                "vendors": {},
            },
        )
        vendor_entry = month_entry["vendors"].setdefault(
            vendor_name.casefold(),
            {
                "name": vendor_name,
                "files": [],
            },
        )
        vendor_entry["files"].append(file_row)
        file_count += 1

    months: list[dict[str, Any]] = []
    vendor_count = 0
    for sort_key in sorted(month_groups.keys(), reverse=True):
        entry = month_groups[sort_key]
        vendor_list = sorted(entry["vendors"].values(), key=lambda v: v["name"].casefold())
        for vendor in vendor_list:
            vendor["files"] = newest_first(vendor["files"])
            vendor["file_count"] = len(vendor["files"])
            vendor_count += 1
        entry["vendors"] = vendor_list
        entry["vendor_count"] = len(vendor_list)
        entry["file_count"] = sum(v["file_count"] for v in vendor_list)
        months.append(entry)

    summary = {
        "run_id": snapshot.get("run_id", ""),
        "snapshot_created_at": snapshot.get("created_at", ""),
        "month_count": len(months),
        "vendor_count": vendor_count,
        "file_count": file_count,
        "last_sync_at": sync_state.get("finished_at") or snapshot.get("created_at", ""),
        "last_sync_status": sync_state.get("status", ""),
        "has_snapshot": bool(snapshot),
    }
    return MirrorData(folders=months, summary=summary)


def _approval_split_folder(folder_path: str) -> tuple[str, str, tuple[int, int, str]]:
    normalized = (folder_path or "").strip().strip("/")
    for prefix in ("home/", "allshared/"):
        if normalized.casefold().startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    parts = [part for part in normalized.split("/") if part]
    if len(parts) < 3:
        return "", "", (0, 0, "")
    first = parts[0].casefold()
    if first not in APPROVAL_FOLDER_NAMES:
        return "", "", (0, 0, "")
    month_label = parts[1]
    vendor_name = parts[2]
    year, month = _parse_period_label(month_label)
    if not year or not month:
        return "", "", (0, 0, "")
    return month_label, vendor_name, (year, month, month_label)


def _final_split_folder(folder_path: str, file_name: str = "") -> tuple[str, str, tuple[int, int, str]]:
    normalized = (folder_path or "").strip().strip("/")
    for prefix in ("home/", "allshared/"):
        if normalized.casefold().startswith(prefix):
            normalized = normalized[len(prefix):]
            break
    parts = [part for part in normalized.split("/") if part]
    if len(parts) < 2:
        return "", "", (0, 0, "")
    first = parts[0].casefold()
    if first not in FINAL_FOLDER_NAMES:
        return "", "", (0, 0, "")
    month_label = parts[1]
    year, month = _parse_period_label(month_label)
    if not year or not month:
        return "", "", (0, 0, "")
    # Final files may sit directly in Final/<month>/ (no vendor subfolder).
    # In that case, derive the vendor from the filename: <Vendor>_<Month>_<Year>.csv
    if len(parts) >= 3:
        vendor_name = parts[2]
    else:
        stem = (file_name or "").rsplit(".", 1)[0]
        vendor_name = stem.replace(month_label, "").strip("_") if stem else ""
    return month_label, vendor_name, (year, month, month_label)


def _parse_period_label(label: str) -> tuple[int, int]:
    text = (label or "").strip().replace("-", "_")
    for separator in ("_", " "):
        parts = [p for p in text.split(separator) if p]
        if len(parts) != 2:
            continue
        first, second = parts
        if first.isdigit() and not second.isdigit():
            year = int(first)
            month_number = _month_number(second)
            if month_number:
                return year, month_number
        if second.isdigit() and not first.isdigit():
            year = int(second)
            month_number = _month_number(first)
            if month_number:
                return year, month_number
    return 0, 0


_MONTH_NAME_TO_NUMBER = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}


def _month_number(value: str) -> int:
    return _MONTH_NAME_TO_NUMBER.get(value.strip().casefold(), 0)


def _extract_version(name: str) -> int:
    if not name:
        return 1
    match = APPROVAL_VERSION_PATTERN.search(name)
    if not match:
        return 1
    try:
        return max(int(match.group(1)), 1)
    except (TypeError, ValueError):
        return 1

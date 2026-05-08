from __future__ import annotations

import json
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
        grouped[folder_path].append(_file_row(local_path, remote, profile_row, status, user_cache))

    folders = []
    for folder_path, files in grouped.items():
        counts = {
            "total": len(files),
            "new": sum(1 for row in files if row["status"] == "new"),
            "active": sum(1 for row in files if row["status"] == "active"),
            "review": sum(1 for row in files if row["status"] == "review"),
            "processed": sum(1 for row in files if row["status"] == "processed"),
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

    folders.sort(key=lambda row: (-row["counts"]["total"], row["display_name"].lower()))
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
) -> dict[str, Any]:
    uploader = _uploader_for(remote, user_cache)
    return {
        "status": status,
        "status_label": _status_label(status),
        "status_sort": {"new": 0, "active": 1, "review": 2, "processed": 3, "deleted_remote": 4}.get(status, 9),
        "review_enabled": status == "new",
        "name": remote.get("name") or profile.get("name") or Path(local_path).name,
        "extension": remote.get("extension") or profile.get("extension") or Path(local_path).suffix.lower(),
        "size": remote.get("size") or profile.get("size") or 0,
        "created_at": remote.get("created_at") or "",
        "modified_at": remote.get("modified_at") or "",
        "modified_sort": modified_sort_value(remote.get("modified_at") or ""),
        "uploaded_by": uploader["name"],
        "uploader_email": uploader["email"],
        "remote_item_id": remote.get("remote_item_id") or "",
        "remote_path": remote.get("remote_path") or "",
        "source_folder_id": remote.get("source_folder_id") or "",
        "source_folder_path": remote.get("source_folder_path") or "",
        "local_path": local_path,
        "profile_kind": profile.get("kind") or "",
        "profile_status": profile.get("status") or "",
        "sheet_count": profile.get("sheet_count"),
        "sharefile_hash": remote.get("sharefile_hash") or "",
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
        "new": "N",
        "active": "A",
        "review": "R",
        "processed": "P",
        "deleted_remote": "D",
    }.get(status, status[:1].upper())


def duplicate_name_count(files: list[dict[str, Any]]) -> int:
    counts: defaultdict[str, int] = defaultdict(int)
    for row in files:
        counts[row["name"].lower()] += 1
    return sum(count for count in counts.values() if count > 1)


def newest_first(files: list[dict[str, Any]]) -> list[dict[str, Any]]:
    named = sorted(files, key=lambda row: row["name"].lower())
    return sorted(named, key=lambda row: row["modified_sort"], reverse=True)


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

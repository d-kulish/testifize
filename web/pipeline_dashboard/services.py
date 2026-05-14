from __future__ import annotations

from datetime import timezone as datetime_timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Protocol

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from testifize_pipeline.config import load_dotenv
from testifize_pipeline.sharefile import ShareFileClient, ShareFileConfig, ShareFileItem

from .models import Asset, AssetEvent, AssetStatus, ShareFileFolder


class ShareFileListClient(Protocol):
    def list_children(self, folder_id: str) -> list[ShareFileItem]:
        ...


class ShareFileDownloadClient(Protocol):
    def download_file(self, item_id: str, destination: Path) -> Path:
        ...


def build_sharefile_client() -> ShareFileClient:
    env = load_dotenv(settings.REPO_ROOT / ".env")
    client = ShareFileClient(ShareFileConfig.from_env(env))
    client.authenticate()
    return client


def scan_folder(folder: ShareFileFolder, client: ShareFileListClient | None = None) -> int:
    client = client or build_sharefile_client()
    matched = 0
    for item in client.list_children(folder.folder_id):
        if item.is_folder or not _matches_any(item.name, folder.effective_file_patterns()):
            continue
        matched += 1
        upsert_asset_from_item(folder, item)
    return matched


@transaction.atomic
def upsert_asset_from_item(folder: ShareFileFolder, item: ShareFileItem) -> Asset:
    now = timezone.now()
    existing = Asset.objects.filter(remote_item_id=item.id).first()
    status = existing.status if existing else AssetStatus.NEW
    if existing and item.modified_at and existing.remote_modified_at != _parse_dt(item.modified_at):
        status = AssetStatus.NEW

    defaults = {
        "vendor": folder.vendor,
        "source_folder": folder,
        "status": status,
        "name": item.name,
        "sharefile_folder_id": folder.folder_id,
        "source_folder_label": folder.label,
        "remote_path": f"{folder.label}/{item.name}",
        "file_size": item.size,
        "remote_created_at": _parse_dt(item.created_at),
        "remote_modified_at": _parse_dt(item.modified_at),
        "created_by_name": item.created_by_name or "",
        "created_by_email": item.created_by_email or "",
        "parser_key": folder.vendor.parser_key if folder.vendor else "",
        "duplicate_group": " ".join(item.name.casefold().strip().split()),
        "last_seen_at": now,
        "raw_metadata": item.raw,
    }

    if existing:
        previous_status = existing.status
        previous_modified = existing.remote_modified_at
        for field, value in defaults.items():
            setattr(existing, field, value)
        existing.save()
        if previous_modified != existing.remote_modified_at:
            record_asset_event(
                existing,
                "rediscovered",
                from_status=previous_status,
                to_status=existing.status,
                message="Remote metadata changed during scan",
            )
        _reconcile_duplicate_roles_for_group(existing.duplicate_group)
        return existing

    asset = Asset.objects.create(remote_item_id=item.id, first_seen_at=now, **defaults)
    record_asset_event(asset, "discovered", to_status=asset.status, message="New remote asset discovered")
    _reconcile_duplicate_roles_for_group(asset.duplicate_group)
    return asset


def _reconcile_duplicate_roles_for_group(duplicate_group: str | None) -> None:
    if not duplicate_group:
        return
    assets = list(
        Asset.objects.filter(duplicate_group=duplicate_group)
        .exclude(duplicate_group="")
        .order_by("remote_created_at", "first_seen_at", "remote_item_id")
    )
    if len(assets) < 2:
        # Only one asset in this group — clear any stale role
        for asset in assets:
            if asset.duplicate_role:
                asset.duplicate_role = ""
                asset.save(update_fields=["duplicate_role", "updated_at"])
        return
    original = assets[0]
    if original.duplicate_role != "original":
        original.duplicate_role = "original"
        original.save(update_fields=["duplicate_role", "updated_at"])
    for dup in assets[1:]:
        if dup.duplicate_role != "duplicate":
            dup.duplicate_role = "duplicate"
            dup.save(update_fields=["duplicate_role", "updated_at"])
def download_asset(asset: Asset, client: ShareFileDownloadClient | None = None) -> Path:
    client = client or build_sharefile_client()
    destination = inbox_path_for_asset(asset)
    set_asset_status(asset, AssetStatus.DOWNLOADING, "Download started")
    try:
        client.download_file(asset.remote_item_id, destination)
    except Exception as exc:
        set_asset_status(asset, AssetStatus.FAILED, f"Download failed: {exc}")
        raise
    asset.local_path = str(destination)
    asset.save(update_fields=["local_path", "updated_at"])
    set_asset_status(asset, AssetStatus.DOWNLOADED, "Download completed")
    return destination


def inbox_path_for_asset(asset: Asset) -> Path:
    vendor_slug = _safe_path_part(asset.vendor.name if asset.vendor else "unassigned")
    return Path(settings.INBOX_ROOT) / vendor_slug / asset.remote_item_id / asset.name


def set_asset_status(asset: Asset, status: str, message: str = "") -> None:
    old_status = asset.status
    asset.status = status
    asset.save(update_fields=["status", "updated_at"])
    record_asset_event(asset, "status", from_status=old_status, to_status=status, message=message)


def record_asset_event(
    asset: Asset,
    event_type: str,
    from_status: str = "",
    to_status: str = "",
    message: str = "",
    metadata: dict | None = None,
) -> AssetEvent:
    return AssetEvent.objects.create(
        asset=asset,
        event_type=event_type,
        from_status=from_status or "",
        to_status=to_status or "",
        message=message,
        metadata=metadata or {},
    )


def _matches_any(name: str, patterns: list[str]) -> bool:
    return any(fnmatch(name.lower(), pattern.lower()) for pattern in patterns)


def _parse_dt(value: str | None):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed and timezone.is_naive(parsed):
        return timezone.make_aware(parsed, datetime_timezone.utc)
    return parsed


def _safe_path_part(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value.strip())
    return cleaned or "unassigned"

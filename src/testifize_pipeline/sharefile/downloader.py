from __future__ import annotations

from pathlib import Path

from testifize_pipeline.assets import AssetCatalog, AssetStatus
from testifize_pipeline.sharefile.client import ShareFileClient


def download_asset(
    client: ShareFileClient,
    catalog: AssetCatalog,
    remote_item_id: str,
    destination_root: Path,
) -> Path:
    record = catalog.get(remote_item_id)
    if not record:
        raise KeyError(f"Unknown asset: {remote_item_id}")

    vendor = record.vendor or "_unknown"
    destination = destination_root / vendor / remote_item_id / record.name
    catalog.set_status(remote_item_id, AssetStatus.DOWNLOADING, "Download started")
    try:
        client.download_file(remote_item_id, destination)
    except Exception as exc:
        catalog.set_status(remote_item_id, AssetStatus.FAILED, f"Download failed: {exc}")
        raise
    catalog.set_status(
        remote_item_id,
        AssetStatus.DOWNLOADED,
        "Download completed",
        local_path=str(destination),
    )
    return destination

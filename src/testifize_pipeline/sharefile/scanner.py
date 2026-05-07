from __future__ import annotations

from fnmatch import fnmatch

from testifize_pipeline.assets import AssetCatalog
from testifize_pipeline.config import VendorFolder
from testifize_pipeline.sharefile.client import ShareFileClient, ShareFileItem


def scan_vendor_folder(
    client: ShareFileClient,
    catalog: AssetCatalog,
    folder: VendorFolder,
) -> list[ShareFileItem]:
    children = client.list_children(folder.input_folder_id)
    matched: list[ShareFileItem] = []
    for item in children:
        if item.is_folder:
            continue
        if not _matches_any(item.name, folder.file_patterns):
            continue
        matched.append(item)
        catalog.upsert_discovered(
            remote_item_id=item.id,
            name=item.name,
            vendor=folder.vendor,
            source_folder_id=folder.input_folder_id,
            source_folder_label=folder.folder_label,
            remote_path=f"{folder.folder_label or folder.input_folder_id}/{item.name}",
            file_size=item.size,
            remote_created_at=item.created_at,
            remote_modified_at=item.modified_at,
            created_by_name=item.created_by_name,
            created_by_email=item.created_by_email,
            raw_metadata=item.raw,
            parser=folder.parser,
        )
    return matched


def _matches_any(name: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(name.lower(), pattern.lower()) for pattern in patterns)

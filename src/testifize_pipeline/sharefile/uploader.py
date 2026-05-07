from __future__ import annotations

from pathlib import Path

from testifize_pipeline.sharefile.client import ShareFileClient, ShareFileItem


def upload_file(
    client: ShareFileClient,
    folder_id: str,
    path: Path,
    content_type: str = "application/octet-stream",
    notify: bool = False,
    overwrite: bool = False,
) -> ShareFileItem:
    return client.upload_bytes(
        folder_id=folder_id,
        filename=path.name,
        content=path.read_bytes(),
        content_type=content_type,
        notify=notify,
        overwrite=overwrite,
    )

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from testifize_pipeline.assets import AssetCatalog
from testifize_pipeline.config import PROJECT_ROOT, load_dotenv, load_vendor_folders
from testifize_pipeline.sharefile import ShareFileClient, ShareFileConfig
from testifize_pipeline.sharefile.scanner import scan_vendor_folder


DEFAULT_CATALOG = PROJECT_ROOT / "data" / "state" / "asset_catalog.sqlite"
DEFAULT_FOLDER_CONFIG = PROJECT_ROOT / "config" / "sharefile_folders.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Testifize ShareFile vendor pipeline")
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="Scan configured ShareFile folders into the asset catalogue")
    scan_parser.add_argument("--folders", type=Path, default=DEFAULT_FOLDER_CONFIG)

    list_parser = subparsers.add_parser("assets", help="List locally catalogued assets")
    list_parser.add_argument("--vendor")
    list_parser.add_argument("--status")
    list_parser.add_argument("--json", action="store_true")

    upload_parser = subparsers.add_parser("upload-test", help="Upload a tiny CSV into a ShareFile folder")
    upload_parser.add_argument("--folder-id", required=True)

    args = parser.parse_args(argv)
    catalog = AssetCatalog(args.catalog)

    if args.command == "scan":
        client = build_client()
        folders = load_vendor_folders(args.folders)
        total = 0
        for folder in folders:
            matched = scan_vendor_folder(client, catalog, folder)
            total += len(matched)
            print(f"{folder.vendor}: {len(matched)} matching files")
        print(f"catalogued={total}")
        return 0

    if args.command == "assets":
        records = catalog.list_assets(vendor=args.vendor, status=args.status)
        if args.json:
            print(json.dumps([record.__dict__ for record in records], indent=2, sort_keys=True))
        else:
            writer = csv.writer(_Stdout())
            writer.writerow(["status", "vendor", "name", "remote_item_id", "modified", "created_by"])
            for record in records:
                writer.writerow(
                    [
                        record.status,
                        record.vendor or "",
                        record.name,
                        record.remote_item_id,
                        record.remote_modified_at or "",
                        record.created_by_name or record.created_by_email or "",
                    ]
                )
        return 0

    if args.command == "upload-test":
        client = build_client()
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"testifize_upload_probe_{timestamp}.csv"
        content = f"source,status,created_utc\ncli,ok,{timestamp}\n".encode("utf-8")
        item = client.upload_bytes(args.folder_id, filename, content, content_type="text/csv")
        print(f"uploaded name={item.name} id={item.id} size={item.size}")
        return 0

    raise AssertionError(f"Unhandled command: {args.command}")


def build_client() -> ShareFileClient:
    env = load_dotenv()
    client = ShareFileClient(ShareFileConfig.from_env(env))
    client.authenticate()
    return client


class _Stdout:
    def write(self, value: str) -> int:
        print(value, end="")
        return len(value)

    def flush(self) -> None:
        return None


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import TestCase, override_settings
from django.utils import timezone

from pipeline_dashboard.models import Asset, AssetEvent, AssetStatus, ShareFileFolder, Vendor
from pipeline_dashboard.services import download_asset, scan_folder, set_asset_status
from testifize_pipeline.sharefile import ShareFileItem


class FakeListClient:
    def __init__(self, items):
        self.items = items

    def list_children(self, folder_id):
        return self.items


class FakeDownloadClient:
    def download_file(self, item_id, destination: Path):
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text("ok")
        return destination


def sharefile_item(item_id="fi-example", name="report.xlsx", modified_at="2026-05-07T10:00:00Z"):
    return ShareFileItem(
        id=item_id,
        name=name,
        kind="ShareFile.Api.Models.File",
        parent_id="fo-example",
        size=42,
        created_at="2026-05-07T09:00:00Z",
        modified_at=modified_at,
        created_by_name="Data Team",
        created_by_email="svc.sfdataccess@ptytechnologies.com",
        raw={"Id": item_id, "Name": name},
    )


class ServiceTests(TestCase):
    def setUp(self):
        self.vendor, _ = Vendor.objects.get_or_create(name="AdTaxi", defaults={"parser_key": "adtaxi"})
        self.folder = ShareFileFolder.objects.create(
            vendor=self.vendor,
            folder_id="fo-example",
            label="Shared Folders/AdTaxi",
            file_patterns=["*.xlsx"],
        )

    def test_scan_folder_upserts_asset_and_preserves_first_seen(self):
        client = FakeListClient([sharefile_item()])

        self.assertEqual(scan_folder(self.folder, client=client), 1)
        asset = Asset.objects.get(remote_item_id="fi-example")
        first_seen = asset.first_seen_at

        self.assertEqual(asset.vendor, self.vendor)
        self.assertEqual(asset.parser_key, "adtaxi")
        self.assertEqual(asset.status, AssetStatus.NEW)
        self.assertEqual(asset.events.count(), 1)

        self.assertEqual(scan_folder(self.folder, client=client), 1)
        asset.refresh_from_db()
        self.assertEqual(asset.first_seen_at, first_seen)
        self.assertGreaterEqual(asset.last_seen_at, first_seen)

    def test_scan_folder_remote_change_keeps_first_seen_and_records_event(self):
        scan_folder(self.folder, client=FakeListClient([sharefile_item(modified_at="2026-05-07T10:00:00Z")]))
        asset = Asset.objects.get(remote_item_id="fi-example")
        first_seen = asset.first_seen_at

        scan_folder(self.folder, client=FakeListClient([sharefile_item(modified_at="2026-05-08T10:00:00Z")]))
        asset.refresh_from_db()

        self.assertEqual(asset.first_seen_at, first_seen)
        self.assertEqual(asset.status, AssetStatus.NEW)
        self.assertEqual(asset.events.filter(event_type="rediscovered").count(), 1)

    def test_set_asset_status_creates_event(self):
        asset = Asset.objects.create(remote_item_id="fi-example", name="report.xlsx", status=AssetStatus.NEW)

        set_asset_status(asset, AssetStatus.QUEUED, "Ready for download")
        asset.refresh_from_db()

        self.assertEqual(asset.status, AssetStatus.QUEUED)
        event = AssetEvent.objects.get(asset=asset)
        self.assertEqual(event.from_status, AssetStatus.NEW)
        self.assertEqual(event.to_status, AssetStatus.QUEUED)

    def test_download_asset_writes_to_vendor_item_path_and_updates_status(self):
        asset = Asset.objects.create(
            remote_item_id="fi-example",
            vendor=self.vendor,
            name="report.xlsx",
            status=AssetStatus.NEW,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with override_settings(INBOX_ROOT=Path(tmpdir)):
                destination = download_asset(asset, client=FakeDownloadClient())

        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.DOWNLOADED)
        self.assertTrue(asset.local_path.endswith("AdTaxi/fi-example/report.xlsx"))
        self.assertEqual(destination.name, "report.xlsx")
        self.assertEqual(asset.events.filter(event_type="status").count(), 2)

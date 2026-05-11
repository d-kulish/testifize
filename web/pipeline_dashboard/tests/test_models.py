from __future__ import annotations

from django.test import TestCase

from pipeline_dashboard.models import Asset, AssetStatus, ShareFileFolder, Vendor


class ModelTests(TestCase):
    def test_vendor_folder_and_asset_creation(self):
        vendor, _ = Vendor.objects.get_or_create(name="AdTaxi", defaults={"parser_key": "adtaxi"})
        folder = ShareFileFolder.objects.create(
            vendor=vendor,
            folder_id="fo-example",
            label="Shared Folders/AdTaxi",
            file_patterns=["*.xlsx"],
        )
        asset = Asset.objects.create(
            remote_item_id="fi-example",
            vendor=vendor,
            source_folder=folder,
            status=AssetStatus.NEW,
            name="report.xlsx",
        )

        self.assertEqual(str(vendor), "AdTaxi")
        self.assertEqual(str(folder), "Shared Folders/AdTaxi")
        self.assertEqual(str(asset), "report.xlsx")
        self.assertIn((AssetStatus.NEW, "New"), AssetStatus.choices)

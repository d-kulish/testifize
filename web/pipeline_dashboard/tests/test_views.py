from __future__ import annotations

from django.test import TestCase
from django.urls import reverse

from pipeline_dashboard.models import Asset, AssetStatus, ShareFileFolder, Vendor


class DashboardViewTests(TestCase):
    def test_dashboard_renders_with_empty_state(self):
        response = self.client.get(reverse("pipeline_dashboard:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pipeline Dashboard")
        self.assertContains(response, "No assets need review yet")

    def test_dashboard_renders_catalogue_data(self):
        vendor = Vendor.objects.create(name="AdTaxi", parser_key="adtaxi")
        folder = ShareFileFolder.objects.create(
            vendor=vendor,
            folder_id="fo-example",
            label="Shared Folders/AdTaxi",
            file_patterns=["*.xlsx"],
        )
        Asset.objects.create(
            remote_item_id="fi-example",
            vendor=vendor,
            source_folder=folder,
            status=AssetStatus.NEW,
            name="AdTaxi report.xlsx",
        )

        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "AdTaxi report.xlsx")
        self.assertContains(response, "AdTaxi")

    def test_assets_page_renders_catalogue_data(self):
        vendor = Vendor.objects.create(name="AdTaxi", parser_key="adtaxi")
        folder = ShareFileFolder.objects.create(
            vendor=vendor,
            folder_id="fo-example",
            label="Shared Folders/AdTaxi",
        )
        Asset.objects.create(
            remote_item_id="fi-example",
            vendor=vendor,
            source_folder=folder,
            status=AssetStatus.NEW,
            name="AdTaxi report.xlsx",
            created_by_name="Vendor User",
        )

        response = self.client.get(reverse("pipeline_dashboard:assets"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Asset List")
        self.assertContains(response, "AdTaxi report.xlsx")
        self.assertContains(response, "Vendor User")

    def test_assets_page_filters_by_status(self):
        Asset.objects.create(
            remote_item_id="fi-new",
            status=AssetStatus.NEW,
            name="new.xlsx",
        )
        Asset.objects.create(
            remote_item_id="fi-ignored",
            status=AssetStatus.IGNORED,
            name="ignored.xlsx",
        )

        response = self.client.get(reverse("pipeline_dashboard:assets"), {"status": AssetStatus.NEW})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "new.xlsx")
        self.assertNotContains(response, "ignored.xlsx")

    def test_folders_page_renders_configured_folders(self):
        vendor = Vendor.objects.create(name="AdTaxi", parser_key="adtaxi")
        ShareFileFolder.objects.create(
            vendor=vendor,
            folder_id="fo-example",
            label="Shared Folders/AdTaxi",
            file_patterns=["*.xlsx"],
        )

        response = self.client.get(reverse("pipeline_dashboard:folders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Configured Folders")
        self.assertContains(response, "Shared Folders/AdTaxi")
        self.assertContains(response, "AdTaxi")

    def test_vendors_page_renders_vendor_data(self):
        Vendor.objects.create(name="AdTaxi", parser_key="adtaxi", notes="Daily media exports")

        response = self.client.get(reverse("pipeline_dashboard:vendors"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vendor List")
        self.assertContains(response, "AdTaxi")
        self.assertContains(response, "adtaxi")

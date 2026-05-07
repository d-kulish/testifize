from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import TestCase, override_settings
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

    def test_folders_page_renders_sharefile_mirror(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            state_root = repo_root / "data" / "state"
            state_root.mkdir(parents=True)
            (state_root / "sharefile_snapshot_latest.json").write_text(
                json.dumps(
                    {
                        "run_id": "snapshot-1",
                        "created_at": "2026-05-07T10:00:00Z",
                        "files": [
                            {
                                "remote_item_id": "fi-new",
                                "name": "z-new.xlsx",
                                "remote_path": "home/josh/z-new.xlsx",
                                "local_path": "data/inbox/home/josh/z-new.xlsx",
                                "source_folder_path": "home/josh",
                                "extension": ".xlsx",
                                "size": 10,
                                "modified_at": "2026-05-07T12:00:00Z",
                                "creator": "Uploader One",
                                "raw_metadata": {"LastModifiedByUserID": "user-1"},
                            },
                            {
                                "remote_item_id": "fi-processed",
                                "name": "a-processed.csv",
                                "remote_path": "home/josh/a-processed.csv",
                                "local_path": "data/inbox/home/josh/a-processed.csv",
                                "source_folder_path": "home/josh",
                                "extension": ".csv",
                                "size": 20,
                                "modified_at": "2026-05-06T12:00:00Z",
                                "creator": "Uploader Two",
                                "raw_metadata": {"LastModifiedByUserID": "user-2"},
                            },
                        ],
                    }
                )
            )
            (state_root / "inbox_profile_latest.json").write_text(
                json.dumps(
                    {
                        "files": [
                            {
                                "local_path": "data/inbox/home/josh/z-new.xlsx",
                                "name": "z-new.xlsx",
                                "kind": "excel",
                                "status": "profiled",
                                "sheet_count": 1,
                            },
                            {
                                "local_path": "data/inbox/home/josh/a-processed.csv",
                                "name": "a-processed.csv",
                                "kind": "csv",
                                "status": "profiled",
                            },
                            {
                                "local_path": "data/inbox/home/josh/deleted.xlsx",
                                "name": "deleted.xlsx",
                                "kind": "excel",
                                "status": "profiled",
                                "sheet_count": 2,
                            },
                        ]
                    }
                )
            )
            (state_root / "file_processing_state.json").write_text(
                json.dumps({"processed_local_paths": ["data/inbox/home/josh/a-processed.csv"]})
            )
            (state_root / "sharefile_users_latest.json").write_text(
                json.dumps(
                    {
                        "users_by_id": {
                            "user-1": {"full_name": "Uploader One", "email": "one@example.com"},
                            "user-2": {"full_name": "Uploader Two", "email": "two@example.com"},
                        }
                    }
                )
            )
            (state_root / "sharefile_sync_state.json").write_text(
                json.dumps({"status": "success", "finished_at": "2026-05-07T12:00:00+00:00"})
            )

            with override_settings(REPO_ROOT=repo_root):
                response = self.client.get(reverse("pipeline_dashboard:folders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loaded Folders")
        self.assertContains(response, "josh")
        self.assertContains(response, "z-new.xlsx")
        self.assertContains(response, "a-processed.csv")
        self.assertContains(response, "deleted.xlsx")
        self.assertContains(response, "Uploader")
        self.assertContains(response, "Mail")
        self.assertContains(response, "Last Sync")
        self.assertContains(response, "Uploader One")
        self.assertContains(response, "Uploader Two")
        self.assertContains(response, "one@example.com")
        self.assertContains(response, "two@example.com")
        self.assertContains(response, 'data-page-size="10"')
        self.assertContains(response, "Prev")
        self.assertContains(response, "Next")
        self.assertLess(response.content.decode().index("z-new.xlsx"), response.content.decode().index("a-processed.csv"))
        self.assertContains(response, ">N<", html=False)
        self.assertContains(response, ">P<", html=False)
        self.assertContains(response, ">D<", html=False)
        self.assertContains(response, "Deleted in SF")

    @patch("pipeline_dashboard.views.subprocess.run")
    def test_update_folders_runs_update_script(self, run_mock):
        run_mock.return_value.returncode = 0
        run_mock.return_value.stdout = "ok"
        run_mock.return_value.stderr = ""

        response = self.client.post(reverse("pipeline_dashboard:update_folders"))

        self.assertRedirects(response, reverse("pipeline_dashboard:folders"))
        run_mock.assert_called_once()

    def test_vendors_page_renders_vendor_data(self):
        Vendor.objects.create(name="AdTaxi", parser_key="adtaxi", notes="Daily media exports")

        response = self.client.get(reverse("pipeline_dashboard:vendors"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Vendor List")
        self.assertContains(response, "AdTaxi")
        self.assertContains(response, "adtaxi")

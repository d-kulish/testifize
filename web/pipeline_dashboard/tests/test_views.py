from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.urls import reverse
from openpyxl import Workbook

from pipeline_dashboard.models import Asset, AssetStatus, ParsedOutput, ShareFileFolder, Vendor
from pipeline_dashboard.parser_workflow import approval_root_id


class FakeApprovalClient:
    def __init__(self):
        from datetime import datetime

        self.current_month = datetime.now().strftime("%B_%Y")
        self.folder_parts = []
        self.uploaded_name = ""

    def ensure_folder_path(self, root_id, parts):
        self.root_id = root_id
        self.folder_parts = parts
        return SimpleNamespace(id="fo-approval")

    def upload_bytes(self, folder_id, filename, content, content_type, notify, overwrite):
        self.folder_id = folder_id
        self.uploaded_name = filename
        self.uploaded_content = content
        return SimpleNamespace(id="fi-uploaded", name=filename)


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
                            {
                                "remote_item_id": "fi-active",
                                "name": "m-active.csv",
                                "remote_path": "home/josh/m-active.csv",
                                "local_path": "data/inbox/home/josh/m-active.csv",
                                "source_folder_path": "home/josh",
                                "source_folder_id": "fo-josh",
                                "extension": ".csv",
                                "size": 30,
                                "modified_at": "2026-05-05T12:00:00Z",
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
                                "local_path": "data/inbox/home/josh/m-active.csv",
                                "name": "m-active.csv",
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
            Asset.objects.create(
                remote_item_id="fi-active",
                status=AssetStatus.PROCESSING,
                name="m-active.csv",
                local_path="data/inbox/home/josh/m-active.csv",
            )

            with override_settings(REPO_ROOT=repo_root):
                response = self.client.get(reverse("pipeline_dashboard:folders"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Loaded Folders")
        self.assertContains(response, "josh")
        self.assertContains(response, "z-new.xlsx")
        self.assertContains(response, "a-processed.csv")
        self.assertContains(response, "m-active.csv")
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
        self.assertContains(response, ">A<", html=False)
        self.assertContains(response, ">P<", html=False)
        self.assertContains(response, ">D<", html=False)
        self.assertContains(response, "Active")
        self.assertContains(response, "Review")
        self.assertContains(response, "Deleted in SF")

    def test_review_file_preview_returns_csv_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            local_path = self._write_review_fixture(repo_root)

            with override_settings(REPO_ROOT=repo_root):
                response = self.client.get(
                    reverse("pipeline_dashboard:review_file_preview"),
                    {"local_path": local_path},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["file"]["name"], "new-report.csv")
        self.assertEqual(payload["file"]["kind"], "csv")
        self.assertEqual(payload["file"]["sheets"][0]["headers"], ["Date", "Campaign", "Spend"])
        self.assertEqual(payload["file"]["sheets"][0]["rows"][1], ["2026-05-07", "Spring", "10"])

    def test_process_review_file_marks_asset_active_with_vendor(self):
        vendor = Vendor.objects.create(name="AdTaxi", parser_key="adtaxi")
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            local_path = self._write_review_fixture(repo_root)

            with override_settings(REPO_ROOT=repo_root):
                response = self.client.post(
                    reverse("pipeline_dashboard:process_review_file"),
                    {"local_path": local_path, "vendor_id": vendor.id},
                )

        self.assertEqual(response.status_code, 200)
        asset = Asset.objects.get(remote_item_id="fi-review")
        self.assertEqual(asset.status, AssetStatus.PROCESSING)
        self.assertEqual(asset.vendor, vendor)
        self.assertEqual(asset.local_path, local_path)
        self.assertEqual(asset.parser_key, "adtaxi")
        self.assertTrue(asset.events.filter(event_type="review_started").exists())

    def test_process_page_renders_processing_assets(self):
        loop, _ = Vendor.objects.get_or_create(name="Loop", defaults={"parser_key": "loop"})
        podcastone, _ = Vendor.objects.get_or_create(name="PodcastOne", defaults={"parser_key": "podcastone"})
        Asset.objects.create(
            remote_item_id="fi-processing",
            vendor=loop,
            status=AssetStatus.PROCESSING,
            name="Loop report.csv",
            created_by_name="Uploader One",
            file_size=25,
        )
        Asset.objects.create(
            remote_item_id="fi-new-hidden",
            vendor=podcastone,
            status=AssetStatus.NEW,
            name="PodcastOne new.csv",
        )

        response = self.client.get(reverse("pipeline_dashboard:process"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Processing Files")
        self.assertContains(response, "Loop report.csv")
        self.assertContains(response, "Loop")
        self.assertContains(response, "PodcastOne")
        self.assertContains(response, "Cancel")
        self.assertContains(response, "Approval")
        self.assertNotContains(response, "PodcastOne new.csv")

    def test_update_process_vendor_changes_asset_vendor(self):
        loop, _ = Vendor.objects.get_or_create(name="Loop", defaults={"parser_key": "loop"})
        podcastone, _ = Vendor.objects.get_or_create(name="PodcastOne", defaults={"parser_key": "podcastone"})
        asset = Asset.objects.create(
            remote_item_id="fi-processing",
            vendor=loop,
            parser_key="loop",
            status=AssetStatus.PROCESSING,
            name="Loop report.csv",
        )

        response = self.client.post(
            reverse("pipeline_dashboard:update_process_vendor", args=[asset.remote_item_id]),
            {"vendor_id": podcastone.id},
        )

        self.assertRedirects(response, reverse("pipeline_dashboard:process"))
        asset.refresh_from_db()
        self.assertEqual(asset.vendor, podcastone)
        self.assertEqual(asset.parser_key, "podcastone")
        self.assertTrue(asset.events.filter(event_type="vendor_changed").exists())

    def test_cancel_process_file_clears_vendor_and_returns_to_new(self):
        loop, _ = Vendor.objects.get_or_create(name="Loop", defaults={"parser_key": "loop"})
        asset = Asset.objects.create(
            remote_item_id="fi-processing",
            vendor=loop,
            parser_key="loop",
            status=AssetStatus.PROCESSING,
            name="Loop report.csv",
        )

        response = self.client.post(reverse("pipeline_dashboard:cancel_process_file", args=[asset.remote_item_id]))

        self.assertRedirects(response, reverse("pipeline_dashboard:process"))
        asset.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.NEW)
        self.assertIsNone(asset.vendor)
        self.assertEqual(asset.parser_key, "")
        self.assertTrue(asset.events.filter(event_type="processing_cancelled").exists())

    def test_parse_file_preview_validates_loop_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            asset = self._write_loop_parse_fixture(repo_root)

            with override_settings(REPO_ROOT=repo_root):
                response = self.client.get(reverse("pipeline_dashboard:parse_file_preview", args=[asset.remote_item_id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["validation"]["ok"])
        self.assertEqual(payload["validation"]["vendor"], "Loop")
        self.assertEqual(payload["validation"]["sheet_name"], "Daily Spend")
        self.assertEqual(payload["file"]["sheets"][0]["name"], "Daily Spend")

    def test_parse_process_file_returns_chart_preview_without_writing_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            asset = self._write_loop_parse_fixture(repo_root)

            with override_settings(REPO_ROOT=repo_root):
                response = self.client.post(reverse("pipeline_dashboard:parse_process_file", args=[asset.remote_item_id]))
                output_exists = (repo_root / "data" / "output" / "Loop" / "Loop_May_2026_v1.csv").exists()

        self.assertEqual(response.status_code, 200)
        asset.refresh_from_db()
        payload = response.json()
        self.assertEqual(asset.status, AssetStatus.PROCESSING)
        self.assertFalse(output_exists)
        self.assertEqual(payload["candidate"]["summary"]["period_label"], "May_2026")
        self.assertEqual(payload["candidate"]["summary"]["row_count"], 2)
        self.assertEqual(payload["charts"]["series"][0]["label"], "Parsed May_2026")
        self.assertEqual(payload["charts"]["series"][0]["points"][0]["day"], 1)
        self.assertEqual(ParsedOutput.objects.filter(asset=asset).count(), 0)

    def test_approve_process_file_sends_versioned_output_for_external_approval(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            asset = self._write_loop_parse_fixture(repo_root)
            fake_client = FakeApprovalClient()

            with (
                override_settings(REPO_ROOT=repo_root),
                patch("pipeline_dashboard.parser_workflow.approval_root_id", return_value="fo-root"),
                patch("pipeline_dashboard.parser_workflow.build_sharefile_client", return_value=fake_client),
            ):
                response = self.client.post(reverse("pipeline_dashboard:approve_process_file", args=[asset.remote_item_id]))
                output_exists = (repo_root / "data" / "output" / "Loop" / "Loop_May_2026_v1.csv").exists()
                processed_exists = (repo_root / "data" / "processed" / "Loop" / "Loop_May_2026.csv").exists()

        self.assertEqual(response.status_code, 200)
        asset.refresh_from_db()
        parsed = ParsedOutput.objects.get(asset=asset)
        self.assertEqual(asset.status, AssetStatus.REVIEW)
        self.assertEqual(asset.uploaded_item_id, "fi-uploaded")
        self.assertEqual(asset.output_path, "data/output/Loop/Loop_May_2026_v1.csv")
        self.assertEqual(parsed.reporting_period, "May_2026")
        self.assertEqual(parsed.row_count, 2)
        self.assertEqual(parsed.comparison_status, "sent_for_approval")
        self.assertEqual(parsed.comparison_summary["sharefile_item_id"], "fi-uploaded")
        self.assertTrue(output_exists)
        self.assertFalse(processed_exists)
        self.assertEqual(fake_client.folder_parts, ["Approval", fake_client.current_month, "Loop"])
        self.assertEqual(fake_client.uploaded_name, "Loop_May_2026_v1.csv")
        self.assertTrue(asset.events.filter(event_type="approval_sent").exists())

    def test_cancel_parsed_output_returns_asset_to_processing(self):
        loop, _ = Vendor.objects.get_or_create(name="Loop", defaults={"parser_key": "loop"})
        asset = Asset.objects.create(
            remote_item_id="fi-loop-review",
            vendor=loop,
            parser_key="loop",
            status=AssetStatus.REVIEW,
            name="Loop review.xlsx",
            output_path="data/output/Loop/Loop_May_2026_v1.csv",
        )
        parsed = ParsedOutput.objects.create(
            asset=asset,
            vendor=loop,
            output_path="data/output/Loop/Loop_May_2026_v1.csv",
            reporting_period="May_2026",
            comparison_status="no_matching_history",
        )

        response = self.client.post(reverse("pipeline_dashboard:cancel_parsed_output", args=[parsed.id]))

        self.assertRedirects(response, reverse("pipeline_dashboard:process"))
        asset.refresh_from_db()
        parsed.refresh_from_db()
        self.assertEqual(asset.status, AssetStatus.PROCESSING)
        self.assertEqual(asset.output_path, "")
        self.assertEqual(parsed.comparison_status, "cancelled")
        self.assertTrue(asset.events.filter(event_type="parsed_output_cancelled").exists())

    def test_approval_root_defaults_to_allshared(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / ".env").write_text("SHAREFILE_CLIENT_ID=example\n", encoding="utf-8")

            with override_settings(REPO_ROOT=repo_root):
                self.assertEqual(approval_root_id(), "allshared")

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

    def _write_review_fixture(self, repo_root: Path) -> str:
        local_path = "data/inbox/home/josh/new-report.csv"
        state_root = repo_root / "data" / "state"
        file_path = repo_root / local_path
        state_root.mkdir(parents=True)
        file_path.parent.mkdir(parents=True)
        file_path.write_text("Date,Campaign,Spend\n2026-05-07,Spring,10\n", encoding="utf-8")
        (state_root / "sharefile_snapshot_latest.json").write_text(
            json.dumps(
                {
                    "run_id": "snapshot-review",
                    "created_at": "2026-05-07T10:00:00Z",
                    "files": [
                        {
                            "remote_item_id": "fi-review",
                            "name": "new-report.csv",
                            "remote_path": "home/josh/new-report.csv",
                            "local_path": local_path,
                            "source_folder_path": "home/josh",
                            "source_folder_id": "fo-josh",
                            "extension": ".csv",
                            "size": file_path.stat().st_size,
                            "created_at": "2026-05-07T09:00:00Z",
                            "modified_at": "2026-05-07T10:00:00Z",
                            "creator": "Uploader One",
                            "raw_metadata": {"LastModifiedByUserID": "user-1"},
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        (state_root / "inbox_profile_latest.json").write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "local_path": local_path,
                            "name": "new-report.csv",
                            "kind": "csv",
                            "status": "profiled",
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        (state_root / "sharefile_users_latest.json").write_text(
            json.dumps({"users_by_id": {"user-1": {"full_name": "Uploader One", "email": "one@example.com"}}}),
            encoding="utf-8",
        )
        return local_path

    def _write_loop_parse_fixture(self, repo_root: Path) -> Asset:
        project_root = Path(__file__).resolve().parents[3]
        parser_root = repo_root / "parsers" / "Loop"
        parser_root.mkdir(parents=True)
        shutil.copy2(project_root / "parsers" / "Loop" / "input_schema.json", parser_root / "input_schema.json")
        shutil.copy2(project_root / "parsers" / "Loop" / "parser.py", parser_root / "parser.py")

        approved_path = repo_root / "data" / "processed" / "Loop" / "Loop.csv"
        approved_path.parent.mkdir(parents=True)
        approved_path.write_text(
            "\n".join(
                [
                    "Date,Vendor,Brand,Channel,Platform,Spend,Impressions,Data_Grain,Processed_At,Source_File",
                    "2026-05-01,Loop,BetOnline,DOOH,Loop TV,10,100,daily,approved,baseline.csv",
                    "2026-05-02,Loop,BetOnline,DOOH,Loop TV,20,200,daily,approved,baseline.csv",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        local_path = "data/inbox/home/josh/LOOP MAY 2026.xlsx"
        workbook_path = repo_root / local_path
        workbook_path.parent.mkdir(parents=True)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Daily Spend"
        sheet["A5"] = "Date"
        sheet["B5"] = "Impressions"
        sheet["C5"] = "Spend"
        sheet["A6"] = "2026-05-01"
        sheet["B6"] = 100
        sheet["C6"] = 10
        sheet["A7"] = "2026-05-02"
        sheet["B7"] = 200
        sheet["C7"] = 20
        workbook.save(workbook_path)
        workbook.close()

        loop, _ = Vendor.objects.get_or_create(name="Loop", defaults={"parser_key": "loop"})
        return Asset.objects.create(
            remote_item_id="fi-loop-parse",
            vendor=loop,
            parser_key="loop",
            status=AssetStatus.PROCESSING,
            name="LOOP MAY 2026.xlsx",
            local_path=local_path,
            file_size=workbook_path.stat().st_size,
        )

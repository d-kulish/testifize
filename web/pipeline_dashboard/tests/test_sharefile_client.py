from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import TestCase

from testifize_pipeline.sharefile.client import ShareFileClient, ShareFileConfig, ShareFileError


class ShareFileClientTests(TestCase):
    def _make_client(self) -> ShareFileClient:
        config = ShareFileConfig(
            subdomain="example",
            username="user@example.com",
            client_id="client-id",
            client_secret="client-secret",
            app_password="password",
        )
        client = ShareFileClient(config)
        client._token = "test-token"
        client.base_url = "https://example.sharefile.com"
        return client

    def test_list_access_controls_returns_value_list(self):
        client = self._make_client()
        mock_response = {
            "value": [
                {
                    "Principal": {"Id": "u1", "Name": "Alice"},
                    "CanView": True,
                    "CanDownload": True,
                    "NotifyOnUpload": True,
                },
                {
                    "Principal": {"Id": "u2", "Name": "Bob"},
                    "CanView": True,
                    "NotifyOnUpload": False,
                },
            ]
        }

        with patch.object(client, "_request_json", return_value=(200, mock_response, {})):
            controls = client.list_access_controls("fo-folder")

        self.assertEqual(len(controls), 2)
        self.assertTrue(controls[0]["NotifyOnUpload"])
        self.assertFalse(controls[1]["NotifyOnUpload"])

    def test_list_access_controls_raises_on_non_200(self):
        client = self._make_client()

        with patch.object(client, "_request_json", return_value=(403, {}, {})):
            with self.assertRaises(ShareFileError):
                client.list_access_controls("fo-folder")

    def test_copy_access_controls_posts_each_control(self):
        client = self._make_client()
        source_controls = [
            {
                "Principal": {"Id": "u1"},
                "CanView": True,
                "CanDownload": True,
                "CanUpload": False,
                "CanDelete": False,
                "CanManagePermissions": False,
                "NotifyOnUpload": True,
                "NotifyOnDownload": False,
            },
            {
                "Principal": {"Id": "g1"},
                "CanView": True,
                "CanDownload": False,
                "CanUpload": True,
                "CanDelete": False,
                "CanManagePermissions": True,
                "NotifyOnUpload": True,
                "NotifyOnDownload": True,
            },
        ]

        def mock_request_json(method, url, **kwargs):
            if "AccessControls" in url and method == "GET":
                return (200, {"value": source_controls}, {})
            if "AccessControls" in url and method == "POST":
                return (201, {}, {})
            return (200, {}, {})

        with patch.object(client, "_request_json", side_effect=mock_request_json):
            client.copy_access_controls("fo-source", "fo-target")

    def test_copy_access_controls_skips_entries_without_principal(self):
        client = self._make_client()
        source_controls = [
            {"CanView": True, "NotifyOnUpload": True},  # missing Principal
        ]

        post_calls = []

        def mock_request_json(method, url, **kwargs):
            if "AccessControls" in url and method == "GET":
                return (200, {"value": source_controls}, {})
            if "AccessControls" in url and method == "POST":
                post_calls.append((method, url, kwargs))
                return (201, {}, {})
            return (200, {}, {})

        with patch.object(client, "_request_json", side_effect=mock_request_json):
            client.copy_access_controls("fo-source", "fo-target")

        self.assertEqual(len(post_calls), 0)

    def test_copy_access_controls_raises_on_failed_post(self):
        client = self._make_client()
        source_controls = [
            {
                "Principal": {"Id": "u1"},
                "NotifyOnUpload": True,
            }
        ]

        def mock_request_json(method, url, **kwargs):
            if "AccessControls" in url and method == "GET":
                return (200, {"value": source_controls}, {})
            if "AccessControls" in url and method == "POST":
                return (400, {"error": "bad request"}, {})
            return (200, {}, {})

        with patch.object(client, "_request_json", side_effect=mock_request_json):
            with self.assertRaises(ShareFileError):
                client.copy_access_controls("fo-source", "fo-target")

    def test_ensure_folder_path_copies_access_controls_for_new_folders(self):
        client = self._make_client()
        call_log = []

        def mock_request_json(method, url, **kwargs):
            if "Children" in url:
                return (200, {"value": []}, {})
            if "Folder" in url and method == "POST":
                call_log.append(("create_folder", url))
                return (201, {"Id": "fo-new", "Name": "NewFolder", "odata.type": "Folder"}, {})
            if "AccessControls" in url and method == "GET":
                return (
                    200,
                    {
                        "value": [
                            {
                                "Principal": {"Id": "u1"},
                                "NotifyOnUpload": True,
                                "CanView": True,
                            }
                        ]
                    },
                    {},
                )
            if "AccessControls" in url and method == "POST":
                call_log.append(("copy_control", url, kwargs.get("json_body")))
                return (201, {}, {})
            return (200, {"Id": "fo-root", "Name": "Root", "odata.type": "Folder"}, {})

        with patch.object(client, "_request_json", side_effect=mock_request_json):
            folder = client.ensure_folder_path(
                "fo-root", ["NewFolder"], copy_access_controls=True
            )

        self.assertEqual(folder.id, "fo-new")
        create_calls = [c for c in call_log if c[0] == "create_folder"]
        copy_calls = [c for c in call_log if c[0] == "copy_control"]
        self.assertEqual(len(create_calls), 1)
        self.assertEqual(len(copy_calls), 1)
        self.assertTrue(copy_calls[0][2]["NotifyOnUpload"])

    def test_ensure_folder_path_does_not_copy_when_folder_exists(self):
        client = self._make_client()
        call_log = []

        def mock_request_json(method, url, **kwargs):
            if "Children" in url:
                return (
                    200,
                    {"value": [{"Id": "fo-existing", "Name": "Existing", "odata.type": "Folder"}]},
                    {},
                )
            if "AccessControls" in url:
                call_log.append((method, url))
                return (200, {"value": []}, {})
            return (200, {"Id": "fo-root", "Name": "Root", "odata.type": "Folder"}, {})

        with patch.object(client, "_request_json", side_effect=mock_request_json):
            folder = client.ensure_folder_path(
                "fo-root", ["Existing"], copy_access_controls=True
            )

        self.assertEqual(folder.id, "fo-existing")
        access_control_calls = [c for c in call_log if "AccessControls" in c[1]]
        self.assertEqual(len(access_control_calls), 0)

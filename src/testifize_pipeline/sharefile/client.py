from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ShareFileConfig:
    subdomain: str
    username: str
    client_id: str
    client_secret: str
    app_password: str

    @classmethod
    def from_env(cls, env: dict[str, str]) -> "ShareFileConfig":
        required = [
            "SHAREFILE_SUBDOMAIN",
            "SHAREFILE_USER",
            "SHAREFILE_CLIENT_ID",
            "SHAREFILE_CLIENT_SECRET",
            "SHAREFILE_APP_PASSWORD",
        ]
        missing = [key for key in required if not env.get(key)]
        if missing:
            raise ValueError(f"Missing ShareFile env keys: {', '.join(missing)}")
        return cls(
            subdomain=env["SHAREFILE_SUBDOMAIN"],
            username=env["SHAREFILE_USER"],
            client_id=env["SHAREFILE_CLIENT_ID"],
            client_secret=env["SHAREFILE_CLIENT_SECRET"],
            app_password=env["SHAREFILE_APP_PASSWORD"],
        )


@dataclass(frozen=True)
class ShareFileItem:
    id: str
    name: str
    kind: str
    parent_id: str | None
    size: int | None
    created_at: str | None
    modified_at: str | None
    created_by_name: str | None
    created_by_email: str | None
    raw: dict[str, Any]

    @property
    def is_folder(self) -> bool:
        return "Folder" in self.kind

    @property
    def is_file(self) -> bool:
        return "File" in self.kind or self.id.startswith("fi")

    @classmethod
    def from_api(cls, raw: dict[str, Any], parent_id: str | None = None) -> "ShareFileItem":
        creator = raw.get("Creator") or raw.get("CreatedBy") or {}
        return cls(
            id=raw.get("Id", ""),
            name=raw.get("Name") or raw.get("FileName") or "",
            kind=raw.get("odata.type") or raw.get("__type") or raw.get("Type") or "",
            parent_id=(raw.get("Parent") or {}).get("Id") or parent_id,
            size=_to_int(raw.get("FileSizeBytes") or raw.get("Size")),
            created_at=raw.get("CreationDate") or raw.get("CreatedDate"),
            modified_at=(
                raw.get("ClientModifiedDate")
                or raw.get("ProgenyEditDate")
                or raw.get("LastModifiedDate")
                or raw.get("CreationDate")
            ),
            created_by_name=creator.get("FullName") or creator.get("Name"),
            created_by_email=creator.get("Email"),
            raw=raw,
        )


def _to_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class ShareFileClient:
    def __init__(self, config: ShareFileConfig):
        self.config = config
        self.base_url = f"https://{config.subdomain}.sharefile.com"
        self._token: str | None = None

    def authenticate(self) -> None:
        status, body, _ = self._request_json(
            "POST",
            f"{self.base_url}/oauth/token",
            form={
                "grant_type": "password",
                "client_id": self.config.client_id,
                "client_secret": self.config.client_secret,
                "username": self.config.username,
                "password": self.config.app_password,
            },
            include_auth=False,
        )
        if status != 200 or "access_token" not in body:
            safe = {key: value for key, value in body.items() if "token" not in key.lower()}
            raise ShareFileError(f"ShareFile authentication failed: status={status} body={safe}")
        self._token = body["access_token"]
        api_cp = body.get("apicp")
        subdomain = body.get("subdomain")
        if api_cp and subdomain:
            self.base_url = f"https://{subdomain}.{api_cp}"

    def get_item(self, item_id: str) -> ShareFileItem:
        status, body, _ = self._request_json("GET", f"{self.base_url}/sf/v3/Items({item_id})")
        if status != 200:
            raise ShareFileError(f"Could not get item {item_id}: status={status} body={body}")
        return ShareFileItem.from_api(body)

    def list_children(self, folder_id: str) -> list[ShareFileItem]:
        status, body, _ = self._request_json("GET", f"{self.base_url}/sf/v3/Items({folder_id})/Children")
        if status != 200:
            raise ShareFileError(f"Could not list folder {folder_id}: status={status} body={body}")
        return [ShareFileItem.from_api(item, parent_id=folder_id) for item in body.get("value", [])]

    def create_folder(self, parent_id: str, name: str, description: str = "") -> ShareFileItem:
        status, body, _ = self._request_json(
            "POST",
            f"{self.base_url}/sf/v3/Items({parent_id})/Folder?overwrite=false&passthrough=false",
            json_body={"Name": name, "Description": description},
        )
        if status not in {200, 201}:
            raise ShareFileError(f"Could not create folder {name} under {parent_id}: status={status} body={body}")
        return ShareFileItem.from_api(body, parent_id=parent_id)

    def ensure_folder_path(
        self, root_id: str, parts: list[str], copy_access_controls: bool = False
    ) -> ShareFileItem:
        current_id = root_id
        current_item = self.get_item(root_id)
        for part in parts:
            match = None
            for child in self.list_children(current_id):
                if child.is_folder and child.name == part:
                    match = child
                    break
            if match:
                current_item = match
            else:
                current_item = self.create_folder(current_id, part)
                if copy_access_controls:
                    self.copy_access_controls(current_id, current_item.id)
            current_id = current_item.id
        return current_item

    def list_access_controls(self, folder_id: str) -> list[dict[str, Any]]:
        status, body, _ = self._request_json(
            "GET", f"{self.base_url}/sf/v3/Items({folder_id})/AccessControls"
        )
        if status != 200:
            raise ShareFileError(
                f"Could not list access controls for folder {folder_id}: status={status} body={body}"
            )
        return body.get("value", [])

    def copy_access_controls(self, source_folder_id: str, target_folder_id: str) -> None:
        controls = self.list_access_controls(source_folder_id)
        for control in controls:
            principal = control.get("Principal")
            if not principal:
                continue
            payload = {
                "Principal": principal,
                "CanView": control.get("CanView", True),
                "CanDownload": control.get("CanDownload", True),
                "CanUpload": control.get("CanUpload", False),
                "CanDelete": control.get("CanDelete", False),
                "CanManagePermissions": control.get("CanManagePermissions", False),
                "NotifyOnUpload": control.get("NotifyOnUpload", False),
                "NotifyOnDownload": control.get("NotifyOnDownload", False),
            }
            status, body, _ = self._request_json(
                "POST",
                f"{self.base_url}/sf/v3/Items({target_folder_id})/AccessControls",
                json_body=payload,
            )
            if status not in {200, 201}:
                raise ShareFileError(
                    f"Could not copy access control to folder {target_folder_id}: status={status} body={body}"
                )

    def download_file(self, item_id: str, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        status, body, _ = self._request_json(
            "GET",
            f"{self.base_url}/sf/v3/Items({item_id})/Download?redirect=false",
        )
        if status != 200:
            raise ShareFileError(f"Could not prepare download {item_id}: status={status} body={body}")
        download_url = body.get("DownloadUrl") or body.get("Url")
        if not download_url:
            raise ShareFileError(f"ShareFile download response did not include a URL for {item_id}")

        status, _, raw = self._request_raw("GET", download_url, include_auth=False)
        if status != 200:
            raise ShareFileError(f"Download failed for {item_id}: status={status}")
        destination.write_bytes(raw)
        return destination

    def upload_bytes(
        self,
        folder_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
        notify: bool = False,
        overwrite: bool = False,
    ) -> ShareFileItem:
        query = urllib.parse.urlencode(
            {
                "method": "standard",
                "raw": "true",
                "fileName": filename,
                "fileSize": str(len(content)),
                "overwrite": str(overwrite).lower(),
                "notify": str(notify).lower(),
            }
        )
        status, body, _ = self._request_json("POST", f"{self.base_url}/sf/v3/Items({folder_id})/Upload?{query}")
        if status != 200 or not body.get("ChunkUri"):
            raise ShareFileError(f"Could not prepare upload: status={status} body={body}")

        status, _, raw = self._request_raw(
            "POST",
            body["ChunkUri"],
            body=content,
            headers={"Content-Type": content_type, "Content-Length": str(len(content))},
            include_auth=False,
        )
        response = raw.decode("utf-8", "replace") if raw else ""
        if status != 200 or response.startswith("ERROR:"):
            raise ShareFileError(f"Upload failed: status={status} response={response[:200]}")

        for item in self.list_children(folder_id):
            if item.name == filename:
                return item
        raise ShareFileError(f"Upload succeeded but {filename} was not found in folder listing")

    def _request_json(
        self,
        method: str,
        url: str,
        form: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        include_auth: bool = True,
    ) -> tuple[int, dict[str, Any], dict[str, str]]:
        body: bytes | None = None
        headers = {"Accept": "application/json"}
        if form is not None:
            body = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif json_body is not None:
            body = json.dumps(json_body).encode()
            headers["Content-Type"] = "application/json"

        status, response_headers, raw = self._request_raw(method, url, body=body, headers=headers, include_auth=include_auth)
        if not raw:
            return status, {}, response_headers
        try:
            return status, json.loads(raw.decode("utf-8", "replace")), response_headers
        except json.JSONDecodeError:
            return status, {"raw": raw.decode("utf-8", "replace")[:500]}, response_headers

    def _request_raw(
        self,
        method: str,
        url: str,
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        include_auth: bool = True,
    ) -> tuple[int, dict[str, str], bytes]:
        req_headers = dict(headers or {})
        if include_auth:
            if not self._token:
                self.authenticate()
            req_headers["Authorization"] = f"Bearer {self._token}"

        request = urllib.request.Request(url, data=body, headers=req_headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, dict(response.headers), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()


class ShareFileError(RuntimeError):
    pass

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable


class AssetStatus(StrEnum):
    DISCOVERED = "discovered"
    NEW = "new"
    QUEUED = "queued"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSING = "processing"
    PROCESSED = "processed"
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    SUPERSEDED = "superseded"
    IGNORED = "ignored"
    FAILED = "failed"


@dataclass(frozen=True)
class AssetRecord:
    remote_item_id: str
    vendor: str | None
    status: str
    name: str
    source_folder_id: str | None
    source_folder_label: str | None
    remote_path: str | None
    file_size: int | None
    remote_created_at: str | None
    remote_modified_at: str | None
    created_by_name: str | None
    created_by_email: str | None
    local_path: str | None
    output_path: str | None
    uploaded_item_id: str | None
    parser: str | None
    parser_version: str | None
    content_hash: str | None
    duplicate_group: str | None
    status_reason: str | None
    first_seen_at: str
    last_seen_at: str
    updated_at: str
    raw_metadata_json: str | None


class AssetCatalog:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.ensure_schema()

    def ensure_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS assets (
                remote_item_id TEXT PRIMARY KEY,
                vendor TEXT,
                status TEXT NOT NULL,
                name TEXT NOT NULL,
                source_folder_id TEXT,
                source_folder_label TEXT,
                remote_path TEXT,
                file_size INTEGER,
                remote_created_at TEXT,
                remote_modified_at TEXT,
                created_by_name TEXT,
                created_by_email TEXT,
                local_path TEXT,
                output_path TEXT,
                uploaded_item_id TEXT,
                parser TEXT,
                parser_version TEXT,
                content_hash TEXT,
                duplicate_group TEXT,
                status_reason TEXT,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                raw_metadata_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_assets_vendor_status
                ON assets(vendor, status);

            CREATE INDEX IF NOT EXISTS idx_assets_remote_modified
                ON assets(remote_modified_at);

            CREATE INDEX IF NOT EXISTS idx_assets_duplicate_group
                ON assets(duplicate_group);

            CREATE TABLE IF NOT EXISTS asset_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                remote_item_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT,
                message TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT
            );
            """
        )
        self.connection.commit()

    def upsert_discovered(
        self,
        *,
        remote_item_id: str,
        name: str,
        vendor: str | None,
        source_folder_id: str | None,
        source_folder_label: str | None,
        remote_path: str | None,
        file_size: int | None,
        remote_created_at: str | None,
        remote_modified_at: str | None,
        created_by_name: str | None,
        created_by_email: str | None,
        raw_metadata: dict[str, Any] | None,
        parser: str | None = None,
    ) -> AssetRecord:
        now = utc_now()
        existing = self.get(remote_item_id)
        status = existing.status if existing else AssetStatus.NEW.value
        first_seen_at = existing.first_seen_at if existing else now
        previous_modified = existing.remote_modified_at if existing else None
        if existing and previous_modified and remote_modified_at and previous_modified != remote_modified_at:
            status = AssetStatus.NEW.value

        payload = {
            "remote_item_id": remote_item_id,
            "vendor": vendor,
            "status": status,
            "name": name,
            "source_folder_id": source_folder_id,
            "source_folder_label": source_folder_label,
            "remote_path": remote_path,
            "file_size": file_size,
            "remote_created_at": remote_created_at,
            "remote_modified_at": remote_modified_at,
            "created_by_name": created_by_name,
            "created_by_email": created_by_email,
            "local_path": existing.local_path if existing else None,
            "output_path": existing.output_path if existing else None,
            "uploaded_item_id": existing.uploaded_item_id if existing else None,
            "parser": parser or (existing.parser if existing else None),
            "parser_version": existing.parser_version if existing else None,
            "content_hash": existing.content_hash if existing else None,
            "duplicate_group": existing.duplicate_group if existing else None,
            "status_reason": existing.status_reason if existing else None,
            "first_seen_at": first_seen_at,
            "last_seen_at": now,
            "updated_at": now,
            "raw_metadata_json": json.dumps(raw_metadata or {}, sort_keys=True),
        }
        self._upsert(payload)
        if not existing:
            self.add_event(remote_item_id, "discovered", None, status, "New remote asset discovered")
        elif previous_modified != remote_modified_at:
            self.add_event(remote_item_id, "rediscovered", existing.status, status, "Remote metadata changed")
        return self.get(remote_item_id)

    def set_status(
        self,
        remote_item_id: str,
        status: AssetStatus | str,
        message: str | None = None,
        **updates: Any,
    ) -> None:
        record = self.get(remote_item_id)
        if not record:
            raise KeyError(f"Unknown asset: {remote_item_id}")
        now = utc_now()
        values = {key: value for key, value in updates.items() if value is not None}
        values["status"] = str(status)
        values["updated_at"] = now
        assignments = ", ".join(f"{key} = ?" for key in values)
        self.connection.execute(
            f"UPDATE assets SET {assignments} WHERE remote_item_id = ?",
            [*values.values(), remote_item_id],
        )
        self.add_event(remote_item_id, "status", record.status, str(status), message)
        self.connection.commit()

    def get(self, remote_item_id: str) -> AssetRecord | None:
        row = self.connection.execute(
            "SELECT * FROM assets WHERE remote_item_id = ?",
            (remote_item_id,),
        ).fetchone()
        return _record_from_row(row) if row else None

    def list_assets(self, vendor: str | None = None, status: str | None = None) -> list[AssetRecord]:
        clauses = []
        params: list[Any] = []
        if vendor:
            clauses.append("vendor = ?")
            params.append(vendor)
        if status:
            clauses.append("status = ?")
            params.append(status)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self.connection.execute(
            f"SELECT * FROM assets {where} ORDER BY remote_modified_at DESC, last_seen_at DESC",
            params,
        ).fetchall()
        return [_record_from_row(row) for row in rows]

    def add_event(
        self,
        remote_item_id: str,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        message: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO asset_events (
                remote_item_id, event_type, from_status, to_status,
                message, created_at, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                remote_item_id,
                event_type,
                from_status,
                to_status,
                message,
                utc_now(),
                json.dumps(metadata or {}, sort_keys=True),
            ),
        )
        self.connection.commit()

    def _upsert(self, payload: dict[str, Any]) -> None:
        keys = list(payload)
        placeholders = ", ".join("?" for _ in keys)
        updates = ", ".join(f"{key} = excluded.{key}" for key in keys if key != "remote_item_id")
        self.connection.execute(
            f"""
            INSERT INTO assets ({", ".join(keys)})
            VALUES ({placeholders})
            ON CONFLICT(remote_item_id) DO UPDATE SET {updates}
            """,
            [payload[key] for key in keys],
        )
        self.connection.commit()


def _record_from_row(row: sqlite3.Row) -> AssetRecord:
    return AssetRecord(**{key: row[key] for key in row.keys()})


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def records_to_dicts(records: Iterable[AssetRecord]) -> list[dict[str, Any]]:
    return [asdict(record) for record in records]

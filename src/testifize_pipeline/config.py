from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> dict[str, str]:
    env_path = path or PROJECT_ROOT / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip("\"").strip("'")
    return values


@dataclass(frozen=True)
class VendorFolder:
    vendor: str
    input_folder_id: str
    output_folder_id: str | None
    parser: str | None
    file_patterns: tuple[str, ...]
    folder_label: str | None = None


def load_vendor_folders(path: Path) -> list[VendorFolder]:
    data = json.loads(path.read_text())
    vendors = data.get("vendors", {})
    folders: list[VendorFolder] = []
    for vendor, config in vendors.items():
        folders.append(
            VendorFolder(
                vendor=vendor,
                input_folder_id=config["input_folder_id"],
                output_folder_id=config.get("output_folder_id"),
                parser=config.get("parser"),
                file_patterns=tuple(config.get("file_patterns", ["*.xlsx", "*.xls", "*.csv"])),
                folder_label=config.get("folder_label"),
            )
        )
    return folders

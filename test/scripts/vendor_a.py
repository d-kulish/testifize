from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from excel_audit import load_workbook, parse_excel_date, row_values, safe_float, safe_int

INPUT_PATH = PROJECT_ROOT / "Inputs" / "Vendor_A_MediaWave_Jan2026.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "csv" / "vendor_a.csv"
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
SCHEMA_PATH = SCHEMA_DIR / "output_schema.json"
INPUT_SCHEMA_PATH = SCHEMA_DIR / "input_a.json"

VENDOR_NAME = "MediaWave"
SPEND_TYPE = "Actual"
MARKETING_CHANNEL = "CTV"

BRAND_MAP = {
    "SP": "StakePoint",
    "StakePoint": "StakePoint",
    "WL": "WagerLine",
    "WagerLine": "WagerLine",
    "NS": "NeonSpin",
    "NeonSpin": "NeonSpin",
    "MR": "MegaReels",
    "MegaReels": "MegaReels",
}


def load_schema_columns() -> list[str]:
    with SCHEMA_PATH.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    return [column["name"] for column in schema["target_output_schema"]]


def load_input_schema() -> dict:
    with INPUT_SCHEMA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_input_columns(input_schema: dict) -> list[dict[str, str]]:
    columns = input_schema.get("columns", [])
    if not columns:
        raise ValueError("Input schema is missing source columns.")
    return columns


def get_mediawave_sheet(sheet_name_prefix: str):
    workbook = load_workbook(INPUT_PATH)
    matches = [
        workbook["sheets"][sheet_name]
        for sheet_name in workbook["sheet_order"]
        if sheet_name.startswith(sheet_name_prefix)
    ]
    if len(matches) != 1:
        raise ValueError(
            f"Expected exactly one sheet matching '{sheet_name_prefix}*', found {len(matches)}."
        )
    return matches[0]


def find_header_row(sheet, input_columns: list[dict[str, str]]) -> int:
    expected_letters = [column["letter"] for column in input_columns]
    expected_header = [column["name"] for column in input_columns]

    for row_number in sorted(sheet.rows):
        row = row_values(sheet, row_number, columns=expected_letters, include_missing=True)
        values = [row.get(letter) for letter in expected_letters]
        if values == expected_header:
            return row_number

    raise ValueError(
        f"Input schema mismatch for sheet '{sheet.name}'. "
        f"Expected header {expected_header} was not found."
    )


def build_source_records(sheet, input_columns: list[dict[str, str]]) -> list[dict[str, str | None]]:
    header_row = find_header_row(sheet, input_columns)
    expected_letters = [column["letter"] for column in input_columns]
    expected_names = [column["name"] for column in input_columns]
    expected_length = len(expected_names)

    records: list[dict[str, str | None]] = []
    for row_number in sorted(sheet.rows):
        if row_number <= header_row:
            continue

        row = row_values(sheet, row_number, columns=expected_letters, include_missing=True)
        values = [row.get(letter) for letter in expected_letters]
        if len(values) != expected_length:
            continue
        if not any(value not in (None, "") for value in values):
            continue

        record = {"_row": row_number}
        record.update(dict(zip(expected_names, values)))
        records.append(record)

    return records


def normalize_brand(value: str | None) -> str:
    brand = (value or "").strip()
    if brand not in BRAND_MAP:
        raise ValueError(f"Unsupported brand value: {brand!r}")
    return BRAND_MAP[brand]


def normalize_channel(_: str | None) -> str:
    return MARKETING_CHANNEL


def normalize_spend(value: str | None) -> float:
    try:
        spend = safe_float(value)
    except ValueError:
        return 0.0
    if spend is None or spend < 0:
        return 0.0
    return spend


def normalize_impressions(value: str | None) -> int | None:
    try:
        impressions = safe_int(value)
    except ValueError:
        return None
    if impressions is None or impressions < 0:
        return None
    return impressions


def build_rows() -> list[dict[str, object]]:
    input_schema = load_input_schema()
    input_columns = get_input_columns(input_schema)
    sheet = get_mediawave_sheet(input_schema["sheet_name_prefix"])
    raw_records = build_source_records(sheet, input_columns)

    rows: list[dict[str, object]] = []
    for record in raw_records:
        if record["Date"] == "TOTAL":
            continue

        date = parse_excel_date(record["Date"])
        if date is None:
            raise ValueError(
                f"Invalid date at source row {record['_row']}: {record['Date']!r}"
            )

        rows.append(
            {
                "Date": date,
                "Vendor": VENDOR_NAME,
                "Brand": normalize_brand(record["Brand"]),
                "Campaign": (record["Campaign Name"] or "").strip(),
                "Marketing_Channel": normalize_channel(record["Placement Type"]),
                "Sub_Channel": (record["Placement Type"] or "").strip(),
                "Daily_Spend": normalize_spend(record["Net Spend (USD)"]),
                "Daily_Impressions": normalize_impressions(record["Impressions"]),
                "Spend_Type": SPEND_TYPE,
            }
        )
    return rows


def write_csv(rows: list[dict[str, object]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = load_schema_columns()
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    rows = build_rows()
    write_csv(rows)
    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

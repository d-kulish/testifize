from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from excel_audit import load_workbook, parse_excel_date, row_values, safe_float, safe_int

INPUT_PATH = PROJECT_ROOT / "Inputs" / "Vendor_B_StreetLevel_Jan2026.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "csv" / "vendor_b.csv"
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
OUTPUT_SCHEMA_PATH = SCHEMA_DIR / "output_schema.json"
INPUT_SCHEMA_PATH = SCHEMA_DIR / "input_b.json"

VENDOR_NAME = "StreetLevel OOH"
CAMPAIGN_NAME = "March Madness Awareness"
MARKETING_CHANNEL = "DOOH"
SPEND_TYPE = "Proportioned"
STAKEPOINT_BRAND = "StakePoint"
AGGREGATED_SUB_CHANNEL = "Aggregated Total"


def load_output_columns() -> list[str]:
    with OUTPUT_SCHEMA_PATH.open(encoding="utf-8") as handle:
        schema = json.load(handle)
    return [column["name"] for column in schema["target_output_schema"]]


def load_input_schema() -> dict:
    with INPUT_SCHEMA_PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def get_sheet(sheet_name: str):
    workbook = load_workbook(INPUT_PATH)
    try:
        return workbook["sheets"][sheet_name]
    except KeyError as exc:
        raise ValueError(f"Sheet {sheet_name!r} was not found in {INPUT_PATH.name}.") from exc


def find_header_row(sheet, columns: list[dict[str, str]]) -> int:
    expected_letters = [column["letter"] for column in columns]
    expected_header = [column["name"] for column in columns]

    for row_number in sorted(sheet.rows):
        row = row_values(sheet, row_number, columns=expected_letters, include_missing=True)
        values = [row.get(letter) for letter in expected_letters]
        if values == expected_header:
            return row_number

    raise ValueError(
        f"Input schema mismatch for sheet '{sheet.name}'. "
        f"Expected header {expected_header} was not found."
    )


def build_weekly_records(sheet, columns: list[dict[str, str]]) -> list[dict[str, str | None]]:
    header_row = find_header_row(sheet, columns)
    expected_letters = [column["letter"] for column in columns]
    expected_names = [column["name"] for column in columns]

    records: list[dict[str, str | None]] = []
    for row_number in sorted(sheet.rows):
        if row_number <= header_row:
            continue

        row = row_values(sheet, row_number, columns=expected_letters, include_missing=True)
        values = [row.get(letter) for letter in expected_letters]
        if not any(value not in (None, "") for value in values):
            continue

        week_start = parse_excel_date(row.get("A"))
        if week_start is None:
            continue

        record = {"_row": row_number}
        record.update(dict(zip(expected_names, values)))
        records.append(record)

    if not records:
        raise ValueError(f"No weekly detail rows were found in sheet '{sheet.name}'.")
    return records


def get_other_brand_totals(sheet, config: dict) -> dict[str, float]:
    brand_column = config["brand_column"]
    value_column = config["value_column"]
    expected_brands = set(config["brands"])
    totals: dict[str, float] = {}

    for row_number in sorted(sheet.rows):
        row = row_values(
            sheet,
            row_number,
            columns=[brand_column, value_column],
            include_missing=True,
        )
        brand = (row.get(brand_column) or "").strip()
        if brand not in expected_brands:
            continue

        value = safe_float(row.get(value_column))
        if value is None:
            raise ValueError(f"Missing aggregate spend for brand {brand!r} at row {row_number}.")
        totals[brand] = value

    missing = expected_brands.difference(totals)
    if missing:
        raise ValueError(f"Missing aggregate totals for brands: {sorted(missing)}")

    return totals


def to_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def split_amount(total: float, periods: int) -> list[float]:
    cents = int((Decimal(str(total)) * 100).quantize(Decimal("1")))
    base = cents // periods
    remainder = cents % periods
    allocations = []
    for index in range(periods):
        share = base + (1 if index < remainder else 0)
        allocations.append(float(Decimal(share) / Decimal(100)))
    return allocations


def split_integer(total: int, periods: int) -> list[int]:
    base = total // periods
    remainder = total % periods
    allocations = []
    for index in range(periods):
        allocations.append(base + (1 if index < remainder else 0))
    return allocations


def week_dates(week_start: str) -> list[str]:
    start = to_date(week_start)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(7)]


def build_stakepoint_rows(weekly_records: list[dict[str, str | None]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []

    for record in weekly_records:
        week_start = parse_excel_date(record["Week Starting"])
        if week_start is None:
            raise ValueError(
                f"Invalid week starting value at source row {record['_row']}: "
                f"{record['Week Starting']!r}"
            )

        cost = safe_float(record["Cost"])
        impressions = safe_int(record["Est. Impressions"])
        if cost is None:
            raise ValueError(f"Missing cost at source row {record['_row']}.")
        if impressions is None:
            raise ValueError(f"Missing impressions at source row {record['_row']}.")

        dates = week_dates(week_start)
        spend_parts = split_amount(cost, len(dates))
        impression_parts = split_integer(impressions, len(dates))
        sub_channel = f"{(record['Venue Type'] or '').strip()} - {(record['Market'] or '').strip()}"

        for current_date, daily_spend, daily_impressions in zip(
            dates,
            spend_parts,
            impression_parts,
        ):
            rows.append(
                {
                    "Date": current_date,
                    "Vendor": VENDOR_NAME,
                    "Brand": STAKEPOINT_BRAND,
                    "Campaign": CAMPAIGN_NAME,
                    "Marketing_Channel": MARKETING_CHANNEL,
                    "Sub_Channel": sub_channel,
                    "Daily_Spend": daily_spend,
                    "Daily_Impressions": daily_impressions,
                    "Spend_Type": SPEND_TYPE,
                }
            )

    return rows


def build_aggregate_brand_rows(unique_dates: list[str], brand: str, total_spend: float) -> list[dict[str, object]]:
    spend_parts = split_amount(total_spend, len(unique_dates))
    rows: list[dict[str, object]] = []

    for current_date, daily_spend in zip(unique_dates, spend_parts):
        rows.append(
            {
                "Date": current_date,
                "Vendor": VENDOR_NAME,
                "Brand": brand,
                "Campaign": CAMPAIGN_NAME,
                "Marketing_Channel": MARKETING_CHANNEL,
                "Sub_Channel": AGGREGATED_SUB_CHANNEL,
                "Daily_Spend": daily_spend,
                "Daily_Impressions": None,
                "Spend_Type": SPEND_TYPE,
            }
        )

    return rows


def build_rows() -> list[dict[str, object]]:
    input_schema = load_input_schema()
    sheet = get_sheet(input_schema["sheet_name"])
    weekly_records = build_weekly_records(sheet, input_schema["weekly_table"]["columns"])
    rows = build_stakepoint_rows(weekly_records)

    unique_dates = sorted({row["Date"] for row in rows})
    aggregate_totals = get_other_brand_totals(sheet, input_schema["other_brand_totals"])
    for brand in input_schema["other_brand_totals"]["brands"]:
        rows.extend(build_aggregate_brand_rows(unique_dates, brand, aggregate_totals[brand]))

    return rows


def write_csv(rows: list[dict[str, object]]) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = load_output_columns()
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

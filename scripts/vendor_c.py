from __future__ import annotations

import csv
import json
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_FLOOR
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from excel_audit import load_workbook, parse_week_label, row_values, safe_float, safe_int

INPUT_PATH = PROJECT_ROOT / "Inputs" / "Vendor_C_AudioBlast_Jan2026.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "csv" / "vendor_c.csv"
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
OUTPUT_SCHEMA_PATH = SCHEMA_DIR / "output_schema.json"
INPUT_SCHEMA_PATH = SCHEMA_DIR / "input_c.json"

VENDOR_NAME = "AudioBlast Media"
CAMPAIGN_NAME = "Podcast Campaign"
MARKETING_CHANNEL = "Podcast/Audio"
SPEND_TYPE = "Proportioned"


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


def build_source_records(sheet, columns: list[dict[str, str]]) -> list[dict[str, str | None]]:
    header_row = find_header_row(sheet, columns)
    expected_letters = [column["letter"] for column in columns]
    expected_names = [column["name"] for column in columns]
    expected_length = len(expected_names)

    records: list[dict[str, str | None]] = []
    for row_number in sorted(sheet.rows):
        if row_number <= header_row:
            continue

        projected_row = row_values(
            sheet,
            row_number,
            columns=expected_letters,
            include_missing=True,
        )
        values = [projected_row.get(letter) for letter in expected_letters]
        if len(values) != expected_length:
            continue
        if not any(value not in (None, "") for value in values):
            continue

        record = {"_row": row_number}
        record.update(dict(zip(expected_names, values)))

        week_start = parse_week_label(record["Week"], year=2026)
        if week_start is None:
            continue
        if (record["Show / Placement"] or "").strip() in {"Subtotal", "GRAND TOTAL - ALL SHOWS"}:
            continue

        records.append(record)

    if not records:
        raise ValueError(f"No data rows were found in sheet '{sheet.name}'.")
    return records


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


def split_integer_by_weights(total: int, weights: list[Decimal]) -> list[int]:
    if not weights:
        return []

    weight_sum = sum(weights, Decimal("0"))
    if weight_sum <= 0:
        return split_integer(total, len(weights))

    allocated = 0
    allocations: list[int] = []
    fractional_parts: list[tuple[Decimal, int]] = []

    for index, weight in enumerate(weights):
        share = (Decimal(total) * weight) / weight_sum
        base = int(share.to_integral_value(rounding=ROUND_FLOOR))
        allocations.append(base)
        allocated += base
        fractional_parts.append((share - Decimal(base), index))

    remainder = total - allocated
    fractional_parts.sort(key=lambda item: (-item[0], item[1]))
    for _, index in fractional_parts[:remainder]:
        allocations[index] += 1

    return allocations


def week_dates(week_start: str) -> list[str]:
    start = to_date(week_start)
    return [(start + timedelta(days=offset)).isoformat() for offset in range(7)]


def build_sub_channel(show_name: str | None, host: str | None) -> str:
    return f"{(show_name or '').strip()} - {(host or '').strip()}"


def build_rows() -> list[dict[str, object]]:
    input_schema = load_input_schema()
    sheet = get_sheet(input_schema["sheet_name"])
    source_records = build_source_records(sheet, input_schema["columns"])

    rows: list[dict[str, object]] = []
    for record in source_records:
        week_start = parse_week_label(record["Week"], year=2026)
        if week_start is None:
            raise ValueError(
                f"Invalid week value at source row {record['_row']}: {record['Week']!r}"
            )

        stakepoint_spend = safe_float(record["StakePoint Spend"]) or 0.0
        wagerline_spend = safe_float(record["WagerLine Spend"]) or 0.0
        total_downloads = safe_int(record["Downloads (est.)"])
        if total_downloads is None:
            raise ValueError(f"Missing downloads at source row {record['_row']}.")

        dates = week_dates(week_start)
        brand_spend_map = {
            "StakePoint": stakepoint_spend,
            "WagerLine": wagerline_spend,
        }
        effective_total_spend = stakepoint_spend + wagerline_spend

        if effective_total_spend > 0:
            download_weights = [
                Decimal(str(stakepoint_spend)),
                Decimal(str(wagerline_spend)),
            ]
        else:
            # Cancelled rows have no spend signal for either brand, so use a neutral split.
            download_weights = [Decimal("1"), Decimal("1")]

        brand_download_parts = split_integer_by_weights(total_downloads, download_weights)
        sub_channel = build_sub_channel(record["Show / Placement"], record["Host"])

        for brand, brand_downloads in zip(input_schema["brands"], brand_download_parts):
            brand_spend = brand_spend_map[brand]
            daily_spend_parts = split_amount(brand_spend, len(dates))
            daily_download_parts = split_integer(brand_downloads, len(dates))

            for current_date, daily_spend, daily_downloads in zip(
                dates,
                daily_spend_parts,
                daily_download_parts,
            ):
                rows.append(
                    {
                        "Date": current_date,
                        "Vendor": VENDOR_NAME,
                        "Brand": brand,
                        "Campaign": CAMPAIGN_NAME,
                        "Marketing_Channel": MARKETING_CHANNEL,
                        "Sub_Channel": sub_channel,
                        "Daily_Spend": daily_spend,
                        "Daily_Impressions": daily_downloads,
                        "Spend_Type": SPEND_TYPE,
                    }
                )

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

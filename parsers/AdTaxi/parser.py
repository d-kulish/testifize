from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


MONEY_SCALE = Decimal("0.000001")
IMPRESSION_SCALE = Decimal("0.000001")


def parse_file(source_path: Path, input_schema: dict[str, Any], output_columns: list[str]) -> list[dict[str, Any]]:
    defaults = input_schema["output_defaults"]
    workbook = load_workbook(source_path, read_only=True, data_only=True)
    try:
        sheet = workbook[input_schema["sheet_name"]]
        start_date, end_date = parse_date_range(sheet[input_schema["metadata"]["date_range_cell"]].value)
        dates = date_range(start_date, end_date)
        if not dates:
            raise ValueError(f"No report dates were parsed from {source_path}.")

        summary_rows = input_schema["summary_rows"]
        spend_column = column_letter_to_index(summary_rows["spend_column"])
        impressions_column = column_letter_to_index(summary_rows["impressions_column"])
        first_row = summary_rows["first_row"]
        last_row = summary_rows["last_row"]

        total_spend = sum_required_cells(sheet, first_row, last_row, spend_column, "Advertiser Cost")
        total_impressions = sum_required_cells(sheet, first_row, last_row, impressions_column, "Impressions")
        daily_spend = distribute(total_spend, len(dates), MONEY_SCALE)
        daily_impressions = distribute(total_impressions, len(dates), IMPRESSION_SCALE)

        processed_at = datetime.now().isoformat(timespec="seconds")
        rows: list[dict[str, Any]] = []
        for row_date, spend, impressions in zip(dates, daily_spend, daily_impressions, strict=True):
            parsed = {
                "Date": row_date.isoformat(),
                "Vendor": defaults["Vendor"],
                "Brand": defaults["Brand"],
                "Channel": defaults["Channel"],
                "Platform": defaults["Platform"],
                "Spend": decimal_text(spend),
                "Impressions": decimal_text(impressions),
                "Data_Grain": defaults["Data_Grain"],
                "Processed_At": processed_at,
                "Source_File": source_path.name,
            }
            rows.append({column: parsed.get(column, "") for column in output_columns})

        return rows
    finally:
        workbook.close()


def parse_date_range(value: object) -> tuple[date, date]:
    if value in (None, ""):
        raise ValueError("Missing AdTaxi date range.")
    text = str(value).strip()
    if " - " in text:
        start_text, end_text = text.split(" - ", 1)
    else:
        parts = re.findall(r"\d{1,2}/\d{1,2}(?:[/\-]\d{2,4})?", text)
        if len(parts) < 2:
            raise ValueError(f"Could not parse AdTaxi date range: {text!r}")
        start_text, end_text = parts[0], parts[-1]

    start = parse_flexible_date(start_text)
    end = parse_flexible_date(end_text, default_year=start.year)
    if end < start:
        raise ValueError(f"AdTaxi date range ends before it starts: {text!r}")
    return start, end


def parse_flexible_date(value: str, default_year: int | None = None) -> date:
    text = value.strip()
    match = re.search(r"(?P<month>\d{1,2})/(?P<day>\d{1,2})(?P<year>[/\-]\d{2,4})?", text)
    if not match:
        raise ValueError(f"Invalid AdTaxi date value: {value!r}")

    year_text = match.group("year")
    if year_text:
        year = int(year_text[1:])
        if year < 100:
            year += 2000
    elif default_year:
        year = default_year
    else:
        raise ValueError(f"AdTaxi date value is missing a year: {value!r}")

    return date(year, int(match.group("month")), int(match.group("day")))


def date_range(start: date, end: date) -> list[date]:
    days = (end - start).days + 1
    return [start + timedelta(days=offset) for offset in range(days)]


def sum_required_cells(sheet: Any, first_row: int, last_row: int, column_index: int, column_name: str) -> Decimal:
    total = Decimal("0")
    for row_number in range(first_row, last_row + 1):
        value = sheet.cell(row_number, column_index).value
        total += parse_decimal(value, row_number, column_name)
    return total


def distribute(total: Decimal, count: int, scale: Decimal) -> list[Decimal]:
    if count <= 0:
        raise ValueError("Cannot distribute totals across an empty date range.")
    daily = (total / Decimal(count)).quantize(scale, rounding=ROUND_HALF_UP)
    values = [daily for _ in range(count)]
    values[-1] = (total - sum(values[:-1], Decimal("0"))).quantize(scale, rounding=ROUND_HALF_UP)
    return values


def column_letter_to_index(letter: str) -> int:
    index = 0
    for char in letter.upper():
        index = index * 26 + ord(char) - ord("A") + 1
    return index


def parse_decimal(value: object, row_number: int, column_name: str) -> Decimal:
    if value in (None, ""):
        raise ValueError(f"Missing {column_name} at row {row_number}.")

    if isinstance(value, str):
        text = value.strip()
        negative = text.startswith("(") and text.endswith(")")
        cleaned = text.strip("()").replace("$", "").replace(",", "")
    else:
        negative = False
        cleaned = str(value)

    try:
        parsed = Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid {column_name} at row {row_number}: {value!r}") from exc

    if negative:
        parsed = -parsed
    if parsed < 0:
        raise ValueError(f"Negative {column_name} at row {row_number}: {value!r}")
    return parsed


def decimal_text(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"

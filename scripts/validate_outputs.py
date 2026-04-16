from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = PROJECT_ROOT / "analysis"
if str(ANALYSIS_DIR) not in sys.path:
    sys.path.insert(0, str(ANALYSIS_DIR))

from excel_audit import load_workbook, parse_excel_date, parse_week_label, row_values, safe_float, safe_int

CSV_DIR = PROJECT_ROOT / "csv"
INPUT_DIR = PROJECT_ROOT / "Inputs"
SCHEMA_DIR = Path(__file__).resolve().parent / "schemas"
OUTPUT_SCHEMA_PATH = SCHEMA_DIR / "output_schema.json"
INPUT_A_SCHEMA_PATH = SCHEMA_DIR / "input_a.json"
INPUT_B_SCHEMA_PATH = SCHEMA_DIR / "input_b.json"
INPUT_C_SCHEMA_PATH = SCHEMA_DIR / "input_c.json"

ALLOWED_SPEND_TYPES = {"Actual", "Proportioned"}
ALLOWED_BRANDS = {"StakePoint", "WagerLine", "NeonSpin", "MegaReels"}
ALLOWED_MARKETING_CHANNELS = {
    "Broadcast/Radio",
    "CTV",
    "Display",
    "DOOH",
    "Influencer/Social",
    "Podcast/Audio",
    "PR/Other",
    "Sponsorship",
}


@dataclass
class ValidationResult:
    vendor: str
    checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)

    def ok(self, message: str) -> None:
        self.checks.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def fail(self, message: str) -> None:
        self.failures.append(message)

    @property
    def status(self) -> str:
        if self.failures:
            return "FAIL"
        if self.warnings:
            return "PASS with WARN"
        return "PASS"


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def expected_output_columns() -> list[str]:
    schema = load_json(OUTPUT_SCHEMA_PATH)
    return [column["name"] for column in schema["target_output_schema"]]


def parse_decimal(value: str | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def sum_decimal(values: list[Decimal]) -> Decimal:
    total = Decimal("0")
    for value in values:
        total += value
    return total


def decimal_to_str(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'))}"


def parse_iso_date(value: str) -> datetime.date | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def find_header_row(sheet, columns: list[dict[str, str]]) -> int:
    letters = [column["letter"] for column in columns]
    expected_header = [column["name"] for column in columns]
    for row_number in sorted(sheet.rows):
        row = row_values(sheet, row_number, columns=letters, include_missing=True)
        values = [row.get(letter) for letter in letters]
        if values == expected_header:
            return row_number
    raise ValueError(f"Header {expected_header} was not found in sheet {sheet.name!r}.")


def build_projected_records(sheet, columns: list[dict[str, str]]) -> list[dict[str, str | None]]:
    header_row = find_header_row(sheet, columns)
    letters = [column["letter"] for column in columns]
    names = [column["name"] for column in columns]
    records: list[dict[str, str | None]] = []
    for row_number in sorted(sheet.rows):
        if row_number <= header_row:
            continue
        row = row_values(sheet, row_number, columns=letters, include_missing=True)
        values = [row.get(letter) for letter in letters]
        if not any(value not in (None, "") for value in values):
            continue
        record = {"_row": row_number}
        record.update(dict(zip(names, values)))
        records.append(record)
    return records


def load_csv_rows(path: Path, result: ValidationResult) -> list[dict[str, str]]:
    if not path.exists() or not path.is_file():
        result.fail(f"CSV file is missing: {path.name}")
        return []

    try:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            expected = expected_output_columns()
            if fieldnames != expected:
                result.fail(
                    f"Header mismatch for {path.name}: expected {expected}, got {fieldnames}"
                )
            rows = list(reader)
    except Exception as exc:  # pragma: no cover - defensive
        result.fail(f"Could not read CSV {path.name}: {exc}")
        return []

    if not result.failures:
        result.ok(f"CSV header matches output schema ({len(rows)} rows).")
    return rows


def validate_global_rows(rows: list[dict[str, str]], result: ValidationResult) -> None:
    date_failures = []
    spend_failures = []
    impression_failures = []
    spend_type_failures = []
    brand_failures = []
    channel_failures = []

    for index, row in enumerate(rows, start=2):
        date_value = row["Date"]
        if parse_iso_date(date_value) is None:
            date_failures.append((index, date_value))

        spend_value = parse_decimal(row["Daily_Spend"])
        if spend_value is None or spend_value < 0:
            spend_failures.append((index, row["Daily_Spend"]))

        impressions_value = row["Daily_Impressions"]
        if impressions_value:
            try:
                int(impressions_value)
            except ValueError:
                impression_failures.append((index, impressions_value))

        if row["Spend_Type"] not in ALLOWED_SPEND_TYPES:
            spend_type_failures.append((index, row["Spend_Type"]))
        if row["Brand"] not in ALLOWED_BRANDS:
            brand_failures.append((index, row["Brand"]))
        if row["Marketing_Channel"] not in ALLOWED_MARKETING_CHANNELS:
            channel_failures.append((index, row["Marketing_Channel"]))

    if date_failures:
        result.fail(f"Invalid ISO dates found: {date_failures[:5]}")
    else:
        result.ok("All dates are valid YYYY-MM-DD strings.")

    if spend_failures:
        result.fail(f"Invalid Daily_Spend values found: {spend_failures[:5]}")
    else:
        result.ok("All Daily_Spend values are numeric and non-negative.")

    if impression_failures:
        result.fail(f"Invalid Daily_Impressions values found: {impression_failures[:5]}")
    else:
        result.ok("All Daily_Impressions values are blank or integer-like.")

    if spend_type_failures:
        result.fail(f"Invalid Spend_Type values found: {spend_type_failures[:5]}")
    else:
        result.ok("All Spend_Type values use allowed enums.")

    if brand_failures:
        result.fail(f"Invalid Brand values found: {brand_failures[:5]}")
    else:
        result.ok("All Brand values use allowed canonical names.")

    if channel_failures:
        result.fail(f"Invalid Marketing_Channel values found: {channel_failures[:5]}")
    else:
        result.ok("All Marketing_Channel values use allowed standardized values.")


def parse_output_metrics(rows: list[dict[str, str]]) -> dict:
    spend_by_brand: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    impressions_by_brand: defaultdict[str, int] = defaultdict(int)
    blank_impressions_by_brand: defaultdict[str, int] = defaultdict(int)

    for row in rows:
        spend = parse_decimal(row["Daily_Spend"])
        if spend is not None:
            spend_by_brand[row["Brand"]] += spend
        if row["Daily_Impressions"]:
            impressions_by_brand[row["Brand"]] += int(row["Daily_Impressions"])
        else:
            blank_impressions_by_brand[row["Brand"]] += 1

    dates = [row["Date"] for row in rows]
    return {
        "row_count": len(rows),
        "brands": Counter(row["Brand"] for row in rows),
        "spend_by_brand": spend_by_brand,
        "impressions_by_brand": impressions_by_brand,
        "blank_impressions_by_brand": blank_impressions_by_brand,
        "min_date": min(dates) if dates else None,
        "max_date": max(dates) if dates else None,
    }


def compare_equal(actual, expected, success: str, failure: str, result: ValidationResult) -> None:
    if actual == expected:
        result.ok(success)
    else:
        result.fail(f"{failure}: expected {expected!r}, got {actual!r}")


def compare_decimal_equal(
    actual: Decimal,
    expected: Decimal,
    success: str,
    failure: str,
    result: ValidationResult,
) -> None:
    if actual == expected:
        result.ok(success)
    else:
        result.fail(
            f"{failure}: expected {decimal_to_str(expected)}, got {decimal_to_str(actual)}"
        )


def load_vendor_a_source() -> dict:
    workbook = load_workbook(INPUT_DIR / "Vendor_A_MediaWave_Jan2026.xlsx")
    input_schema = load_json(INPUT_A_SCHEMA_PATH)
    sheet = workbook["sheets"][next(
        sheet_name
        for sheet_name in workbook["sheet_order"]
        if sheet_name.startswith(input_schema["sheet_name_prefix"])
    )]
    records = [
        record
        for record in build_projected_records(sheet, input_schema["columns"])
        if record["Date"] != "TOTAL"
    ]
    numeric_impressions = [safe_int(record["Impressions"]) for record in records]
    parsed_dates = [parse_excel_date(record["Date"]) for record in records]
    return {
        "row_count": len(records),
        "spend_total": sum_decimal(
            [Decimal(str(safe_float(record["Net Spend (USD)"]) or 0)) for record in records]
        ),
        "impressions_total": sum(value or 0 for value in numeric_impressions),
        "blank_impressions": sum(1 for value in numeric_impressions if value is None),
        "min_date": min(parsed_dates),
        "max_date": max(parsed_dates),
    }


def validate_vendor_a(result: ValidationResult) -> None:
    rows = load_csv_rows(CSV_DIR / "vendor_a.csv", result)
    if not rows:
        return
    validate_global_rows(rows, result)
    metrics = parse_output_metrics(rows)
    source = load_vendor_a_source()

    compare_equal(
        metrics["row_count"],
        source["row_count"],
        "Vendor A row count matches source detail rows.",
        "Vendor A row count mismatch",
        result,
    )
    compare_decimal_equal(
        sum_decimal(list(metrics["spend_by_brand"].values())),
        source["spend_total"],
        "Vendor A spend total matches source net spend.",
        "Vendor A spend total mismatch",
        result,
    )
    compare_equal(
        sum(metrics["impressions_by_brand"].values()),
        source["impressions_total"],
        "Vendor A impressions total matches source numeric impressions.",
        "Vendor A impressions total mismatch",
        result,
    )
    compare_equal(
        sum(metrics["blank_impressions_by_brand"].values()),
        source["blank_impressions"],
        "Vendor A blank-impression count matches source invalid impressions.",
        "Vendor A blank-impression count mismatch",
        result,
    )
    compare_equal(
        metrics["min_date"],
        source["min_date"],
        "Vendor A minimum date matches source.",
        "Vendor A minimum date mismatch",
        result,
    )
    compare_equal(
        metrics["max_date"],
        source["max_date"],
        "Vendor A maximum date matches source.",
        "Vendor A maximum date mismatch",
        result,
    )

    allowed_vendor = {row["Vendor"] for row in rows}
    allowed_channel = {row["Marketing_Channel"] for row in rows}
    allowed_spend_type = {row["Spend_Type"] for row in rows}
    compare_equal(
        allowed_vendor,
        {"MediaWave"},
        "Vendor A vendor values are correct.",
        "Vendor A vendor values mismatch",
        result,
    )
    compare_equal(
        allowed_channel,
        {"CTV"},
        "Vendor A marketing channel is correct.",
        "Vendor A marketing channel mismatch",
        result,
    )
    compare_equal(
        allowed_spend_type,
        {"Actual"},
        "Vendor A spend type is correct.",
        "Vendor A spend type mismatch",
        result,
    )


def load_vendor_b_source() -> dict:
    workbook = load_workbook(INPUT_DIR / "Vendor_B_StreetLevel_Jan2026.xlsx")
    input_schema = load_json(INPUT_B_SCHEMA_PATH)
    sheet = workbook["sheets"][input_schema["sheet_name"]]
    weekly = [
        row
        for row in build_projected_records(sheet, input_schema["weekly_table"]["columns"])
        if parse_excel_date(row["Week Starting"]) is not None
    ]

    week_starts = [parse_excel_date(row["Week Starting"]) for row in weekly]
    month_total = safe_float(row_values(sheet, 29, columns=["E"], include_missing=True)["E"]) or 0.0
    wagerline_total = safe_float(row_values(sheet, 2, columns=["H"], include_missing=True)["H"]) or 0.0
    neonspin_total = safe_float(row_values(sheet, 3, columns=["H"], include_missing=True)["H"]) or 0.0
    return {
        "stake_spend": sum_decimal(
            [Decimal(str(safe_float(row["Cost"]) or 0)) for row in weekly]
        ),
        "stake_impressions": sum(safe_int(row["Est. Impressions"]) or 0 for row in weekly),
        "wagerline_spend": Decimal(str(wagerline_total)),
        "neonspin_spend": Decimal(str(neonspin_total)),
        "monthly_total": Decimal(str(month_total)),
        "min_date": min(week_starts),
        "max_date": (datetime.strptime(max(week_starts), "%Y-%m-%d").date() + timedelta(days=6)).isoformat(),
    }


def validate_vendor_b(result: ValidationResult) -> None:
    rows = load_csv_rows(CSV_DIR / "vendor_b.csv", result)
    if not rows:
        return
    validate_global_rows(rows, result)
    metrics = parse_output_metrics(rows)
    source = load_vendor_b_source()

    compare_decimal_equal(
        metrics["spend_by_brand"]["StakePoint"],
        source["stake_spend"],
        "Vendor B StakePoint spend matches weekly cost total.",
        "Vendor B StakePoint spend mismatch",
        result,
    )
    compare_equal(
        metrics["impressions_by_brand"]["StakePoint"],
        source["stake_impressions"],
        "Vendor B StakePoint impressions match weekly estimated impressions.",
        "Vendor B StakePoint impressions mismatch",
        result,
    )
    compare_decimal_equal(
        metrics["spend_by_brand"]["WagerLine"],
        source["wagerline_spend"],
        "Vendor B WagerLine spend matches aggregate side-table total.",
        "Vendor B WagerLine spend mismatch",
        result,
    )
    compare_decimal_equal(
        metrics["spend_by_brand"]["NeonSpin"],
        source["neonspin_spend"],
        "Vendor B NeonSpin spend matches aggregate side-table total.",
        "Vendor B NeonSpin spend mismatch",
        result,
    )
    compare_equal(
        metrics["impressions_by_brand"].get("WagerLine", 0),
        0,
        "Vendor B WagerLine impressions are blank for all rows.",
        "Vendor B WagerLine impressions should be blank",
        result,
    )
    compare_equal(
        metrics["impressions_by_brand"].get("NeonSpin", 0),
        0,
        "Vendor B NeonSpin impressions are blank for all rows.",
        "Vendor B NeonSpin impressions should be blank",
        result,
    )
    compare_decimal_equal(
        sum_decimal(list(metrics["spend_by_brand"].values())),
        source["monthly_total"],
        "Vendor B combined spend matches workbook monthly total.",
        "Vendor B combined spend mismatch against monthly total",
        result,
    )
    compare_equal(
        metrics["min_date"],
        source["min_date"],
        "Vendor B minimum date matches earliest source week start.",
        "Vendor B minimum date mismatch",
        result,
    )
    compare_equal(
        metrics["max_date"],
        source["max_date"],
        "Vendor B maximum date matches latest source week plus six days.",
        "Vendor B maximum date mismatch",
        result,
    )

    vendors = {row["Vendor"] for row in rows}
    channels = {row["Marketing_Channel"] for row in rows}
    spend_types = {row["Spend_Type"] for row in rows}
    compare_equal(
        vendors,
        {"StreetLevel OOH"},
        "Vendor B vendor values are correct.",
        "Vendor B vendor values mismatch",
        result,
    )
    compare_equal(
        channels,
        {"DOOH"},
        "Vendor B marketing channel is correct.",
        "Vendor B marketing channel mismatch",
        result,
    )
    compare_equal(
        spend_types,
        {"Proportioned"},
        "Vendor B spend type is correct.",
        "Vendor B spend type mismatch",
        result,
    )


def load_vendor_c_source() -> dict:
    workbook = load_workbook(INPUT_DIR / "Vendor_C_AudioBlast_Jan2026.xlsx")
    input_schema = load_json(INPUT_C_SCHEMA_PATH)
    sheet = workbook["sheets"][input_schema["sheet_name"]]
    columns = input_schema["columns"]
    letters = [column["letter"] for column in columns]
    names = [column["name"] for column in columns]

    header_row = None
    expected_header = [column["name"] for column in columns]
    for row_number in sorted(sheet.rows):
        row = row_values(sheet, row_number, columns=letters, include_missing=True)
        if [row.get(letter) for letter in letters] == expected_header:
            header_row = row_number
            break
    if header_row is None:
        raise ValueError("Vendor C header row was not found.")

    records = []
    note_counter = Counter()
    for row_number in sorted(sheet.rows):
        if row_number <= header_row:
            continue
        row = row_values(sheet, row_number, columns=letters, include_missing=True)
        record = dict(zip(names, [row.get(letter) for letter in letters]))
        if parse_week_label(record["Week"], year=2026) is None:
            continue
        if (record["Show / Placement"] or "").strip() in {"Subtotal", "GRAND TOTAL - ALL SHOWS"}:
            continue
        records.append(record)
        note = (record["Notes"] or "").strip()
        if "Cancelled" in note:
            note_counter["Cancelled"] += 1
        if "Makeweight" in note:
            note_counter["Makeweight"] += 1

    week_starts = [parse_week_label(record["Week"], year=2026) for record in records]
    source_total_spend = sum_decimal(
        [Decimal(str(safe_float(record["Total Spend"]) or 0)) for record in records]
    )
    source_downloads = sum(safe_int(record["Downloads (est.)"]) or 0 for record in records)
    stake_spend = sum_decimal(
        [Decimal(str(safe_float(record["StakePoint Spend"]) or 0)) for record in records]
    )
    wagerline_spend = sum_decimal(
        [Decimal(str(safe_float(record["WagerLine Spend"]) or 0)) for record in records]
    )
    total_spend_mismatch_count = 0
    for record in records:
        raw_total_spend = Decimal(str(safe_float(record["Total Spend"]) or 0))
        derived_total_spend = Decimal(str(safe_float(record["StakePoint Spend"]) or 0)) + Decimal(
            str(safe_float(record["WagerLine Spend"]) or 0)
        )
        if raw_total_spend != derived_total_spend:
            total_spend_mismatch_count += 1
    return {
        "row_count": len(records),
        "spend_total": source_total_spend,
        "downloads_total": source_downloads,
        "stake_spend_total": stake_spend,
        "wagerline_spend_total": wagerline_spend,
        "combined_brand_spend_total": stake_spend + wagerline_spend,
        "raw_total_spend_mismatch_count": total_spend_mismatch_count,
        "min_date": min(week_starts),
        "max_date": (datetime.strptime(max(week_starts), "%Y-%m-%d").date() + timedelta(days=6)).isoformat(),
        "notes": note_counter,
    }


def validate_vendor_c(result: ValidationResult) -> None:
    rows = load_csv_rows(CSV_DIR / "vendor_c.csv", result)
    if not rows:
        return
    validate_global_rows(rows, result)
    metrics = parse_output_metrics(rows)
    source = load_vendor_c_source()

    expected_rows = source["row_count"] * 2 * 7
    compare_equal(
        metrics["row_count"],
        expected_rows,
        "Vendor C row count matches source rows expanded to 2 brands x 7 days.",
        "Vendor C row count mismatch",
        result,
    )
    compare_decimal_equal(
        metrics["spend_by_brand"]["StakePoint"],
        source["stake_spend_total"],
        "Vendor C StakePoint spend matches source StakePoint Spend.",
        "Vendor C StakePoint spend mismatch",
        result,
    )
    compare_decimal_equal(
        metrics["spend_by_brand"]["WagerLine"],
        source["wagerline_spend_total"],
        "Vendor C WagerLine spend matches source WagerLine Spend.",
        "Vendor C WagerLine spend mismatch",
        result,
    )
    compare_decimal_equal(
        sum_decimal(list(metrics["spend_by_brand"].values())),
        source["combined_brand_spend_total"],
        "Vendor C combined spend matches the sum of source brand-specific spend columns.",
        "Vendor C combined spend mismatch against source brand-specific columns",
        result,
    )
    compare_equal(
        sum(metrics["impressions_by_brand"].values()),
        source["downloads_total"],
        "Vendor C combined impressions match source Downloads (est.).",
        "Vendor C combined impressions mismatch",
        result,
    )
    compare_equal(
        metrics["min_date"],
        source["min_date"],
        "Vendor C minimum date matches earliest parsed source week.",
        "Vendor C minimum date mismatch",
        result,
    )
    compare_equal(
        metrics["max_date"],
        source["max_date"],
        "Vendor C maximum date matches latest source week plus six days.",
        "Vendor C maximum date mismatch",
        result,
    )
    compare_equal(
        {row["Vendor"] for row in rows},
        {"AudioBlast Media"},
        "Vendor C vendor values are correct.",
        "Vendor C vendor values mismatch",
        result,
    )
    compare_equal(
        {row["Marketing_Channel"] for row in rows},
        {"Podcast/Audio"},
        "Vendor C marketing channel is correct.",
        "Vendor C marketing channel mismatch",
        result,
    )
    compare_equal(
        {row["Spend_Type"] for row in rows},
        {"Proportioned"},
        "Vendor C spend type is correct.",
        "Vendor C spend type mismatch",
        result,
    )
    compare_equal(
        metrics["brands"],
        Counter({"StakePoint": source["row_count"] * 7, "WagerLine": source["row_count"] * 7}),
        "Vendor C expands each source row to both brands across seven dates.",
        "Vendor C brand expansion mismatch",
        result,
    )

    if source["raw_total_spend_mismatch_count"] > 0:
        result.warn(
            "Vendor C source has rows where raw Total Spend does not equal "
            "StakePoint Spend + WagerLine Spend "
            f"(mismatch rows: {source['raw_total_spend_mismatch_count']}). "
            "Validation treats brand-specific spend columns as the source of truth."
        )
    else:
        result.ok("Vendor C raw Total Spend column is consistent with brand-specific spend columns.")

    if source["notes"]["Cancelled"] or source["notes"]["Makeweight"]:
        result.warn(
            "Vendor C source contains note-driven edge cases "
            f"(Cancelled={source['notes']['Cancelled']}, Makeweight={source['notes']['Makeweight']}). "
            "Downloads are allocated by spend weights, with fallbacks for zero-total rows."
        )
    else:
        result.ok("Vendor C source contains no cancelled or makeweight note rows.")


def print_result(result: ValidationResult) -> None:
    print(f"[{result.status}] {result.vendor}")
    for check in result.checks:
        print(f"  OK: {check}")
    for warning in result.warnings:
        print(f"  WARN: {warning}")
    for failure in result.failures:
        print(f"  FAIL: {failure}")
    print()


def main() -> int:
    results = [
        ValidationResult("Vendor A"),
        ValidationResult("Vendor B"),
        ValidationResult("Vendor C"),
    ]

    validate_vendor_a(results[0])
    validate_vendor_b(results[1])
    validate_vendor_c(results[2])

    for result in results:
        print_result(result)

    if any(result.failures for result in results):
        print("Validation summary: FAIL")
        return 1

    if any(result.warnings for result in results):
        print("Validation summary: PASS with WARN")
    else:
        print("Validation summary: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

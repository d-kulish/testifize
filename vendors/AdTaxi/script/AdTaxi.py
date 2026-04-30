from __future__ import annotations

import csv
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

INPUT_SCHEMA_PATH = SCRIPT_DIR / "input_schema.json"
OUTPUT_SCHEMA_PATH = PROJECT_ROOT / "test" / "scripts" / "schemas" / "output_schema.json"
OUTPUT_PATH = SCRIPT_DIR / "AdTaxi.csv"
REPORT_PATH = SCRIPT_DIR / "AdTaxi_comparison_report.md"
FINAL_ADTAXI_PATH = PROJECT_ROOT / "final" / "AdTaxi.csv"

FRICTION_SOURCE_TOKEN = "Friction_Digital_9.1.24_10.31.25"
SPEND_TOLERANCE = Decimal("0.005")
IMPRESSION_TOLERANCE = Decimal("0")


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_output_columns() -> list[str]:
    schema = load_json(OUTPUT_SCHEMA_PATH)
    return [column["name"] for column in schema["target_output_schema"]]


def parse_date(value: str, row_number: int) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"Missing Date at source row {row_number}.")

    for date_format in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(text).date().isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid Date at source row {row_number}: {value!r}") from exc


def parse_decimal(value: str | None, row_number: int, column_name: str) -> Decimal:
    text = (value or "").strip()
    if not text:
        raise ValueError(f"Missing {column_name} at row {row_number}.")

    negative = text.startswith("(") and text.endswith(")")
    cleaned = text.strip("()").replace("$", "").replace(",", "")
    try:
        parsed = Decimal(cleaned)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"Invalid {column_name} at row {row_number}: {value!r}") from exc

    if negative:
        parsed = -parsed
    if parsed < 0:
        raise ValueError(f"Negative {column_name} at row {row_number}: {value!r}")
    return parsed


def parse_impressions(value: str | None, row_number: int, column_name: str) -> int:
    parsed = parse_decimal(value, row_number, column_name)
    if parsed != parsed.to_integral_value():
        raise ValueError(f"Non-integer {column_name} at row {row_number}: {value!r}")
    return int(parsed)


def validate_required_columns(fieldnames: list[str] | None, required_columns: list[str], path: Path) -> None:
    if not fieldnames:
        raise ValueError(f"{path} has no header row.")

    missing = [column for column in required_columns if column not in fieldnames]
    if missing:
        raise ValueError(f"{path.name} is missing required columns: {missing}")


def build_daily_rows() -> list[dict[str, object]]:
    input_schema = load_json(INPUT_SCHEMA_PATH)
    source_path = (SCRIPT_DIR / input_schema["source_file"]).resolve()
    selected = input_schema["selected_columns"]
    defaults = input_schema["output_defaults"]
    allowed_currencies = set(
        input_schema["validations"]["Advertiser Currency Code"]["allowed_values"]
    )

    daily_spend: defaultdict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    daily_impressions: defaultdict[str, int] = defaultdict(int)

    with source_path.open(newline="", encoding=input_schema.get("encoding", "utf-8")) as handle:
        reader = csv.DictReader(handle)
        validate_required_columns(reader.fieldnames, input_schema["required_columns"], source_path)

        for row_number, row in enumerate(reader, start=2):
            currency = (row[selected["currency"]] or "").strip()
            if currency not in allowed_currencies:
                raise ValueError(
                    f"Unexpected currency at source row {row_number}: {currency!r}"
                )

            date = parse_date(row[selected["date"]], row_number)
            daily_spend[date] += parse_decimal(row[selected["spend"]], row_number, selected["spend"])
            daily_impressions[date] += parse_impressions(
                row[selected["impressions"]],
                row_number,
                selected["impressions"],
            )

    rows: list[dict[str, object]] = []
    for date in sorted(daily_spend):
        rows.append(
            {
                "Date": date,
                "Vendor": defaults["Vendor"],
                "Brand": defaults["Brand"],
                "Campaign": defaults["Campaign"],
                "Marketing_Channel": defaults["Marketing_Channel"],
                "Sub_Channel": defaults["Sub_Channel"],
                "Daily_Spend": daily_spend[date].quantize(Decimal("0.01")),
                "Daily_Impressions": daily_impressions[date],
                "Spend_Type": defaults["Spend_Type"],
            }
        )

    if not rows:
        raise ValueError(f"No rows were parsed from {source_path}.")
    return rows


def write_csv(rows: list[dict[str, object]]) -> None:
    fieldnames = load_output_columns()
    with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output_row = dict(row)
            output_row["Daily_Spend"] = f"{row['Daily_Spend']:.2f}"
            writer.writerow(output_row)


def load_generated_daily() -> dict[str, dict[str, Decimal]]:
    daily: dict[str, dict[str, Decimal]] = {}
    with OUTPUT_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row_number, row in enumerate(reader, start=2):
            date = row["Date"]
            daily[date] = {
                "spend": parse_decimal(row["Daily_Spend"], row_number, "Daily_Spend"),
                "impressions": Decimal(
                    parse_impressions(row["Daily_Impressions"], row_number, "Daily_Impressions")
                ),
            }
    return daily


def load_benchmark_daily() -> dict[str, dict[str, Decimal]]:
    daily: defaultdict[str, dict[str, Decimal]] = defaultdict(
        lambda: {"spend": Decimal("0"), "impressions": Decimal("0")}
    )

    with FINAL_ADTAXI_PATH.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = ["Date", "Spend", "Impressions", "Source_File"]
        validate_required_columns(reader.fieldnames, required, FINAL_ADTAXI_PATH)

        for row_number, row in enumerate(reader, start=2):
            if FRICTION_SOURCE_TOKEN not in (row.get("Source_File") or ""):
                continue

            date = row["Date"]
            daily[date]["spend"] += parse_decimal(row["Spend"], row_number, "Spend")
            daily[date]["impressions"] += parse_decimal(
                row["Impressions"],
                row_number,
                "Impressions",
            )

    if not daily:
        raise ValueError(
            f"No benchmark rows containing {FRICTION_SOURCE_TOKEN!r} were found in "
            f"{FINAL_ADTAXI_PATH}."
        )

    return dict(daily)


def summarize_daily(daily: dict[str, dict[str, Decimal]]) -> dict[str, object]:
    dates = sorted(daily)
    return {
        "rows": len(daily),
        "min_date": dates[0] if dates else "",
        "max_date": dates[-1] if dates else "",
        "spend": sum((values["spend"] for values in daily.values()), Decimal("0")),
        "impressions": sum(
            (values["impressions"] for values in daily.values()),
            Decimal("0"),
        ),
    }


def compare_daily(
    generated: dict[str, dict[str, Decimal]],
    benchmark: dict[str, dict[str, Decimal]],
) -> dict[str, object]:
    generated_dates = set(generated)
    benchmark_dates = set(benchmark)
    shared_dates = sorted(generated_dates & benchmark_dates)

    max_spend_diff = Decimal("0")
    max_impression_diff = Decimal("0")
    differing_rows = []

    for date in shared_dates:
        spend_diff = generated[date]["spend"] - benchmark[date]["spend"]
        impression_diff = generated[date]["impressions"] - benchmark[date]["impressions"]
        max_spend_diff = max(max_spend_diff, abs(spend_diff))
        max_impression_diff = max(max_impression_diff, abs(impression_diff))
        if abs(spend_diff) > SPEND_TOLERANCE or abs(impression_diff) > IMPRESSION_TOLERANCE:
            differing_rows.append(
                {
                    "Date": date,
                    "Generated Spend": generated[date]["spend"],
                    "Benchmark Spend": benchmark[date]["spend"],
                    "Spend Diff": spend_diff,
                    "Generated Impressions": generated[date]["impressions"],
                    "Benchmark Impressions": benchmark[date]["impressions"],
                    "Impressions Diff": impression_diff,
                }
            )

    return {
        "generated_summary": summarize_daily(generated),
        "benchmark_summary": summarize_daily(benchmark),
        "missing_dates": sorted(benchmark_dates - generated_dates),
        "extra_dates": sorted(generated_dates - benchmark_dates),
        "max_spend_diff": max_spend_diff,
        "max_impression_diff": max_impression_diff,
        "differing_rows": differing_rows,
    }


def decimal_text(value: Decimal, places: str = "0.01") -> str:
    return f"{value.quantize(Decimal(places))}"


def write_report(comparison: dict[str, object]) -> None:
    generated = comparison["generated_summary"]
    benchmark = comparison["benchmark_summary"]
    missing_dates = comparison["missing_dates"]
    extra_dates = comparison["extra_dates"]
    differing_rows = comparison["differing_rows"]
    max_spend_diff = comparison["max_spend_diff"]
    max_impression_diff = comparison["max_impression_diff"]

    lines = [
        "# AdTaxi Friction Comparison Report",
        "",
        "## Summary",
        "",
        "| Metric | Generated AdTaxi.csv | Final Friction slice |",
        "|---|---:|---:|",
        f"| Rows | {generated['rows']} | {benchmark['rows']} |",
        f"| Date range | {generated['min_date']} to {generated['max_date']} | "
        f"{benchmark['min_date']} to {benchmark['max_date']} |",
        f"| Total spend | {decimal_text(generated['spend'])} | "
        f"{decimal_text(benchmark['spend'])} |",
        f"| Total impressions | {int(generated['impressions'])} | "
        f"{int(benchmark['impressions'])} |",
        "",
        "## Date Coverage",
        "",
        f"- Missing dates from generated output: {len(missing_dates)}",
        f"- Extra dates in generated output: {len(extra_dates)}",
        "",
        "## Difference Checks",
        "",
        f"- Max absolute daily spend difference: {max_spend_diff}",
        f"- Max absolute daily impression difference: {max_impression_diff}",
        f"- Material differing dates: {len(differing_rows)}",
        "",
    ]

    if missing_dates:
        lines.extend(["### Missing Dates", "", ", ".join(missing_dates[:25]), ""])
    if extra_dates:
        lines.extend(["### Extra Dates", "", ", ".join(extra_dates[:25]), ""])

    if differing_rows:
        lines.extend(
            [
                "### Sample Differing Dates",
                "",
                "| Date | Generated Spend | Final Spend | Spend Diff | Generated Impressions | Final Impressions | Impression Diff |",
                "|---|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for row in differing_rows[:10]:
            lines.append(
                f"| {row['Date']} | {decimal_text(row['Generated Spend'])} | "
                f"{decimal_text(row['Benchmark Spend'])} | {row['Spend Diff']} | "
                f"{int(row['Generated Impressions'])} | "
                f"{int(row['Benchmark Impressions'])} | "
                f"{int(row['Impressions Diff'])} |"
            )
        lines.append("")
    else:
        lines.extend(
            [
                "No material daily differences were found between the generated output "
                "and the Friction Digital slice in `final/AdTaxi.csv`.",
                "",
            ]
        )

    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    rows = build_daily_rows()
    write_csv(rows)

    generated = load_generated_daily()
    benchmark = load_benchmark_daily()
    comparison = compare_daily(generated, benchmark)
    write_report(comparison)

    print(f"Wrote {len(rows)} rows to {OUTPUT_PATH}")
    print(f"Wrote comparison report to {REPORT_PATH}")


if __name__ == "__main__":
    main()

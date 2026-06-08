from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.db.models import Count, Max
from django.utils import timezone

from .models import Asset, AssetEvent, AssetStatus, ParsedOutput, ShareFileFolder, Vendor


@dataclass(frozen=True)
class VendorParserHealth:
    has_schema: bool
    has_parser: bool
    schema_path: str
    parser_path: str

    @property
    def ok(self) -> bool:
        return self.has_schema and self.has_parser

    @property
    def label(self) -> str:
        return "Ready" if self.ok else "Missing"

    @property
    def badge_class(self) -> str:
        return "passed" if self.ok else "failed"


def build_vendor_page_context() -> dict[str, Any]:
    vendors = list(Vendor.objects.order_by("name"))
    vendor_rows = [vendor_summary(vendor) for vendor in vendors]
    folders = list(ShareFileFolder.objects.select_related("vendor").order_by("label"))
    metrics = {
        "vendors": len(vendor_rows),
        "active": sum(1 for row in vendor_rows if row.vendor.is_active),
        "parser_ready": sum(1 for row in vendor_rows if row.parser.ok),
        "folders": len(folders),
        "observed_people": len({person.email or person.name for row in vendor_rows for person in row.people}),
    }
    month_labels, history_coverage = _compute_vendor_coverage(vendors)
    return {
        "title": "Vendors",
        "active_nav": "vendors",
        "vendor_rows": vendor_rows,
        "folders": folders,
        "all_vendors": vendors,
        "metrics": metrics,
        "history_months": month_labels,
        "history_coverage": history_coverage,
    }


def _compute_vendor_coverage(vendors: list[Vendor]) -> tuple[list[str], dict[str, list[str]]]:
    approved_outputs = list(
        ParsedOutput.objects.select_related("vendor")
        .filter(comparison_status="approved")
        .order_by("vendor__name", "-created_at")
    )

    today = timezone.localdate()
    month_window = []
    year, month = today.year, today.month
    for _ in range(12):
        month_window.insert(0, date(year, month, 1))
        month -= 1
        if month == 0:
            month = 12
            year -= 1

    month_ends = []
    for m in month_window:
        _, last_day = calendar.monthrange(m.year, m.month)
        month_ends.append(date(m.year, m.month, last_day))

    month_labels = [m.strftime("%b %y") for m in month_window]

    history_coverage: dict[str, list[str]] = {}
    if approved_outputs:
        outputs_with_periods = [
            o for o in approved_outputs if o.period_start and o.period_end
        ]
        vendor_ids = {o.vendor_id for o in approved_outputs}
        for vid in vendor_ids:
            covered = set()
            vendor_outputs = [o for o in outputs_with_periods if o.vendor_id == vid]
            for idx, (m_start, m_end) in enumerate(zip(month_window, month_ends)):
                for o in vendor_outputs:
                    if o.period_start <= m_end and o.period_end >= m_start:
                        covered.add(idx)
                        break
            key = str(vid) if vid is not None else "none"
            history_coverage[key] = [
                "current" if idx == 11 else "covered" if idx in covered else "missing"
                for idx in range(12)
            ]

    return month_labels, history_coverage


def vendor_summary(vendor: Vendor) -> SimpleNamespace:
    status_counts = {
        row["status"]: row["count"]
        for row in Asset.objects.filter(vendor=vendor).values("status").annotate(count=Count("remote_item_id"))
    }
    parsed_counts = {
        row["comparison_status"]: row["count"]
        for row in ParsedOutput.objects.filter(vendor=vendor).values("comparison_status").annotate(count=Count("id"))
    }
    last_asset = (
        Asset.objects.filter(vendor=vendor)
        .order_by("-remote_modified_at", "-last_seen_at", "name")
        .first()
    )
    recent_assets = list(
        Asset.objects.filter(vendor=vendor)
        .select_related("source_folder")
        .order_by("-remote_modified_at", "-last_seen_at", "name")[:5]
    )
    recent_events = list(
        AssetEvent.objects.filter(asset__vendor=vendor)
        .select_related("asset")
        .order_by("-created_at", "-id")[:5]
    )
    people = observed_people(vendor)
    return SimpleNamespace(
        vendor=vendor,
        parser=parser_health(vendor),
        status_counts=status_counts,
        parsed_counts=parsed_counts,
        folders=list(vendor.folders.order_by("label")),
        folder_count=vendor.folders.count(),
        asset_count=sum(status_counts.values()),
        review_count=status_counts.get(AssetStatus.REVIEW, 0),
        processing_count=status_counts.get(AssetStatus.PROCESSING, 0),
        processed_count=status_counts.get(AssetStatus.PROCESSED, 0) + status_counts.get(AssetStatus.UPLOADED, 0),
        approval_count=parsed_counts.get("sent_for_approval", 0),
        approved_count=parsed_counts.get("approved", 0),
        cancelled_count=parsed_counts.get("cancelled", 0),
        last_asset=last_asset,
        latest_activity_at=latest_activity_at(vendor),
        people=people,
        recent_assets=recent_assets,
        recent_events=recent_events,
        can_delete=can_delete_vendor(vendor),
        health_badges=health_badges(vendor, status_counts, parsed_counts, people),
    )


def parser_health(vendor: Vendor) -> VendorParserHealth:
    parser_root = settings.REPO_ROOT / "parsers" / vendor.name
    schema_path = parser_root / "input_schema.json"
    parser_path = parser_root / "parser.py"
    return VendorParserHealth(
        has_schema=schema_path.exists(),
        has_parser=parser_path.exists(),
        schema_path=display_path(schema_path),
        parser_path=display_path(parser_path),
    )


def observed_people(vendor: Vendor) -> list[SimpleNamespace]:
    rows = (
        Asset.objects.filter(vendor=vendor)
        .exclude(created_by_name="", created_by_email="")
        .values("created_by_name", "created_by_email")
        .annotate(upload_count=Count("remote_item_id"), last_upload=Max("remote_modified_at"))
        .order_by("-last_upload", "created_by_name", "created_by_email")
    )
    people = []
    for row in rows:
        name = row["created_by_name"] or row["created_by_email"] or "Unknown"
        email = row["created_by_email"] or ""
        people.append(
            SimpleNamespace(
                name=name,
                email=email,
                upload_count=row["upload_count"],
                last_upload=row["last_upload"],
            )
        )
    return people


def latest_activity_at(vendor: Vendor):
    latest_event = (
        AssetEvent.objects.filter(asset__vendor=vendor)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    latest_parsed = (
        ParsedOutput.objects.filter(vendor=vendor)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )
    values = [value for value in [latest_event, latest_parsed] if value]
    return max(values) if values else None


def can_delete_vendor(vendor: Vendor) -> bool:
    return (
        not vendor.folders.exists()
        and not vendor.assets.exists()
        and not vendor.parsed_outputs.exists()
    )


def health_badges(
    vendor: Vendor,
    status_counts: dict[str, int],
    parsed_counts: dict[str, int],
    people: list[SimpleNamespace],
) -> list[dict[str, str]]:
    badges = []
    if not vendor.is_active:
        badges.append({"label": "Inactive", "class": "ignored"})
    if not parser_health(vendor).ok:
        badges.append({"label": "Parser missing", "class": "failed"})
    if not vendor.folders.exists():
        badges.append({"label": "No folders", "class": "queued"})
    if status_counts.get(AssetStatus.REVIEW, 0) or parsed_counts.get("sent_for_approval", 0):
        badges.append({"label": "Review pending", "class": "review"})
    if not people:
        badges.append({"label": "No observed users", "class": "queued"})
    return badges or [{"label": "Healthy", "class": "passed"}]


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(settings.REPO_ROOT))
    except ValueError:
        return str(path)

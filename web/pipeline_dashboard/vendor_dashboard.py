from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.db.models import Count, Max, Q
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
    for row in vendor_rows:
        key = str(row.vendor.id) if row.vendor else "none"
        coverage = history_coverage.get(key, ["missing"] * 12)
        gap = 12
        for idx in range(11, -1, -1):
            if coverage[idx] == "covered":
                gap = 11 - idx
                break
        row.gap_months = gap
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


def _build_histogram_maturity(vendor: Vendor, cutoff_date: date) -> list[dict[str, Any]]:
    """Build a 240-day pipeline-maturity timeline.

    Each day shows the highest stage any of the vendor's files reached on
    that day.  Backward moves are ignored (once a stage is reached the file
    never drops below it).

    Milestones (colour a single day only):
        1 submitted  – raw file uploaded to ShareFile
        4 approved   – file approved and stored in Final/

    Active periods (colour every day from first occurrence until the next
    higher stage begins):
        2 parsing    – file entered downloading / processing / uploading
        3 approval   – file sent for external approval (review status)
    """
    dates = [cutoff_date + timedelta(days=i) for i in range(240)]
    date_to_stage: dict[date, int] = {d: 0 for d in dates}

    SUBMITTED = 1
    PARSING = 2
    APPROVAL = 3
    APPROVED = 4

    PARSING_STATUSES = {
        AssetStatus.DOWNLOADING,
        AssetStatus.DOWNLOADED,
        AssetStatus.PROCESSING,
        AssetStatus.UPLOADING,
    }

    # All assets for this vendor.
    assets = Asset.objects.filter(vendor=vendor)

    # Batch-load all events, ordered chronologically.
    all_events = list(
        AssetEvent.objects.filter(asset__vendor=vendor)
        .order_by("created_at")
        .values("asset_id", "created_at", "to_status", "event_type")
    )
    events_by_asset: dict[str, list[dict]] = {}
    for evt in all_events:
        events_by_asset.setdefault(evt["asset_id"], []).append(evt)

    for asset in assets.iterator():
        # Build chronological transitions for this asset.
        transitions: list[tuple[date, int]] = []

        if asset.remote_created_at:
            transitions.append((asset.remote_created_at.date(), SUBMITTED))

        for evt in events_by_asset.get(asset.remote_item_id, []):
            to_status = evt["to_status"]
            event_type = evt["event_type"]
            stage: int | None = None
            # Check final_approved first: its to_status is PROCESSED, which
            # would otherwise be swallowed by PARSING_STATUSES.
            if event_type == "final_approved":
                stage = APPROVED
            elif to_status == AssetStatus.REVIEW or event_type == "approval_sent":
                stage = APPROVAL
            elif to_status in PARSING_STATUSES:
                stage = PARSING
            if stage is not None:
                transitions.append((evt["created_at"].date(), stage))

        # Sort by date.
        transitions.sort(key=lambda x: x[0])

        # Deduplicate same-day transitions, keeping the max stage.
        deduped: list[tuple[date, int]] = []
        for d, stage in transitions:
            if deduped and deduped[-1][0] == d:
                deduped[-1] = (d, max(deduped[-1][1], stage))
            else:
                deduped.append((d, stage))

        # Walk through transitions, maintaining cumulative stage (no backward).
        current_stage = 0
        for i, (trans_date, stage) in enumerate(deduped):
            # Ignore backward moves.
            if stage < current_stage:
                continue
            current_stage = stage

            if stage == SUBMITTED:
                # Submitted is a one-day milestone only.
                if trans_date in date_to_stage:
                    date_to_stage[trans_date] = max(date_to_stage[trans_date], SUBMITTED)
                continue

            if stage == APPROVED:
                # Approved is a one-day finish milestone.
                if trans_date in date_to_stage:
                    date_to_stage[trans_date] = max(date_to_stage[trans_date], APPROVED)
                # After approval the asset contributes nothing further.
                break

            # Determine end date for this stage (exclusive).
            next_date = deduped[i + 1][0] if i + 1 < len(deduped) else None

            # Colour every day from trans_date up to (but not including) next_date.
            d = trans_date
            while d in date_to_stage:
                if next_date is not None and d >= next_date:
                    break
                date_to_stage[d] = max(date_to_stage[d], current_stage)
                d += timedelta(days=1)

    stage_names = {0: None, 1: "submitted", 2: "parsing", 3: "approval", 4: "approved"}
    return [{"date": str(d), "stage": stage_names[date_to_stage[d]]} for d in dates]


def build_vendor_detail_payload(vendor: Vendor) -> dict[str, Any]:
    """Assemble all Phase 1 Details-tab panels from existing models."""
    today = timezone.localdate()
    cutoff_date = today - timedelta(days=239)

    # Panel A: 240-day pipeline maturity histogram
    histogram = _build_histogram_maturity(vendor, cutoff_date)

    people = observed_people(vendor)

    # Panel C: Recent raw files
    recent_assets = list(
        Asset.objects.filter(vendor=vendor)
        .select_related("source_folder")
        .order_by("-remote_modified_at")[:20]
    )

    # Panel D: Approval queue
    approval_files = list(
        ParsedOutput.objects.filter(vendor=vendor, comparison_status="sent_for_approval")
        .select_related("asset")
        .order_by("-created_at")[:5]
    )

    # Panel E: Approved history
    history_files = list(
        ParsedOutput.objects.filter(vendor=vendor, comparison_status="approved")
        .select_related("asset")
        .order_by("-created_at")[:5]
    )

    # Panel F: Activity stream
    events = list(
        AssetEvent.objects.filter(asset__vendor=vendor)
        .select_related("asset")
        .order_by("-created_at")[:20]
    )

    return {
        "histogram": histogram,
        "people": [
            {
                "name": p.name,
                "email": p.email,
                "upload_count": p.upload_count,
                "last_upload": p.last_upload.isoformat() if p.last_upload else None,
            }
            for p in people
        ],
        "assets": [
            {
                "remote_item_id": a.remote_item_id,
                "name": a.name,
                "status": a.status,
                "file_size": a.file_size,
                "remote_modified_at": a.remote_modified_at.isoformat() if a.remote_modified_at else None,
                "uploader": a.created_by_display or "Unknown",
                "folder": a.source_folder.label if a.source_folder else a.source_folder_label or "",
                "is_active": a.is_active,
                "duplicate_role": a.duplicate_role or "",
            }
            for a in recent_assets
        ],
        "approval": [
            {
                "id": p.id,
                "reporting_period": p.reporting_period,
                "version": p.version,
                "row_count": p.row_count,
                "total_spend": str(p.total_spend) if p.total_spend is not None else "0",
                "total_impressions": str(p.total_impressions) if p.total_impressions is not None else "0",
                "created_at": p.created_at.isoformat(),
                "asset_name": p.asset.name if p.asset else "",
            }
            for p in approval_files
        ],
        "history": [
            {
                "id": p.id,
                "reporting_period": p.reporting_period,
                "version": p.version,
                "row_count": p.row_count,
                "total_spend": str(p.total_spend) if p.total_spend is not None else "0",
                "total_impressions": str(p.total_impressions) if p.total_impressions is not None else "0",
                "created_at": p.created_at.isoformat(),
                "asset_name": p.asset.name if p.asset else "",
                "output_path": p.output_path,
            }
            for p in history_files
        ],
        "events": [
            {
                "created_at": e.created_at.isoformat(),
                "asset_name": e.asset.name,
                "asset_id": e.asset_id,
                "event_type": e.event_type,
                "from_status": e.from_status,
                "to_status": e.to_status,
                "message": e.message,
            }
            for e in events
        ],
    }

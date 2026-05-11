from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from .file_review import ReviewPreviewError, build_file_preview, inbox_file_path
from .models import Asset, AssetEvent, AssetStatus, ParsedOutput, ShareFileFolder, Vendor
from .parser_workflow import (
    ParserWorkflowError,
    build_parse_preview,
    build_parse_result_preview,
    final_period_label,
    final_processed_output_path,
    finalize_approved_output,
    stage_asset_parser,
    upload_approved_output,
)
from .sharefile_mirror import load_sharefile_mirror
from .services import set_asset_status


REVIEW_STATUSES = [
    AssetStatus.NEW,
    AssetStatus.FAILED,
    AssetStatus.QUEUED,
    AssetStatus.DOWNLOADED,
    AssetStatus.REVIEW,
    AssetStatus.SUPERSEDED,
    AssetStatus.IGNORED,
]

FOLDER_VENDOR_RULES = {
    "josh": ("PodcastOne", "Octopus", "Loop", "TVM", "TAIV"),
    "may_2026_internal_folders": ("RallyAdMedia", "AdTaxi"),
}

DASHBOARD_FILE_EXTENSIONS = {".csv", ".xls", ".xlsx"}
DASHBOARD_FINISHED_STATUSES = {
    AssetStatus.PROCESSED,
    AssetStatus.UPLOADED,
    AssetStatus.SUPERSEDED,
    AssetStatus.IGNORED,
}
DASHBOARD_SPENDING_VENDORS = ("Loop", "PodcastOne", "TVM", "TAIV")
DASHBOARD_SPENDING_EXAMPLE_PLANS = {
    "Loop": {
        "paid_start": -38,
        "paid_end": -9,
        "reported_start": -37,
        "reported_end": -10,
        "budget_multiplier": Decimal("1.05"),
    },
    "PodcastOne": {
        "paid_start": -30,
        "paid_end": 5,
        "reported_start": -28,
        "reported_end": 5,
        "budget_multiplier": Decimal("1.02"),
    },
    "TVM": {
        "paid_start": -16,
        "paid_end": 35,
        "reported_start": -16,
        "reported_end": -5,
        "budget_multiplier": Decimal("1.35"),
    },
    "TAIV": {
        "paid_start": -2,
        "paid_end": 38,
        "reported_start": -2,
        "reported_end": 7,
        "budget_multiplier": Decimal("1.28"),
    },
}


def dashboard(request):
    mirror = load_sharefile_mirror()
    status_counts = {
        row["status"]: row["count"]
        for row in Asset.objects.values("status").annotate(count=Count("remote_item_id"))
    }
    queue_assets = list(
        Asset.objects.select_related("vendor", "source_folder")
        .order_by("-remote_modified_at", "-last_seen_at", "name")[:18]
    )
    for asset in queue_assets:
        _decorate_dashboard_asset(asset)

    attention_assets = _dashboard_attention_assets(mirror.folders)
    spending = _dashboard_spending()

    context = {
        "title": "Testifize Pipeline",
        "dashboard_tabs": _dashboard_tabs(status_counts, mirror.summary),
        "mirror_summary": mirror.summary,
        "queue_assets": queue_assets,
        "attention_assets": attention_assets,
        "spending": spending,
        "active_nav": "dashboard",
    }
    return render(request, "pipeline_dashboard/dashboard.html", context)


def _dashboard_spending() -> SimpleNamespace:
    today = timezone.localdate()
    window_start = today - timedelta(days=40)
    window_end = today + timedelta(days=40)
    rows = []
    for vendor_name in DASHBOARD_SPENDING_VENDORS:
        parsed = (
            ParsedOutput.objects.select_related("asset", "vendor")
            .filter(vendor__name=vendor_name, comparison_status="approved")
            .order_by("-created_at", "-id")
            .first()
        )
        if parsed:
            rows.append(_spending_row(parsed, window_start, window_end))

    return SimpleNamespace(
        rows=rows,
        month_segments=_spending_month_segments(window_start, window_end),
        month_markers=_spending_month_markers(window_start, window_end),
        weekend_segments=_spending_weekend_segments(window_start, window_end),
        ticks=_spending_ticks(window_start, window_end),
        today_position=_timeline_center(today, window_start, window_end),
        window_start=window_start,
        window_end=window_end,
    )


def _spending_row(parsed: ParsedOutput, window_start: date, window_end: date) -> SimpleNamespace:
    today = timezone.localdate()
    plan = _spending_plan_dates(parsed, today)
    recorded_amount = Decimal(parsed.total_spend or 0)
    paid_amount = (recorded_amount * plan["budget_multiplier"]).quantize(Decimal("0.01"))
    paid_start = plan["paid_start"]
    paid_end = plan["paid_end"]
    reported_start = plan["reported_start"]
    reported_end = plan["reported_end"]
    amount_gap = paid_amount - recorded_amount
    paid_days = _inclusive_days(paid_start, paid_end)
    recorded_days = _inclusive_days(reported_start, reported_end)
    date_gap_days = paid_days - recorded_days

    return SimpleNamespace(
        vendor=parsed.vendor.name if parsed.vendor else "Unassigned",
        campaign=_spending_campaign_name(parsed),
        paid_label=_money_label(paid_amount),
        recorded_label=_money_label(recorded_amount),
        money_gap_label=_money_gap_label(amount_gap),
        money_gap_class=_gap_class(amount_gap),
        paid_days=paid_days,
        recorded_days=recorded_days,
        date_gap_label=str(date_gap_days),
        date_gap_class="ok" if date_gap_days == 0 else "warn",
        planned_left=_timeline_left(paid_start, window_start, window_end),
        planned_width=_timeline_width(paid_start, paid_end, window_start, window_end),
        recorded_left=_timeline_left(reported_start, window_start, window_end),
        recorded_width=_timeline_width(reported_start, reported_end, window_start, window_end),
        recorded_bar_class="warn" if date_gap_days >= 7 and reported_end < today else "",
    )


def _spending_plan_dates(parsed: ParsedOutput, today: date) -> dict[str, object]:
    vendor_name = parsed.vendor.name if parsed.vendor else ""
    example = DASHBOARD_SPENDING_EXAMPLE_PLANS.get(vendor_name)
    if example:
        return {
            "paid_start": today + timedelta(days=example["paid_start"]),
            "paid_end": today + timedelta(days=example["paid_end"]),
            "reported_start": today + timedelta(days=example["reported_start"]),
            "reported_end": today + timedelta(days=example["reported_end"]),
            "budget_multiplier": example["budget_multiplier"],
        }

    fallback_start = parsed.period_start or today
    fallback_end = parsed.period_end or fallback_start
    return {
        "paid_start": fallback_start,
        "paid_end": fallback_end,
        "reported_start": fallback_start,
        "reported_end": fallback_end,
        "budget_multiplier": Decimal("1.00"),
    }


def _inclusive_days(start: date, end: date) -> int:
    return max((end - start).days + 1, 0)


def _spending_campaign_name(parsed: ParsedOutput) -> str:
    name = Path(parsed.asset.name).stem if parsed.asset_id else parsed.reporting_period
    fallback = (parsed.reporting_period or "Campaign").replace("_", " ")
    for marker in ("_April", "_May", "_June", "_July", "_August", "_September", "_October", "_November", "_December"):
        if marker in name:
            name = name.split(marker, 1)[0]
            break
    vendor = parsed.vendor.name if parsed.vendor else ""
    normalized_vendor = vendor.upper().replace(" ", "")
    if normalized_vendor and name.upper().replace(" ", "").startswith(normalized_vendor):
        name = name[len(vendor):].lstrip(" _-")
    return name or fallback


def _spending_month_segments(window_start: date, window_end: date) -> list[dict[str, object]]:
    segments = []
    current = window_start.replace(day=1)
    total_days = _timeline_total_days(window_start, window_end)
    index = 0
    while current <= window_end:
        next_month = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
        segment_start = max(current, window_start)
        segment_end = min(next_month - timedelta(days=1), window_end)
        if segment_start <= segment_end:
            left = ((segment_start - window_start).days / total_days) * 100
            width = (((segment_end - segment_start).days + 1) / total_days) * 100
            segments.append({
                "label": segment_start.strftime("%b"),
                "left": left,
                "width": width,
                "tone": "alt" if index % 2 else "",
            })
            index += 1
        current = next_month
    return segments


def _spending_month_markers(window_start: date, window_end: date) -> list[dict[str, float]]:
    markers = []
    total_days = _timeline_total_days(window_start, window_end)
    current = (window_start.replace(day=28) + timedelta(days=4)).replace(day=1)
    while current < window_end:
        markers.append({"left": ((current - window_start).days / total_days) * 100})
        current = (current.replace(day=28) + timedelta(days=4)).replace(day=1)
    return markers


def _spending_weekend_segments(window_start: date, window_end: date) -> list[dict[str, float]]:
    segments = []
    total_days = _timeline_total_days(window_start, window_end)
    current = window_start
    segment_start = None
    while current <= window_end:
        if current.weekday() >= 5 and segment_start is None:
            segment_start = current
        if segment_start and (current.weekday() < 5 or current == window_end):
            segment_end = current if current.weekday() >= 5 else current - timedelta(days=1)
            left = ((segment_start - window_start).days / total_days) * 100
            width = (((segment_end - segment_start).days + 1) / total_days) * 100
            segments.append({"left": left, "width": width})
            segment_start = None
        current += timedelta(days=1)
    return segments


def _spending_ticks(window_start: date, window_end: date) -> list[dict[str, object]]:
    ticks = []
    total_days = _timeline_total_days(window_start, window_end)
    for offset in range(0, 81, 10):
        tick_date = window_start + timedelta(days=offset)
        ticks.append({"label": f"{tick_date:%b} {tick_date.day}", "left": ((offset + 0.5) / total_days) * 100})
    return ticks


def _timeline_total_days(window_start: date, window_end: date) -> int:
    return max((window_end - window_start).days + 1, 1)


def _timeline_center(item_date: date, window_start: date, window_end: date) -> float:
    total_days = _timeline_total_days(window_start, window_end)
    clamped_date = min(max(item_date, window_start), window_end)
    return (((clamped_date - window_start).days + 0.5) / total_days) * 100


def _timeline_left(item_start: date, window_start: date, window_end: date) -> float:
    total_days = _timeline_total_days(window_start, window_end)
    clamped_start = min(max(item_start, window_start), window_end)
    return ((clamped_start - window_start).days / total_days) * 100


def _timeline_width(item_start: date, item_end: date, window_start: date, window_end: date) -> float:
    total_days = _timeline_total_days(window_start, window_end)
    clamped_start = min(max(item_start, window_start), window_end)
    clamped_end = min(max(item_end, window_start), window_end)
    if clamped_end < clamped_start:
        return 0
    return max((((clamped_end - clamped_start).days + 1) / total_days) * 100, 1.5)


def _money_label(amount: Decimal) -> str:
    if abs(amount) >= Decimal("1000"):
        return f"${amount / Decimal('1000'):,.1f}k"
    return f"${amount:,.0f}"


def _money_gap_label(amount: Decimal) -> str:
    if amount == 0:
        return "$0"
    sign = "-" if amount < 0 else "+"
    return f"{sign}{_money_label(abs(amount))}"


def _gap_class(amount: Decimal) -> str:
    return "ok" if amount == 0 else "warn"


def _decorate_dashboard_asset(asset: Asset) -> None:
    suffix = Path(asset.name).suffix.lower().lstrip(".")
    asset.display_file_type = suffix.upper() if suffix else "-"
    asset.display_parser = asset.parser_key or (asset.vendor.parser_key if asset.vendor else "")
    asset.display_parser = asset.display_parser or "-"
    if asset.status == AssetStatus.FAILED:
        asset.validation_label = "Needs attention"
        asset.validation_class = "failed"
    elif asset.status == AssetStatus.REVIEW:
        asset.validation_label = "Ready"
        asset.validation_class = "review"
    elif asset.status in {AssetStatus.PROCESSED, AssetStatus.UPLOADED}:
        asset.validation_label = "Passed"
        asset.validation_class = "passed"
    else:
        asset.validation_label = "-"
        asset.validation_class = ""
    asset.duplicate_label = "Check" if asset.duplicate_group else "-"


def _dashboard_tabs(status_counts: dict[str, int], mirror_summary: dict[str, int]) -> list[dict[str, object]]:
    all_count = sum(status_counts.values()) or mirror_summary.get("file_count", 0)
    return [
        {"label": "All", "count": all_count, "active": True},
        {"label": "New", "count": status_counts.get(AssetStatus.NEW, mirror_summary.get("new_count", 0))},
        {"label": "Processing", "count": status_counts.get(AssetStatus.PROCESSING, mirror_summary.get("active_count", 0))},
        {"label": "Parsed", "count": status_counts.get(AssetStatus.PROCESSED, mirror_summary.get("processed_count", 0))},
        {"label": "Warnings", "count": status_counts.get(AssetStatus.FAILED, 0)},
        {"label": "Ready", "count": status_counts.get(AssetStatus.REVIEW, mirror_summary.get("review_count", 0))},
        {"label": "Approved", "count": status_counts.get(AssetStatus.UPLOADED, 0)},
        {"label": "Duplicates", "count": mirror_summary.get("duplicate_name_count", 0)},
    ]


def _dashboard_attention_assets(folders: list[dict]) -> list[object]:
    extension_filter = Q(name__iendswith=".csv") | Q(name__iendswith=".xls") | Q(name__iendswith=".xlsx")
    pending_approval_ids = set(
        ParsedOutput.objects.filter(comparison_status="sent_for_approval").values_list("asset_id", flat=True)
    )
    attention_by_id = {}
    assets = list(
        Asset.objects.select_related("vendor", "source_folder")
        .filter(extension_filter)
        .exclude(status__in=DASHBOARD_FINISHED_STATUSES)
        .order_by("remote_created_at", "remote_modified_at", "name")
    )
    for asset in assets:
        _decorate_attention_asset(asset, pending_approval_ids)
        attention_by_id[asset.remote_item_id] = asset

    for folder in folders:
        folder_label = _dashboard_folder_label(folder.get("path") or folder.get("display_name") or "")
        for file_row in folder.get("files", []):
            if not _mirror_file_needs_action(file_row):
                continue
            remote_item_id = file_row.get("remote_item_id") or file_row.get("local_path") or file_row["name"]
            if remote_item_id in attention_by_id:
                continue
            attention_by_id[remote_item_id] = _mirror_attention_item(file_row, folder_label)

    attention_items = list(attention_by_id.values())
    attention_items.sort(key=_attention_sort_key)
    return attention_items


def _attention_sort_key(item: object) -> tuple[int, int, float, str]:
    uploaded_sort = getattr(item, "card_uploaded_sort", 0) or 0
    missing_uploaded_at = 1 if uploaded_sort <= 0 else 0
    return (
        missing_uploaded_at,
        -getattr(item, "card_age_days", 0),
        uploaded_sort,
        getattr(item, "name", "").lower(),
    )


def _mirror_file_needs_action(file_row: dict) -> bool:
    suffix = Path(file_row.get("name") or "").suffix.lower()
    return suffix in DASHBOARD_FILE_EXTENSIONS and file_row.get("status") in {"new", "active", "review"}


def _mirror_attention_item(file_row: dict, folder_label: str) -> SimpleNamespace:
    uploaded_at = _parse_attention_dt(file_row.get("created_at") or file_row.get("modified_at"))
    age_days = _asset_age_days(uploaded_at)
    stage = _mirror_attention_stage(file_row.get("status") or "new")
    return SimpleNamespace(
        name=file_row.get("name") or Path(file_row.get("local_path") or "").name,
        card_vendor="No Vendor",
        card_vendor_missing=True,
        card_uploaded_at=uploaded_at,
        card_uploaded_sort=uploaded_at.timestamp() if uploaded_at else 0,
        card_age_days=age_days,
        card_age_label=_age_label(age_days),
        card_age_class=_age_class(age_days),
        card_stage=stage,
        card_stage_label={"new": "New", "review": "Review", "approval": "Approval"}[stage],
        card_stage_sort={"approval": 0, "review": 1, "new": 2}[stage],
        card_uploader=file_row.get("uploaded_by") or file_row.get("uploader_email") or "Unknown uploader",
        card_progress=_progress_segments(stage),
    )


def _dashboard_folder_label(folder_path: str) -> str:
    label = (folder_path or "").strip("/")
    for prefix in ("home/", "allshared/"):
        if label.startswith(prefix):
            label = label.removeprefix(prefix)
            break
    return label or "Unassigned"


def _parse_attention_dt(value: str | None):
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed and timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _decorate_attention_asset(asset: Asset, pending_approval_ids: set[str]) -> None:
    uploaded_at = _asset_uploaded_at(asset)
    age_days = _asset_age_days(uploaded_at)
    stage = _attention_stage(asset, pending_approval_ids)

    asset.card_uploaded_at = uploaded_at
    asset.card_age_days = age_days
    asset.card_age_label = _age_label(age_days)
    asset.card_age_class = _age_class(age_days)
    asset.card_stage = stage
    asset.card_stage_label = {"new": "New", "review": "Review", "approval": "Approval"}[stage]
    asset.card_stage_sort = {"approval": 0, "review": 1, "new": 2}[stage]
    asset.card_uploader = asset.created_by_display or "Unknown uploader"
    asset.card_vendor = asset.vendor.name if asset.vendor else "No Vendor"
    asset.card_vendor_missing = asset.vendor_id is None
    asset.card_progress = _progress_segments(stage)
    asset.card_uploaded_sort = uploaded_at.timestamp() if uploaded_at else 0


def _asset_uploaded_at(asset: Asset):
    uploaded_at = asset.remote_created_at or asset.remote_modified_at or asset.first_seen_at or asset.last_seen_at
    if uploaded_at and timezone.is_naive(uploaded_at):
        uploaded_at = timezone.make_aware(uploaded_at, timezone.get_current_timezone())
    return uploaded_at


def _asset_age_days(uploaded_at) -> int:
    if not uploaded_at:
        return 0
    if timezone.is_naive(uploaded_at):
        uploaded_at = timezone.make_aware(uploaded_at, timezone.get_current_timezone())
    uploaded_date = timezone.localtime(uploaded_at).date()
    return max((timezone.localdate() - uploaded_date).days, 0)


def _age_label(age_days: int) -> str:
    if age_days <= 0:
        return "Today"
    if age_days == 1:
        return "1 day old"
    return f"{age_days} days old"


def _age_class(age_days: int) -> str:
    if age_days <= 1:
        return "fresh"
    if age_days <= 3:
        return "watch"
    if age_days <= 5:
        return "late"
    return "overdue"


def _attention_stage(asset: Asset, pending_approval_ids: set[str]) -> str:
    if asset.remote_item_id in pending_approval_ids or asset.status == AssetStatus.REVIEW:
        return "approval"
    if asset.status == AssetStatus.PROCESSING:
        return "review"
    return "new"


def _mirror_attention_stage(status: str) -> str:
    if status == "review":
        return "approval"
    if status == "active":
        return "review"
    return "new"


def _progress_segments(stage: str) -> list[dict[str, str]]:
    order = ["new", "review", "approval"]
    labels = {"new": "New", "review": "Review", "approval": "Approval"}
    active_index = order.index(stage)
    segments = []
    for index, key in enumerate(order):
        if index < active_index:
            state = "complete"
        elif index == active_index:
            state = "active"
        else:
            state = "pending"
        segments.append({"label": labels[key], "state": state})
    return segments


def process(request):
    processing_assets = list(
        Asset.objects.select_related("vendor", "source_folder")
        .filter(status=AssetStatus.PROCESSING)
        .order_by("-remote_modified_at", "-last_seen_at", "name")
    )
    grouped_assets = []
    active_vendors = list(Vendor.objects.filter(is_active=True).order_by("name"))
    for vendor in active_vendors:
        vendor_assets = [asset for asset in processing_assets if asset.vendor_id == vendor.id]
        if vendor_assets:
            grouped_assets.append({"vendor": vendor, "assets": vendor_assets})
    unassigned_assets = [asset for asset in processing_assets if not asset.vendor_id]
    if unassigned_assets:
        grouped_assets.append({"vendor": None, "assets": unassigned_assets})
    context = {
        "title": "Parsing",
        "assets": processing_assets,
        "grouped_assets": grouped_assets,
        "vendors": active_vendors,
        "parsed_outputs": ParsedOutput.objects.select_related("asset", "vendor")
        .filter(comparison_status="sent_for_approval")
        .order_by("-created_at")[:50],
        "active_nav": "process",
    }
    return render(request, "pipeline_dashboard/process.html", context)


def folders(request):
    mirror = load_sharefile_mirror()
    vendors = list(Vendor.objects.filter(is_active=True).order_by("name"))
    _apply_folder_vendor_rules(mirror.folders, vendors)
    mirror_summary = {
        **mirror.summary,
        "last_sync_display": _display_timestamp(mirror.summary.get("last_sync_at", "")),
    }
    context = {
        "title": "SF folders",
        "folders": mirror.folders,
        "mirror_summary": mirror_summary,
        "vendors": vendors,
        "active_nav": "folders",
    }
    return render(request, "pipeline_dashboard/folders.html", context)


@require_POST
def update_folders(request):
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    result = subprocess.run(
        [sys.executable, "scripts/update_sharefile_mirror.py", "--repo-root", str(settings.REPO_ROOT)],
        cwd=settings.REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
        timeout=900,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "No output").strip().splitlines()[-1]
        messages.error(request, f"SF folders update failed: {detail}")
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse(
            {
                "ok": result.returncode == 0,
                "redirect_url": reverse("pipeline_dashboard:folders"),
            },
            status=200 if result.returncode == 0 else 400,
        )
    return redirect("pipeline_dashboard:folders")


def _display_timestamp(value: str) -> str:
    if not value:
        return ""
    parsed = parse_datetime(value)
    if not parsed:
        return value
    if timezone.is_naive(parsed):
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return timezone.localtime(parsed).strftime("%b %d, %Y %H:%M")


@require_GET
def review_file_preview(request):
    local_path = request.GET.get("local_path", "")
    file_row = _mirror_file_by_local_path(local_path)
    if not file_row:
        return JsonResponse({"error": "File is not in the current SF mirror."}, status=404)

    try:
        preview = build_file_preview(local_path, file_row)
    except ReviewPreviewError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse({"file": preview})


@require_POST
@transaction.atomic
def process_review_file(request):
    local_path = request.POST.get("local_path", "")
    vendor_id = request.POST.get("vendor_id", "")
    file_row = _mirror_file_by_local_path(local_path)
    if not file_row:
        return JsonResponse({"error": "File is not in the current SF mirror."}, status=404)
    if file_row["status"] != "new":
        return JsonResponse({"error": "Only new files can be moved to Parsing."}, status=400)
    if not file_row.get("remote_item_id"):
        return JsonResponse({"error": "Only files still present in ShareFile can be moved to Parsing."}, status=400)
    try:
        inbox_file_path(local_path)
    except ReviewPreviewError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    try:
        vendor = Vendor.objects.get(pk=vendor_id, is_active=True)
    except (Vendor.DoesNotExist, ValueError):
        return JsonResponse({"error": "Choose an active vendor before moving to Parsing."}, status=400)
    if not _vendor_allowed_for_file(vendor, file_row):
        return JsonResponse({"error": f"{vendor.name} is not available for this folder."}, status=400)

    source_folder = _source_folder_for_file(file_row)
    existing = Asset.objects.filter(remote_item_id=file_row["remote_item_id"]).first()
    previous_status = existing.status if existing else ""
    defaults = {
        "vendor": vendor,
        "source_folder": source_folder,
        "status": AssetStatus.PROCESSING,
        "name": file_row["name"],
        "sharefile_folder_id": file_row.get("source_folder_id") or "",
        "source_folder_label": file_row.get("source_folder_path") or "",
        "remote_path": file_row.get("remote_path") or "",
        "file_size": file_row.get("size") or None,
        "remote_created_at": _parse_dt(file_row.get("created_at")),
        "remote_modified_at": _parse_dt(file_row.get("modified_at")),
        "created_by_name": file_row.get("uploaded_by") or "",
        "created_by_email": file_row.get("uploader_email") or "",
        "local_path": local_path,
        "parser_key": vendor.parser_key,
        "content_hash": file_row.get("sharefile_hash") or "",
        "duplicate_group": file_row["name"].lower(),
        "last_seen_at": timezone.now(),
        "status_reason": "Moved to Parsing from SF folders review.",
        "raw_metadata": {
            "source": "sf_folders_review",
            "profile_kind": file_row.get("profile_kind") or "",
            "profile_status": file_row.get("profile_status") or "",
        },
    }
    asset, _ = Asset.objects.update_or_create(remote_item_id=file_row["remote_item_id"], defaults=defaults)
    AssetEvent.objects.create(
        asset=asset,
        event_type="review_started",
        from_status=previous_status,
        to_status=AssetStatus.PROCESSING,
        message="Moved to Parsing from SF folders review.",
        metadata={"local_path": local_path, "vendor_id": vendor.id},
    )
    return JsonResponse({"status": "active", "label": "A", "asset_id": asset.remote_item_id})


@require_POST
@transaction.atomic
def update_process_vendor(request, remote_item_id: str):
    asset = get_object_or_404(
        Asset.objects.select_for_update(),
        remote_item_id=remote_item_id,
        status=AssetStatus.PROCESSING,
    )
    vendor_id = request.POST.get("vendor_id", "")
    try:
        vendor = Vendor.objects.get(pk=vendor_id, is_active=True)
    except (Vendor.DoesNotExist, ValueError):
        messages.error(request, "Choose an active vendor.")
        return redirect("pipeline_dashboard:process")

    previous_vendor = asset.vendor.name if asset.vendor else ""
    asset.vendor = vendor
    asset.parser_key = vendor.parser_key
    asset.save(update_fields=["vendor", "parser_key", "updated_at"])
    AssetEvent.objects.create(
        asset=asset,
        event_type="vendor_changed",
        from_status=AssetStatus.PROCESSING,
        to_status=AssetStatus.PROCESSING,
        message=f"Vendor changed from {previous_vendor or 'Unassigned'} to {vendor.name}.",
        metadata={"previous_vendor": previous_vendor, "vendor_id": vendor.id},
    )
    messages.success(request, f"{asset.name}: vendor updated to {vendor.name}.")
    return redirect("pipeline_dashboard:process")


@require_POST
@transaction.atomic
def cancel_process_file(request, remote_item_id: str):
    asset = get_object_or_404(
        Asset.objects.select_for_update(),
        remote_item_id=remote_item_id,
        status=AssetStatus.PROCESSING,
    )
    previous_vendor = asset.vendor.name if asset.vendor else ""
    asset.vendor = None
    asset.parser_key = ""
    asset.status_reason = "Parsing was cancelled; file returned to New."
    asset.save(update_fields=["vendor", "parser_key", "status_reason", "updated_at"])
    set_asset_status(asset, AssetStatus.NEW, "Parsing cancelled from Parsing page.")
    AssetEvent.objects.create(
        asset=asset,
        event_type="processing_cancelled",
        from_status=AssetStatus.PROCESSING,
        to_status=AssetStatus.NEW,
        message="Parsing cancelled from Parsing page.",
        metadata={"previous_vendor": previous_vendor},
    )
    messages.success(request, f"{asset.name}: returned to New.")
    return redirect("pipeline_dashboard:process")


@require_GET
def parse_file_preview(request, remote_item_id: str):
    asset = get_object_or_404(
        Asset.objects.select_related("vendor", "source_folder"),
        remote_item_id=remote_item_id,
        status=AssetStatus.PROCESSING,
    )
    try:
        payload = build_parse_preview(asset)
    except (ParserWorkflowError, ReviewPreviewError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    return JsonResponse(payload)


@require_POST
@transaction.atomic
def parse_process_file(request, remote_item_id: str):
    asset = get_object_or_404(
        Asset.objects.select_related("vendor", "source_folder"),
        remote_item_id=remote_item_id,
        status=AssetStatus.PROCESSING,
    )
    try:
        payload = build_parse_result_preview(asset)
    except (ParserWorkflowError, ReviewPreviewError, ValueError) as exc:
        return JsonResponse({"error": str(exc)}, status=400)

    return JsonResponse(payload)


@require_POST
@transaction.atomic
def approve_process_file(request, remote_item_id: str):
    asset = get_object_or_404(
        Asset.objects.select_for_update().select_related("vendor", "source_folder"),
        remote_item_id=remote_item_id,
        status=AssetStatus.PROCESSING,
    )
    parsed = None
    try:
        parsed = stage_asset_parser(asset)
        upload_item = upload_approved_output(settings.REPO_ROOT / parsed.output_path, parsed.vendor, parsed.comparison_summary)
    except (ParserWorkflowError, ReviewPreviewError, ValueError) as exc:
        _remove_staged_output(parsed)
        transaction.set_rollback(True)
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        _remove_staged_output(parsed)
        transaction.set_rollback(True)
        return JsonResponse({"error": str(exc)}, status=400)

    parsed.comparison_status = "sent_for_approval"
    parsed.comparison_summary = {
        **(parsed.comparison_summary or {}),
        "sharefile_item_id": upload_item.id,
        "sharefile_filename": upload_item.name,
    }
    parsed.save(update_fields=["comparison_status", "comparison_summary"])

    asset.output_path = parsed.output_path
    asset.uploaded_item_id = upload_item.id
    asset.status_reason = "Parsed output sent to ShareFile Approval for external review."
    asset.save(update_fields=["output_path", "uploaded_item_id", "status_reason", "updated_at"])
    set_asset_status(asset, AssetStatus.REVIEW, "Parsed output sent to ShareFile Approval for external review.")
    AssetEvent.objects.create(
        asset=asset,
        event_type="approval_sent",
        from_status=AssetStatus.PROCESSING,
        to_status=AssetStatus.REVIEW,
        message=f"Parsed output sent to ShareFile Approval as {upload_item.name}.",
        metadata={
            "parsed_output_id": parsed.id,
            "comparison_status": parsed.comparison_status,
            "sharefile_item_id": upload_item.id,
            "sharefile_filename": upload_item.name,
        },
    )
    return JsonResponse(
        {
            "status": "review",
            "asset_id": asset.remote_item_id,
            "output_path": parsed.output_path,
            "comparison_status": parsed.comparison_status,
            "uploaded_item_id": upload_item.id,
            "uploaded_name": upload_item.name,
        }
    )


@require_POST
@transaction.atomic
def cancel_parsed_output(request, parsed_output_id: int):
    parsed = get_object_or_404(
        ParsedOutput.objects.select_for_update().select_related("asset", "vendor"),
        pk=parsed_output_id,
    )
    asset = Asset.objects.select_for_update().get(pk=parsed.asset_id)
    previous_status = asset.status

    parsed.comparison_status = "cancelled"
    parsed.comparison_summary = {
        **(parsed.comparison_summary or {}),
        "cancelled_at": timezone.now().isoformat(),
    }
    parsed.save(update_fields=["comparison_status", "comparison_summary"])

    asset.output_path = ""
    asset.uploaded_item_id = ""
    asset.status_reason = "Parsed CSV approval was cancelled; file returned to Parsing."
    asset.save(update_fields=["output_path", "uploaded_item_id", "status_reason", "updated_at"])
    set_asset_status(asset, AssetStatus.PROCESSING, "Parsed CSV approval cancelled from Approval area.")
    AssetEvent.objects.create(
        asset=asset,
        event_type="parsed_output_cancelled",
        from_status=previous_status,
        to_status=AssetStatus.PROCESSING,
        message="Parsed CSV approval cancelled from Approval area.",
        metadata={"parsed_output_id": parsed.id, "output_path": parsed.output_path},
    )
    messages.success(request, f"{asset.name}: returned to Parsing Files.")
    return redirect("pipeline_dashboard:process")


@require_POST
@transaction.atomic
def approve_parsed_output(request, parsed_output_id: int):
    parsed = get_object_or_404(
        ParsedOutput.objects.select_for_update().select_related("asset", "vendor"),
        pk=parsed_output_id,
        comparison_status="sent_for_approval",
    )
    asset = Asset.objects.select_for_update().get(pk=parsed.asset_id)
    previous_status = asset.status
    if asset.status != AssetStatus.REVIEW:
        return JsonResponse({"error": "Only files in Review can be marked approved."}, status=400)

    try:
        upload_item = finalize_approved_output(parsed)
    except (ParserWorkflowError, ReviewPreviewError, ValueError) as exc:
        transaction.set_rollback(True)
        return JsonResponse({"error": str(exc)}, status=400)
    except Exception as exc:
        transaction.set_rollback(True)
        return JsonResponse({"error": str(exc)}, status=400)

    final_path = final_processed_output_path(parsed)
    period_label = final_period_label(parsed)
    parsed.comparison_status = "approved"
    parsed.comparison_summary = {
        **(parsed.comparison_summary or {}),
        "final_sharefile_item_id": upload_item.id,
        "final_sharefile_filename": upload_item.name,
        "final_sharefile_path": f"Final/{period_label}/{upload_item.name}",
        "final_local_path": _relative_path(final_path),
        "approved_at": timezone.now().isoformat(),
    }
    parsed.save(update_fields=["comparison_status", "comparison_summary"])

    asset.output_path = _relative_path(final_path)
    asset.uploaded_item_id = upload_item.id
    asset.status_reason = "Parsed CSV approved and stored in ShareFile Final."
    asset.save(update_fields=["output_path", "uploaded_item_id", "status_reason", "updated_at"])
    set_asset_status(asset, AssetStatus.PROCESSED, "Parsed CSV approved and stored in ShareFile Final.")
    AssetEvent.objects.create(
        asset=asset,
        event_type="final_approved",
        from_status=previous_status,
        to_status=AssetStatus.PROCESSED,
        message=f"Parsed CSV stored in ShareFile Final as {upload_item.name}.",
        metadata={
            "parsed_output_id": parsed.id,
            "final_sharefile_item_id": upload_item.id,
            "final_sharefile_filename": upload_item.name,
            "final_local_path": _relative_path(final_path),
        },
    )
    messages.success(request, f"{asset.name}: approved and stored in ShareFile Final.")
    return redirect("pipeline_dashboard:process")


def _remove_staged_output(parsed: ParsedOutput | None) -> None:
    if parsed and parsed.output_path:
        (settings.REPO_ROOT / parsed.output_path).unlink(missing_ok=True)


def _apply_folder_vendor_rules(folders: list[dict], vendors: list[Vendor]) -> None:
    vendors_by_name = {vendor.name.casefold(): vendor for vendor in vendors}
    for folder in folders:
        names = _allowed_vendor_names_for_folder(folder.get("path", ""))
        allowed_vendors = [vendors_by_name[name.casefold()] for name in names if name.casefold() in vendors_by_name]
        folder["allowed_vendor_ids"] = ",".join(str(vendor.id) for vendor in allowed_vendors)
        folder["allowed_vendor_names"] = ", ".join(vendor.name for vendor in allowed_vendors)


def _vendor_allowed_for_file(vendor: Vendor, file_row: dict) -> bool:
    names = _allowed_vendor_names_for_folder(file_row.get("source_folder_path", ""))
    if not names:
        return True
    return vendor.name.casefold() in {name.casefold() for name in names}


def _allowed_vendor_names_for_folder(folder_path: str) -> tuple[str, ...]:
    key = _folder_rule_key(folder_path)
    return FOLDER_VENDOR_RULES.get(key, ())


def _folder_rule_key(folder_path: str) -> str:
    normalized = (folder_path or "").strip().strip("/")
    for prefix in ("home/", "allshared/"):
        if normalized.startswith(prefix):
            normalized = normalized.removeprefix(prefix)
            break
    return normalized.casefold()


def _mirror_file_by_local_path(local_path: str) -> dict | None:
    if not local_path:
        return None
    mirror = load_sharefile_mirror()
    for folder in mirror.folders:
        for file_row in folder["files"]:
            if file_row["local_path"] == local_path:
                return file_row
    return None


def _source_folder_for_file(file_row: dict) -> ShareFileFolder | None:
    folder_id = file_row.get("source_folder_id") or ""
    if not folder_id:
        return None
    folder, _ = ShareFileFolder.objects.get_or_create(
        folder_id=folder_id,
        defaults={"label": file_row.get("source_folder_path") or folder_id},
    )
    return folder


def _parse_dt(value: str | None):
    if not value:
        return None
    return parse_datetime(value)


def _relative_path(path):
    try:
        return str(path.relative_to(settings.REPO_ROOT))
    except ValueError:
        return str(path)

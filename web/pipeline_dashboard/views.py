from __future__ import annotations

import os
import subprocess
import sys

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.http import require_GET, require_POST

from .file_review import ReviewPreviewError, build_file_preview, inbox_file_path
from .models import Asset, AssetEvent, AssetStatus, ShareFileFolder, Vendor
from .sharefile_mirror import load_sharefile_mirror
from .services import set_asset_status


REVIEW_STATUSES = [
    AssetStatus.NEW,
    AssetStatus.FAILED,
    AssetStatus.QUEUED,
    AssetStatus.DOWNLOADED,
    AssetStatus.SUPERSEDED,
    AssetStatus.IGNORED,
]


def admin_urls_context() -> dict[str, str]:
    return {
        "index": reverse("admin:index"),
        "vendors": reverse("admin:pipeline_dashboard_vendor_changelist"),
        "vendor_add": reverse("admin:pipeline_dashboard_vendor_add"),
        "folders": reverse("admin:pipeline_dashboard_sharefilefolder_changelist"),
        "folder_add": reverse("admin:pipeline_dashboard_sharefilefolder_add"),
        "assets": reverse("admin:pipeline_dashboard_asset_changelist"),
    }


def status_rows(active_status: str | None = None) -> list[dict[str, object]]:
    status_counts = {
        row["status"]: row["count"]
        for row in Asset.objects.values("status").annotate(count=Count("remote_item_id"))
    }
    return [
        {
            "key": status,
            "label": AssetStatus(status).label,
            "count": status_counts.get(status, 0),
            "url": f"{reverse('pipeline_dashboard:assets')}?status={status}",
            "admin_url": f"{reverse('admin:pipeline_dashboard_asset_changelist')}?status__exact={status}",
            "active": status == active_status,
        }
        for status in REVIEW_STATUSES
    ]


def dashboard(request):
    status_counts = {
        row["status"]: row["count"]
        for row in Asset.objects.values("status").annotate(count=Count("remote_item_id"))
    }
    vendor_counts = (
        Asset.objects.values("vendor__name")
        .annotate(count=Count("remote_item_id"))
        .order_by("-count", "vendor__name")[:8]
    )
    review_assets = (
        Asset.objects.select_related("vendor", "source_folder")
        .filter(status__in=[AssetStatus.NEW, AssetStatus.FAILED, AssetStatus.QUEUED])
        .order_by("-remote_modified_at", "-last_seen_at")[:12]
    )
    recent_assets = (
        Asset.objects.select_related("vendor", "source_folder")
        .order_by("-last_seen_at", "name")[:12]
    )
    folders = ShareFileFolder.objects.select_related("vendor").order_by("label")[:12]

    context = {
        "title": "Testifize Pipeline",
        "totals": {
            "assets": Asset.objects.count(),
            "vendors": Vendor.objects.count(),
            "folders": ShareFileFolder.objects.count(),
            "needs_review": Asset.objects.filter(status__in=[AssetStatus.NEW, AssetStatus.FAILED]).count(),
            "downloaded": status_counts.get(AssetStatus.DOWNLOADED, 0),
            "uploaded": status_counts.get(AssetStatus.UPLOADED, 0),
        },
        "status_rows": [
            {
                "key": status,
                "label": AssetStatus(status).label,
                "count": status_counts.get(status, 0),
                "url": f"{reverse('pipeline_dashboard:assets')}?status={status}",
            }
            for status in REVIEW_STATUSES
        ],
        "vendor_counts": vendor_counts,
        "review_assets": review_assets,
        "recent_assets": recent_assets,
        "folders": folders,
        "admin_urls": admin_urls_context(),
        "active_nav": "dashboard",
    }
    return render(request, "pipeline_dashboard/dashboard.html", context)


def assets(request):
    active_status = request.GET.get("status") or ""
    valid_statuses = {choice.value for choice in AssetStatus}
    asset_queryset = Asset.objects.select_related("vendor", "source_folder").order_by(
        "-remote_modified_at",
        "-last_seen_at",
        "name",
    )
    if active_status in valid_statuses:
        asset_queryset = asset_queryset.filter(status=active_status)
    else:
        active_status = ""

    context = {
        "title": "Assets",
        "assets": asset_queryset[:200],
        "status_rows": status_rows(active_status or None),
        "active_status": active_status,
        "admin_urls": admin_urls_context(),
        "active_nav": "assets",
    }
    return render(request, "pipeline_dashboard/assets.html", context)


def process(request):
    processing_assets = (
        Asset.objects.select_related("vendor", "source_folder")
        .filter(status=AssetStatus.PROCESSING)
        .order_by("-remote_modified_at", "-last_seen_at", "name")
    )
    context = {
        "title": "Process",
        "assets": processing_assets,
        "vendors": Vendor.objects.filter(is_active=True).order_by("name"),
        "admin_urls": admin_urls_context(),
        "active_nav": "process",
    }
    return render(request, "pipeline_dashboard/process.html", context)


def folders(request):
    mirror = load_sharefile_mirror()
    context = {
        "title": "SF folders",
        "folders": mirror.folders,
        "mirror_summary": mirror.summary,
        "vendors": Vendor.objects.filter(is_active=True).order_by("name"),
        "admin_urls": admin_urls_context(),
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
    if result.returncode == 0:
        messages.success(request, "SF folders updated.")
    else:
        detail = (result.stderr or result.stdout or "No output").strip().splitlines()[-1]
        messages.error(request, f"SF folders update failed: {detail}")
    return redirect("pipeline_dashboard:folders")


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
        return JsonResponse({"error": "Only new files can be moved to Active."}, status=400)
    if not file_row.get("remote_item_id"):
        return JsonResponse({"error": "Only files still present in ShareFile can be processed."}, status=400)
    try:
        inbox_file_path(local_path)
    except ReviewPreviewError as exc:
        return JsonResponse({"error": str(exc)}, status=400)
    try:
        vendor = Vendor.objects.get(pk=vendor_id, is_active=True)
    except (Vendor.DoesNotExist, ValueError):
        return JsonResponse({"error": "Choose an active vendor before processing."}, status=400)

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
        "status_reason": "Moved to Active from SF folders review.",
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
        message="Moved to Active from SF folders review.",
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
    asset.status_reason = "Processing was cancelled; file returned to New."
    asset.save(update_fields=["vendor", "parser_key", "status_reason", "updated_at"])
    set_asset_status(asset, AssetStatus.NEW, "Processing cancelled from Process page.")
    AssetEvent.objects.create(
        asset=asset,
        event_type="processing_cancelled",
        from_status=AssetStatus.PROCESSING,
        to_status=AssetStatus.NEW,
        message="Processing cancelled from Process page.",
        metadata={"previous_vendor": previous_vendor},
    )
    messages.success(request, f"{asset.name}: returned to New.")
    return redirect("pipeline_dashboard:process")


def vendors(request):
    vendor_queryset = Vendor.objects.annotate(
        asset_count=Count("assets", distinct=True),
        folder_count=Count("folders", distinct=True),
    ).order_by("name")
    context = {
        "title": "Vendors",
        "vendors": vendor_queryset,
        "admin_urls": admin_urls_context(),
        "active_nav": "vendors",
    }
    return render(request, "pipeline_dashboard/vendors.html", context)


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

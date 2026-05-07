from __future__ import annotations

from django.db.models import Count
from django.shortcuts import render
from django.urls import reverse

from .models import Asset, AssetStatus, ShareFileFolder, Vendor


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


def folders(request):
    folder_queryset = (
        ShareFileFolder.objects.select_related("vendor")
        .annotate(asset_count=Count("assets"))
        .order_by("label")
    )
    context = {
        "title": "ShareFile Folders",
        "folders": folder_queryset,
        "admin_urls": admin_urls_context(),
        "active_nav": "folders",
    }
    return render(request, "pipeline_dashboard/folders.html", context)


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

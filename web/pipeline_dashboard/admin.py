from __future__ import annotations

from django.contrib import admin, messages

from .models import Asset, AssetEvent, AssetStatus, ParsedOutput, ShareFileFolder, Vendor
from .services import download_asset, scan_folder, set_asset_status


@admin.register(Vendor)
class VendorAdmin(admin.ModelAdmin):
    list_display = ["name", "parser_key", "is_active", "updated_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "parser_key", "notes"]


@admin.register(ShareFileFolder)
class ShareFileFolderAdmin(admin.ModelAdmin):
    list_display = ["label", "folder_id", "role", "vendor", "is_active", "updated_at"]
    list_filter = ["role", "vendor", "is_active"]
    search_fields = ["label", "folder_id", "vendor__name", "notes"]
    actions = ["scan_selected_folders"]

    @admin.action(description="Scan selected folders")
    def scan_selected_folders(self, request, queryset):
        total = 0
        for folder in queryset:
            try:
                total += scan_folder(folder)
            except Exception as exc:
                self.message_user(request, f"{folder}: scan failed: {exc}", level=messages.ERROR)
        self.message_user(request, f"Scan complete. Catalogued {total} matching files.", level=messages.SUCCESS)


class AssetEventInline(admin.TabularInline):
    model = AssetEvent
    extra = 0
    can_delete = False
    fields = ["event_type", "from_status", "to_status", "message", "created_at"]
    readonly_fields = fields
    ordering = ["-created_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "status",
        "vendor",
        "source_folder",
        "remote_modified_at",
        "file_size",
        "created_by_display",
    ]
    list_filter = ["status", "vendor", "source_folder", "parser_key", "duplicate_role", "duplicate_group"]
    search_fields = [
        "name",
        "remote_item_id",
        "created_by_name",
        "created_by_email",
        "status_reason",
        "duplicate_group",
    ]
    list_editable = ["status", "vendor"]
    readonly_fields = ["remote_item_id", "first_seen_at", "last_seen_at", "updated_at", "raw_metadata"]
    fieldsets = [
        (
            "Review",
            {
                "fields": [
                    "status",
                    "vendor",
                    "parser_key",
                    "duplicate_role",
                    "duplicate_group",
                    "status_reason",
                ]
            },
        ),
        (
            "ShareFile",
            {
                "fields": [
                    "remote_item_id",
                    "name",
                    "source_folder",
                    "sharefile_folder_id",
                    "source_folder_label",
                    "remote_path",
                    "file_size",
                    "remote_created_at",
                    "remote_modified_at",
                    "created_by_name",
                    "created_by_email",
                ]
            },
        ),
        (
            "Local processing",
            {
                "fields": [
                    "local_path",
                    "output_path",
                    "uploaded_item_id",
                    "parser_version",
                    "content_hash",
                ]
            },
        ),
        ("Audit", {"fields": ["first_seen_at", "last_seen_at", "updated_at", "raw_metadata"]}),
    ]
    inlines = [AssetEventInline]
    actions = ["mark_queued", "mark_ignored", "mark_superseded", "download_selected"]

    @admin.action(description="Mark selected assets queued")
    def mark_queued(self, request, queryset):
        self._set_status_for_queryset(request, queryset, AssetStatus.QUEUED, "Marked queued from admin")

    @admin.action(description="Mark selected assets ignored")
    def mark_ignored(self, request, queryset):
        self._set_status_for_queryset(request, queryset, AssetStatus.IGNORED, "Marked ignored from admin")

    @admin.action(description="Mark selected assets superseded")
    def mark_superseded(self, request, queryset):
        self._set_status_for_queryset(request, queryset, AssetStatus.SUPERSEDED, "Marked superseded from admin")

    @admin.action(description="Download selected assets")
    def download_selected(self, request, queryset):
        count = 0
        for asset in queryset:
            try:
                download_asset(asset)
                count += 1
            except Exception as exc:
                self.message_user(request, f"{asset.name}: download failed: {exc}", level=messages.ERROR)
        self.message_user(request, f"Downloaded {count} assets.", level=messages.SUCCESS)

    def _set_status_for_queryset(self, request, queryset, status: str, message: str):
        count = 0
        for asset in queryset:
            set_asset_status(asset, status, message)
            count += 1
        self.message_user(request, f"Updated {count} assets to {status}.", level=messages.SUCCESS)


@admin.register(AssetEvent)
class AssetEventAdmin(admin.ModelAdmin):
    list_display = ["asset", "event_type", "from_status", "to_status", "created_at"]
    list_filter = ["event_type", "from_status", "to_status"]
    search_fields = ["asset__name", "asset__remote_item_id", "message"]
    readonly_fields = ["asset", "event_type", "from_status", "to_status", "message", "created_at", "metadata"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(ParsedOutput)
class ParsedOutputAdmin(admin.ModelAdmin):
    list_display = [
        "output_path",
        "vendor",
        "asset",
        "reporting_period",
        "version",
        "row_count",
        "comparison_status",
        "created_at",
    ]
    list_filter = ["vendor", "comparison_status", "reporting_period"]
    search_fields = ["output_path", "approved_path", "asset__name", "vendor__name"]
    readonly_fields = [
        "asset",
        "vendor",
        "output_path",
        "approved_path",
        "reporting_period",
        "period_start",
        "period_end",
        "version",
        "row_count",
        "total_spend",
        "total_impressions",
        "comparison_status",
        "comparison_summary",
        "created_at",
    ]

    def has_add_permission(self, request):
        return False

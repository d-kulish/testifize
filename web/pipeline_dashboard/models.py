from __future__ import annotations

from django.db import models
from django.utils import timezone


class AssetStatus(models.TextChoices):
    DISCOVERED = "discovered", "Discovered"
    NEW = "new", "New"
    QUEUED = "queued", "Queued"
    DOWNLOADING = "downloading", "Downloading"
    DOWNLOADED = "downloaded", "Downloaded"
    PROCESSING = "processing", "Processing"
    REVIEW = "review", "Review"
    PROCESSED = "processed", "Processed"
    UPLOADING = "uploading", "Uploading"
    UPLOADED = "uploaded", "Uploaded"
    SUPERSEDED = "superseded", "Superseded"
    IGNORED = "ignored", "Ignored"
    FAILED = "failed", "Failed"


class FolderRole(models.TextChoices):
    INPUT = "input", "Input"
    OUTPUT = "output", "Output"
    BOTH = "both", "Both"


class Vendor(models.Model):
    name = models.CharField(max_length=120, unique=True)
    parser_key = models.CharField(max_length=120, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class ShareFileFolder(models.Model):
    vendor = models.ForeignKey(Vendor, blank=True, null=True, on_delete=models.SET_NULL, related_name="folders")
    folder_id = models.CharField(max_length=120, unique=True)
    label = models.CharField(max_length=255)
    role = models.CharField(max_length=20, choices=FolderRole.choices, default=FolderRole.INPUT)
    file_patterns = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["label"]

    def __str__(self) -> str:
        return self.label

    def effective_file_patterns(self) -> list[str]:
        return self.file_patterns or ["*.xlsx", "*.xls", "*.csv"]


class Asset(models.Model):
    remote_item_id = models.CharField(max_length=120, primary_key=True)
    vendor = models.ForeignKey(Vendor, blank=True, null=True, on_delete=models.SET_NULL, related_name="assets")
    source_folder = models.ForeignKey(
        ShareFileFolder,
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="assets",
    )
    status = models.CharField(max_length=30, choices=AssetStatus.choices, default=AssetStatus.NEW, db_index=True)
    name = models.CharField(max_length=500)
    sharefile_folder_id = models.CharField(max_length=120, blank=True)
    source_folder_label = models.CharField(max_length=255, blank=True)
    remote_path = models.CharField(max_length=1000, blank=True)
    file_size = models.BigIntegerField(blank=True, null=True)
    remote_created_at = models.DateTimeField(blank=True, null=True)
    remote_modified_at = models.DateTimeField(blank=True, null=True, db_index=True)
    created_by_name = models.CharField(max_length=255, blank=True)
    created_by_email = models.EmailField(blank=True)
    local_path = models.CharField(max_length=1000, blank=True)
    output_path = models.CharField(max_length=1000, blank=True)
    uploaded_item_id = models.CharField(max_length=120, blank=True)
    parser_key = models.CharField(max_length=120, blank=True)
    parser_version = models.CharField(max_length=120, blank=True)
    content_hash = models.CharField(max_length=128, blank=True)
    duplicate_group = models.CharField(max_length=255, blank=True, db_index=True)
    duplicate_role = models.CharField(
        max_length=20,
        choices=[
            ("original", "Original"),
            ("duplicate", "Duplicate"),
        ],
        blank=True,
        db_index=True,
    )
    status_reason = models.TextField(blank=True)
    first_seen_at = models.DateTimeField(default=timezone.now, editable=False)
    last_seen_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    raw_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-remote_modified_at", "-last_seen_at", "name"]
        indexes = [
            models.Index(fields=["vendor", "status"], name="asset_vendor_status_idx"),
            models.Index(fields=["source_folder", "status"], name="asset_folder_status_idx"),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def created_by_display(self) -> str:
        return self.created_by_name or self.created_by_email


class AssetEvent(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(max_length=80)
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30, blank=True)
    message = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self) -> str:
        return f"{self.event_type}: {self.asset_id}"


class ParsedOutput(models.Model):
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name="parsed_outputs")
    vendor = models.ForeignKey(Vendor, blank=True, null=True, on_delete=models.SET_NULL, related_name="parsed_outputs")
    output_path = models.CharField(max_length=1000, unique=True)
    approved_path = models.CharField(max_length=1000, blank=True)
    reporting_period = models.CharField(max_length=80, blank=True)
    period_start = models.DateField(blank=True, null=True)
    period_end = models.DateField(blank=True, null=True)
    version = models.PositiveIntegerField(default=1)
    row_count = models.PositiveIntegerField(default=0)
    total_spend = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    total_impressions = models.DecimalField(max_digits=20, decimal_places=6, default=0)
    comparison_status = models.CharField(max_length=40, default="pending", db_index=True)
    comparison_summary = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-created_at", "vendor__name", "output_path"]
        indexes = [
            models.Index(fields=["vendor", "comparison_status"], name="parsed_vendor_status_idx"),
            models.Index(fields=["asset", "created_at"], name="parsed_asset_created_idx"),
        ]

    def __str__(self) -> str:
        return self.output_path

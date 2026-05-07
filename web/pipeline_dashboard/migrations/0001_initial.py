from __future__ import annotations

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Vendor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120, unique=True)),
                ("parser_key", models.CharField(blank=True, max_length=120)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["name"]},
        ),
        migrations.CreateModel(
            name="ShareFileFolder",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("folder_id", models.CharField(max_length=120, unique=True)),
                ("label", models.CharField(max_length=255)),
                (
                    "role",
                    models.CharField(
                        choices=[("input", "Input"), ("output", "Output"), ("both", "Both")],
                        default="input",
                        max_length=20,
                    ),
                ),
                ("file_patterns", models.JSONField(blank=True, default=list)),
                ("is_active", models.BooleanField(default=True)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "vendor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="folders",
                        to="pipeline_dashboard.vendor",
                    ),
                ),
            ],
            options={"ordering": ["label"]},
        ),
        migrations.CreateModel(
            name="Asset",
            fields=[
                ("remote_item_id", models.CharField(max_length=120, primary_key=True, serialize=False)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("discovered", "Discovered"),
                            ("new", "New"),
                            ("queued", "Queued"),
                            ("downloading", "Downloading"),
                            ("downloaded", "Downloaded"),
                            ("processing", "Processing"),
                            ("processed", "Processed"),
                            ("uploading", "Uploading"),
                            ("uploaded", "Uploaded"),
                            ("superseded", "Superseded"),
                            ("ignored", "Ignored"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="new",
                        max_length=30,
                    ),
                ),
                ("name", models.CharField(max_length=500)),
                ("sharefile_folder_id", models.CharField(blank=True, max_length=120)),
                ("source_folder_label", models.CharField(blank=True, max_length=255)),
                ("remote_path", models.CharField(blank=True, max_length=1000)),
                ("file_size", models.BigIntegerField(blank=True, null=True)),
                ("remote_created_at", models.DateTimeField(blank=True, null=True)),
                ("remote_modified_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("created_by_name", models.CharField(blank=True, max_length=255)),
                ("created_by_email", models.EmailField(blank=True, max_length=254)),
                ("local_path", models.CharField(blank=True, max_length=1000)),
                ("output_path", models.CharField(blank=True, max_length=1000)),
                ("uploaded_item_id", models.CharField(blank=True, max_length=120)),
                ("parser_key", models.CharField(blank=True, max_length=120)),
                ("parser_version", models.CharField(blank=True, max_length=120)),
                ("content_hash", models.CharField(blank=True, max_length=128)),
                ("duplicate_group", models.CharField(blank=True, db_index=True, max_length=255)),
                ("status_reason", models.TextField(blank=True)),
                ("first_seen_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("last_seen_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("raw_metadata", models.JSONField(blank=True, default=dict)),
                (
                    "source_folder",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assets",
                        to="pipeline_dashboard.sharefilefolder",
                    ),
                ),
                (
                    "vendor",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assets",
                        to="pipeline_dashboard.vendor",
                    ),
                ),
            ],
            options={
                "ordering": ["-remote_modified_at", "-last_seen_at", "name"],
                "indexes": [
                    models.Index(fields=["vendor", "status"], name="asset_vendor_status_idx"),
                    models.Index(fields=["source_folder", "status"], name="asset_folder_status_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="AssetEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(max_length=80)),
                ("from_status", models.CharField(blank=True, max_length=30)),
                ("to_status", models.CharField(blank=True, max_length=30)),
                ("message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                (
                    "asset",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="events",
                        to="pipeline_dashboard.asset",
                    ),
                ),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]

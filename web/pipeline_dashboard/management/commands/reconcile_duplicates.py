from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from pipeline_dashboard.models import Asset
from pipeline_dashboard.services import _reconcile_duplicate_roles_for_group


class Command(BaseCommand):
    help = "Backfill duplicate_role for existing assets and reconcile roles across all groups."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without writing to the database.",
        )
        parser.add_argument(
            "--group",
            type=str,
            help="Process only a specific duplicate_group (normalized filename).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        target_group = options.get("group")

        if target_group:
            groups = [target_group]
        else:
            groups = list(
                Asset.objects.exclude(duplicate_group="")
                .values_list("duplicate_group", flat=True)
                .distinct()
            )

        if not groups:
            self.stdout.write(self.style.WARNING("No duplicate_group values found."))
            return

        self.stdout.write(f"Processing {len(groups)} duplicate group(s)...")

        updated_originals = 0
        updated_duplicates = 0
        cleared = 0
        unchanged = 0

        with transaction.atomic():
            for group in groups:
                if not group:
                    continue

                assets = list(
                    Asset.objects.filter(duplicate_group=group)
                    .order_by("remote_created_at", "first_seen_at", "remote_item_id")
                )

                if len(assets) < 2:
                    # Clear stale roles if only one remains
                    for asset in assets:
                        if asset.duplicate_role:
                            if not dry_run:
                                asset.duplicate_role = ""
                                asset.save(update_fields=["duplicate_role", "updated_at"])
                            cleared += 1
                        else:
                            unchanged += 1
                    continue

                # First = original, rest = duplicate
                original = assets[0]
                if original.duplicate_role != "original":
                    if not dry_run:
                        original.duplicate_role = "original"
                        original.save(update_fields=["duplicate_role", "updated_at"])
                    updated_originals += 1
                else:
                    unchanged += 1

                for dup in assets[1:]:
                    if dup.duplicate_role != "duplicate":
                        if not dry_run:
                            dup.duplicate_role = "duplicate"
                            dup.save(update_fields=["duplicate_role", "updated_at"])
                        updated_duplicates += 1
                    else:
                        unchanged += 1

        mode = "[DRY RUN] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(
            f"{mode}Done: {updated_originals} originals, {updated_duplicates} duplicates, "
            f"{cleared} cleared, {unchanged} unchanged."
        ))

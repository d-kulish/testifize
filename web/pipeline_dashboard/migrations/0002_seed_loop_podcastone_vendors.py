from __future__ import annotations

from django.db import migrations


def seed_vendors(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    for name, parser_key in [
        ("Loop", "loop"),
        ("PodcastOne", "podcastone"),
    ]:
        vendor_model.objects.get_or_create(
            name=name,
            defaults={
                "parser_key": parser_key,
                "is_active": True,
            },
        )


def unseed_vendors(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    vendor_model.objects.filter(name__in=["Loop", "PodcastOne"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_dashboard", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_vendors, unseed_vendors),
    ]

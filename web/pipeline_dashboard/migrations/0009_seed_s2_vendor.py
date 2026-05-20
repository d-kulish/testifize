from django.db import migrations


def seed_s2_vendor(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    folder_model = apps.get_model("pipeline_dashboard", "ShareFileFolder")

    s2, _ = vendor_model.objects.get_or_create(
        name="S2",
        defaults={
            "parser_key": "S2",
            "is_active": True,
        },
    )

    # Assign S2 to the pm folder if it exists
    for folder in folder_model.objects.filter(label__icontains="pm"):
        folder.vendor = s2
        folder.save(update_fields=["vendor", "updated_at"])


def unseed_s2_vendor(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    folder_model = apps.get_model("pipeline_dashboard", "ShareFileFolder")

    s2 = vendor_model.objects.filter(name="S2").first()
    if s2:
        folder_model.objects.filter(vendor=s2).update(vendor=None)
    vendor_model.objects.filter(name="S2").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_dashboard", "0008_asset_is_active"),
    ]

    operations = [
        migrations.RunPython(seed_s2_vendor, unseed_s2_vendor),
    ]

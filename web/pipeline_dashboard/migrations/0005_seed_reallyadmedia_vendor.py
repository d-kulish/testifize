from django.db import migrations


def seed_rallyadmedia_vendor(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    vendor_model.objects.get_or_create(
        name="RallyAdMedia",
        defaults={
            "parser_key": "rallyadmedia",
            "is_active": True,
        },
    )


def unseed_rallyadmedia_vendor(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    vendor_model.objects.filter(name="RallyAdMedia", parser_key="rallyadmedia").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_dashboard", "0004_seed_josh_folder_vendors"),
    ]

    operations = [
        migrations.RunPython(seed_rallyadmedia_vendor, unseed_rallyadmedia_vendor),
    ]

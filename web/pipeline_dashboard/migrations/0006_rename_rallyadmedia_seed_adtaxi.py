from django.db import migrations


def seed_vendor_updates(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")

    vendor_model.objects.filter(name="ReallyAdMedia").update(
        name="RallyAdMedia",
        parser_key="rallyadmedia",
        is_active=True,
    )
    vendor_model.objects.get_or_create(
        name="RallyAdMedia",
        defaults={
            "parser_key": "rallyadmedia",
            "is_active": True,
        },
    )
    vendor_model.objects.get_or_create(
        name="AdTaxi",
        defaults={
            "parser_key": "adtaxi",
            "is_active": True,
        },
    )


def unseed_vendor_updates(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    vendor_model.objects.filter(name="AdTaxi", parser_key="adtaxi").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_dashboard", "0005_seed_reallyadmedia_vendor"),
    ]

    operations = [
        migrations.RunPython(seed_vendor_updates, unseed_vendor_updates),
    ]

from django.db import migrations


def seed_josh_folder_vendors(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    for name, parser_key in [
        ("Octopus", "octopus"),
        ("TVM", "tvm"),
        ("TAIV", "taiv"),
    ]:
        vendor_model.objects.get_or_create(
            name=name,
            defaults={
                "parser_key": parser_key,
                "is_active": True,
            },
        )


def unseed_josh_folder_vendors(apps, schema_editor):
    vendor_model = apps.get_model("pipeline_dashboard", "Vendor")
    vendor_model.objects.filter(name__in=["Octopus", "TVM", "TAIV"]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline_dashboard", "0003_alter_asset_status_parsedoutput"),
    ]

    operations = [
        migrations.RunPython(seed_josh_folder_vendors, unseed_josh_folder_vendors),
    ]

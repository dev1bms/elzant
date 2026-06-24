from django.db import migrations


def seed_singleton(apps, schema_editor):
    """Ensure the WeddingConfig singleton exists with default names/date so it
    appears in the admin right after deploy. Venue/time/hijri are left blank as
    placeholders to be filled from the admin."""
    WeddingConfig = apps.get_model("core", "WeddingConfig")
    WeddingConfig.objects.get_or_create(pk=1)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_singleton, noop),
    ]

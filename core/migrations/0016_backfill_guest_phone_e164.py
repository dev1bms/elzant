from django.db import migrations


def backfill_e164(apps, schema_editor):
    """Populate phone_e164 for existing guests so the inbound WhatsApp RSVP
    webhook (which matches on phone_e164 only) can find them."""
    from core.whatsapp import normalize_phone

    WeddingGuest = apps.get_model("core", "WeddingGuest")
    for g in WeddingGuest.objects.exclude(phone_number=""):
        e = normalize_phone(g.phone_number) or ""
        if e and e != g.phone_e164:
            g.phone_e164 = e
            g.save(update_fields=["phone_e164"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0015_weddingconfig_greeting_cta_label_and_more"),
    ]

    operations = [
        migrations.RunPython(backfill_e164, migrations.RunPython.noop),
    ]

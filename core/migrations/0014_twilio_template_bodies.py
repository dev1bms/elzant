from django.db import migrations

# Twilio Content Templates use positional variables: {{1}} = guest name,
# {{2}} = the personal invitation link (sent inline). Re-align the seeded
# preview wordings (from 0011) to that 2-variable shape.
BODIES = {
    "invite_formal_ar": (
        "السلام عليكم {{1}} 🌿\n"
        "يتشرّف أهل العروسين بدعوتكم لحضور حفل زفاف محمود ورينان.\n"
        "تفضّلوا بفتح دعوتكم الخاصة: {{2}}"
    ),
    "invite_warm_ar": (
        "أهلاً {{1}} 🤍\n"
        "فرحتنا ما تكتمل إلا بوجودكم! ندعوكم لمشاركتنا حفل زفاف محمود ورينان.\n"
        "دعوتكم الخاصة: {{2}}"
    ),
    "invite_short_ar": (
        "{{1}}، يسعدنا دعوتكم لحضور حفل زفاف محمود ورينان 🌿\n"
        "دعوتكم الخاصة: {{2}}"
    ),
    "invite_religious_ar": (
        "بسم الله الرحمن الرحيم\n"
        "السلام عليكم {{1}} ورحمة الله 🤍\n"
        "«وَمِنْ آيَاتِهِ أَنْ خَلَقَ لَكُم مِّنْ أَنفُسِكُمْ أَزْوَاجًا لِّتَسْكُنُوا إِلَيْهَا».\n"
        "ندعوكم لحضور حفل زفاف محمود ورينان — دعوتكم الخاصة: {{2}}"
    ),
}


def update_bodies(apps, schema_editor):
    WhatsAppTemplate = apps.get_model("core", "WhatsAppTemplate")
    for name, body in BODIES.items():
        WhatsAppTemplate.objects.filter(name=name, language="ar").update(
            body_preview_ar=body,
            variables_map=["guest_name", "invitation_link"],
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_twilio_config"),
    ]

    operations = [
        migrations.RunPython(update_bodies, migrations.RunPython.noop),
    ]

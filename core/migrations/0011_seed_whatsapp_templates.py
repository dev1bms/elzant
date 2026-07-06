from django.db import migrations

# Ready-made Arabic invitation wordings. These are seeded as WhatsAppTemplate
# rows (is_approved=False) so the admin can pick one and submit it to Meta for
# approval. Body variable {{1}} = guest name; the invitation button uses a
# dynamic URL (base https://elzant.com/i/ + the guest token). The exact copy is
# also in docs/whatsapp-setup-guide.html for pasting into Meta's template editor.
TEMPLATES = [
    {
        "name": "invite_formal_ar",
        "body": (
            "السلام عليكم {{1}} 🌿\n"
            "يتشرّف أهل العروسين بدعوتكم لحضور حفل زفاف محمود ورينان.\n"
            "تفضّلوا بفتح دعوتكم الخاصة من الزر أدناه — بانتظار تشريفكم."
        ),
    },
    {
        "name": "invite_warm_ar",
        "body": (
            "أهلاً {{1}} 🤍\n"
            "فرحتنا ما تكتمل إلا بوجودكم! ندعوكم لمشاركتنا حفل زفاف محمود ورينان.\n"
            "دعوتكم الخاصة بالزر أدناه 👇"
        ),
    },
    {
        "name": "invite_short_ar",
        "body": (
            "{{1}}، يسعدنا دعوتكم لحضور حفل زفاف محمود ورينان 🌿\n"
            "دعوتكم الخاصة بالزر أدناه."
        ),
    },
    {
        "name": "invite_religious_ar",
        "body": (
            "بسم الله الرحمن الرحيم\n"
            "السلام عليكم {{1}} ورحمة الله 🤍\n"
            "«وَمِنْ آيَاتِهِ أَنْ خَلَقَ لَكُم مِّنْ أَنفُسِكُمْ أَزْوَاجًا لِّتَسْكُنُوا إِلَيْهَا».\n"
            "ندعوكم لحضور حفل زفاف محمود ورينان — دعوتكم الخاصة بالزر أدناه."
        ),
    },
]


def seed(apps, schema_editor):
    WhatsAppTemplate = apps.get_model("core", "WhatsAppTemplate")
    for t in TEMPLATES:
        WhatsAppTemplate.objects.get_or_create(
            name=t["name"],
            language="ar",
            defaults={
                "category": "utility",
                "body_preview_ar": t["body"],
                "variables_map": ["guest_name"],
                "is_approved": False,
                "active": True,
            },
        )


def unseed(apps, schema_editor):
    WhatsAppTemplate = apps.get_model("core", "WhatsAppTemplate")
    WhatsAppTemplate.objects.filter(
        name__in=[t["name"] for t in TEMPLATES], language="ar"
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_whatsappconfig_secrets"),
    ]

    operations = [
        migrations.RunPython(seed, unseed),
    ]

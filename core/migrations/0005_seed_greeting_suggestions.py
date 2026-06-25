from django.db import migrations

DEFAULTS = [
    ("ألف مبروك للعروسين، ربنا يتمّم لكم على خير.", "short"),
    ("بارك الله لكما وبارك عليكما وجمع بينكما في خير.", "religious"),
    ("فرحتنا كبيرة فيكم، جعل الله أيامكم كلها سعادة.", "family"),
    ("أجمل التهاني للعروسين، حياة مليئة بالحب والبركة.", "nice"),
    ("من القلب ألف مبروك، وربنا يسعدكم ويهنيكم.", "short"),
    ("أسأل الله أن يجعل بيتكما عامراً بالمودّة والرحمة.", "religious"),
]


def seed(apps, schema_editor):
    Suggestion = apps.get_model("core", "GreetingSuggestion")
    if Suggestion.objects.exists():
        return
    for i, (text, category) in enumerate(DEFAULTS):
        Suggestion.objects.create(text_ar=text, category=category, active=True, sequence=i)


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [("core", "0004_greetingsuggestion_weddingguest_and_more")]

    operations = [migrations.RunPython(seed, unseed)]

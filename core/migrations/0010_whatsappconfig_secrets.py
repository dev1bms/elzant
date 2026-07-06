import os

from django.db import migrations, models


def copy_secrets_from_env(apps, schema_editor):
    """One-time convenience: if the WhatsApp secrets were previously provided via
    environment variables (.env), copy them into the singleton so nothing breaks
    after the move to admin-managed secrets. No-op when the vars are absent/empty
    or a value is already set in the row."""
    WhatsAppConfig = apps.get_model("core", "WhatsAppConfig")
    cfg, _ = WhatsAppConfig.objects.get_or_create(pk=1)
    changed = False
    for field, env_key in (
        ("api_token", "WHATSAPP_TOKEN"),
        ("app_secret", "WHATSAPP_APP_SECRET"),
        ("verify_token", "WHATSAPP_VERIFY_TOKEN"),
        ("api_version", "WHATSAPP_API_VERSION"),
    ):
        val = os.environ.get(env_key, "")
        if val and not getattr(cfg, field, ""):
            setattr(cfg, field, val)
            changed = True
    if changed:
        cfg.save()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0009_alter_weddingconfig_privacy_notice_short"),
    ]

    operations = [
        migrations.AddField(
            model_name="whatsappconfig",
            name="api_token",
            field=models.TextField(blank=True, verbose_name="توكن الوصول (Access Token)"),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="app_secret",
            field=models.CharField(blank=True, max_length=100, verbose_name="App Secret"),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="verify_token",
            field=models.CharField(blank=True, max_length=100, verbose_name="Verify Token (Webhook)"),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="api_version",
            field=models.CharField(default="v21.0", max_length=10, verbose_name="إصدار Graph API"),
        ),
        migrations.RunPython(copy_secrets_from_env, migrations.RunPython.noop),
    ]

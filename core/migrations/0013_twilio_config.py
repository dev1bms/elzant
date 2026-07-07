from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0012_greeting_status_held"),
    ]

    operations = [
        # --- Twilio fields on WhatsAppConfig ---
        migrations.AddField(
            model_name="whatsappconfig",
            name="twilio_account_sid",
            field=models.CharField(blank=True, max_length=64, verbose_name="Twilio Account SID"),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="twilio_auth_token",
            field=models.CharField(blank=True, max_length=100, verbose_name="Twilio Auth Token"),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="twilio_from",
            field=models.CharField(
                blank=True, max_length=25,
                help_text="مثل +14155238886 (رقم Twilio/الـSandbox). يُضاف whatsapp: تلقائياً.",
                verbose_name="رقم واتساب المُرسِل (E.164)",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="messaging_service_sid",
            field=models.CharField(
                blank=True, max_length=64,
                help_text="بديل عن رقم المُرسِل — إن ضُبط يُستخدم بدله.",
                verbose_name="Messaging Service SID (اختياري)",
            ),
        ),
        migrations.AddField(
            model_name="whatsappconfig",
            name="content_sid",
            field=models.CharField(
                blank=True, max_length=64,
                help_text="قالب المحتوى المعتمد في Twilio لرسالة الدعوة.",
                verbose_name="Content Template SID (HX...)",
            ),
        ),
        # --- Remove the old Meta Cloud API fields ---
        migrations.RemoveField(model_name="whatsappconfig", name="phone_number_id"),
        migrations.RemoveField(model_name="whatsappconfig", name="waba_id"),
        migrations.RemoveField(model_name="whatsappconfig", name="default_template_name"),
        migrations.RemoveField(model_name="whatsappconfig", name="template_lang"),
        migrations.RemoveField(model_name="whatsappconfig", name="api_token"),
        migrations.RemoveField(model_name="whatsappconfig", name="app_secret"),
        migrations.RemoveField(model_name="whatsappconfig", name="verify_token"),
        migrations.RemoveField(model_name="whatsappconfig", name="api_version"),
        # --- WhatsAppTemplate: map a ready wording to a Twilio Content SID ---
        migrations.AddField(
            model_name="whatsapptemplate",
            name="content_sid",
            field=models.CharField(blank=True, max_length=64, verbose_name="Content Template SID (Twilio)"),
        ),
        migrations.AlterField(
            model_name="whatsapptemplate",
            name="is_approved",
            field=models.BooleanField(default=False, verbose_name="معتمد"),
        ),
    ]

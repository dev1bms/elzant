from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0011_seed_whatsapp_templates"),
    ]

    operations = [
        migrations.AlterField(
            model_name="greeting",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "بانتظار"),
                    ("approved", "ظاهرة"),
                    ("rejected", "محظورة"),
                    ("held", "محجوزة للمراجعة"),
                ],
                db_index=True,
                default="approved",
                max_length=10,
            ),
        ),
    ]

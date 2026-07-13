from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_alter_printerconfig_baudrate"),
    ]

    operations = [
        migrations.AddField(
            model_name="printerconfig",
            name="printer_type",
            field=models.CharField(
                choices=[("DT230_FISCAL", "Tally Dascom DT-230 (Fiscal)")],
                default="DT230_FISCAL",
                max_length=32,
                verbose_name="Tipo de impresora",
            ),
        ),
        migrations.AddField(
            model_name="printerconfig",
            name="updated_at",
            field=models.DateTimeField(
                auto_now=True,
                default=timezone.now,
                verbose_name="Actualizado",
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="printerconfig",
            name="port",
            field=models.CharField(
                blank=True,
                default="",
                max_length=20,
                verbose_name="Puerto COM",
            ),
        ),
    ]

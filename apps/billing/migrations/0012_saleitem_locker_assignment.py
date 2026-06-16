from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0011_report_email"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleitem",
            name="requires_locker_assignment",
            field=models.BooleanField(default=False, verbose_name="Requiere asignación de casillero"),
        ),
        migrations.AddField(
            model_name="saleitem",
            name="default_rental_days",
            field=models.PositiveSmallIntegerField(default=30, verbose_name="Días de alquiler por defecto"),
        ),
    ]

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0025_corporate_plan"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clientbillingevent",
            name="event_type",
            field=models.CharField(
                choices=[
                    ("CUT_DATE_CHANGED", "Cambio de fecha de corte"),
                    ("SUBSCRIPTION_REACTIVATED", "Reactivación de suscripción"),
                    ("LATE_FEE_APPLIED", "Multa aplicada"),
                    ("LATE_FEE_WAIVED", "Multa omitida"),
                    ("MEMBERSHIP_DELETED", "Membresía eliminada"),
                    ("ADMIN_ACCESS_GRANTED", "Acceso administrativo asignado"),
                ],
                max_length=32,
                verbose_name="Tipo",
            ),
        ),
    ]

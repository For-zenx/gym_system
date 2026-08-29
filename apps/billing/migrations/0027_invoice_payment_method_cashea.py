from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0026_admin_access_granted_event_type"),
    ]

    operations = [
        migrations.AlterField(
            model_name="invoice",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CASH_VES", "Efectivo Bs"),
                    ("CASH_USD", "Efectivo $"),
                    ("DEBIT", "Débito"),
                    ("MOBILE", "Pago móvil"),
                    ("CASHEA", "Cashea"),
                    ("MIXED", "Mixto"),
                ],
                max_length=16,
                null=True,
                verbose_name="Forma de pago",
            ),
        ),
    ]

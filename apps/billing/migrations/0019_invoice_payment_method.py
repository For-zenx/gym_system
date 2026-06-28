from django.db import migrations, models

import apps.clients.fields


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0018_billing_settings_fixed_grace_days"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoice",
            name="payment_method",
            field=models.CharField(
                blank=True,
                choices=[
                    ("CASH_VES", "Efectivo Bs"),
                    ("CASH_USD", "Efectivo $"),
                    ("DEBIT", "Débito"),
                    ("MOBILE", "Pago móvil"),
                    ("MIXED", "Mixto"),
                ],
                max_length=16,
                null=True,
                verbose_name="Forma de pago",
            ),
        ),
        migrations.AddField(
            model_name="invoice",
            name="payment_splits",
            field=apps.clients.fields.SQLiteJSONField(
                blank=True,
                default=list,
                verbose_name="Desglose de pago mixto",
            ),
        ),
    ]

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0019_invoice_payment_method"),
        ("classes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceline",
            name="class_registration",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invoice_lines",
                to="classes.classregistration",
                verbose_name="Inscripción a clase",
            ),
        ),
        migrations.AlterField(
            model_name="invoiceline",
            name="line_kind",
            field=models.CharField(
                choices=[
                    ("MEMBERSHIP", "Membresía"),
                    ("PRODUCT", "Producto o servicio"),
                    ("LATE_FEE", "Multa"),
                    ("CLASS", "Clase"),
                ],
                max_length=16,
                verbose_name="Tipo de línea",
            ),
        ),
    ]

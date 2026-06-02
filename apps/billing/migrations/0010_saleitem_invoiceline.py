from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import apps.clients.fields


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0009_billing_ops"),
    ]

    operations = [
        migrations.CreateModel(
            name="SaleItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, verbose_name="Nombre")),
                ("description", models.TextField(blank=True, verbose_name="Descripción")),
                (
                    "item_type",
                    models.CharField(
                        choices=[("SERVICE", "Servicio"), ("PRODUCT", "Producto")],
                        default="SERVICE",
                        max_length=10,
                        verbose_name="Tipo",
                    ),
                ),
                ("price_usd", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Precio (USD)")),
                ("is_active", models.BooleanField(default=True, verbose_name="Activo")),
                ("sort_order", models.PositiveIntegerField(default=0, verbose_name="Orden")),
            ],
            options={
                "verbose_name": "Producto o servicio",
                "verbose_name_plural": "Productos y servicios",
                "ordering": ["sort_order", "name", "id"],
            },
        ),
        migrations.CreateModel(
            name="InvoiceLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "line_kind",
                    models.CharField(
                        choices=[
                            ("MEMBERSHIP", "Membresía"),
                            ("PRODUCT", "Producto o servicio"),
                            ("LATE_FEE", "Multa"),
                        ],
                        max_length=16,
                        verbose_name="Tipo de línea",
                    ),
                ),
                ("description", models.CharField(max_length=255, verbose_name="Descripción")),
                ("quantity", models.PositiveIntegerField(default=1, verbose_name="Cantidad")),
                (
                    "unit_price_usd",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=12,
                        verbose_name="Precio unitario (USD)",
                    ),
                ),
                ("amount_ves", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Monto (VES)")),
                ("metadata", apps.clients.fields.SQLiteJSONField(blank=True, default=dict, verbose_name="Metadatos")),
                (
                    "invoice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lines",
                        to="billing.invoice",
                        verbose_name="Factura",
                    ),
                ),
                (
                    "membership",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoice_lines",
                        to="billing.membership",
                        verbose_name="Membresía",
                    ),
                ),
                (
                    "sale_item",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="invoice_lines",
                        to="billing.saleitem",
                        verbose_name="Ítem de catálogo",
                    ),
                ),
            ],
            options={
                "verbose_name": "Línea de factura",
                "verbose_name_plural": "Líneas de factura",
                "ordering": ["id"],
            },
        ),
    ]

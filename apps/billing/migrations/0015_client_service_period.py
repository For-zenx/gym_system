from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_towel_service_item(apps, schema_editor):
    SaleItem = apps.get_model("billing", "SaleItem")
    if SaleItem.objects.filter(item_type="SERVICE").exclude(system_code="LOCKER_RENTAL").exists():
        return
    if SaleItem.objects.filter(name__icontains="toalla").exists():
        return
    SaleItem.objects.create(
        name="Servicio de toallas",
        description="Acceso al servicio de toallas durante el periodo del plan.",
        item_type="SERVICE",
        price_usd=Decimal("3.00"),
        is_active=True,
    )


def unseed_towel_service_item(apps, schema_editor):
    SaleItem = apps.get_model("billing", "SaleItem")
    SaleItem.objects.filter(
        name="Servicio de toallas",
        system_code__isnull=True,
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("billing", "0014_saleitem_system_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientServicePeriod",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField(verbose_name="Inicio")),
                ("end_date", models.DateField(verbose_name="Vencimiento")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Activo"),
                            ("EXPIRED", "Vencido"),
                            ("CANCELLED", "Cancelado"),
                        ],
                        default="ACTIVE",
                        max_length=16,
                        verbose_name="Estado",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creado")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Actualizado")),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="service_periods",
                        to="clients.client",
                        verbose_name="Afiliado",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_service_periods",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Registrado por",
                    ),
                ),
                (
                    "invoice_line",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="service_periods",
                        to="billing.invoiceline",
                        verbose_name="Línea de factura",
                    ),
                ),
                (
                    "membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="service_periods",
                        to="billing.membership",
                        verbose_name="Membresía",
                    ),
                ),
                (
                    "sale_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="service_periods",
                        to="billing.saleitem",
                        verbose_name="Servicio",
                    ),
                ),
            ],
            options={
                "verbose_name": "Periodo de servicio",
                "verbose_name_plural": "Periodos de servicio",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="clientserviceperiod",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status", "ACTIVE")),
                fields=("client", "sale_item"),
                name="unique_active_service_period_per_client_item",
            ),
        ),
        migrations.RunPython(seed_towel_service_item, unseed_towel_service_item),
    ]

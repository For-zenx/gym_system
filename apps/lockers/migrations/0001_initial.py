from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("billing", "0012_saleitem_locker_assignment"),
        ("clients", "0006_task035_fixed_flexible_billing"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Locker",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.CharField(max_length=30, unique=True, verbose_name="Número")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("AVAILABLE", "Disponible"),
                            ("OCCUPIED", "Ocupado"),
                            ("MAINTENANCE", "Mantenimiento"),
                            ("INACTIVE", "Inactivo"),
                        ],
                        default="AVAILABLE",
                        max_length=16,
                        verbose_name="Estado",
                    ),
                ),
                ("notes", models.TextField(blank=True, verbose_name="Notas")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creado")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Actualizado")),
            ],
            options={
                "verbose_name": "Casillero",
                "verbose_name_plural": "Casilleros",
                "ordering": ["number", "id"],
            },
        ),
        migrations.CreateModel(
            name="LockerRental",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField(verbose_name="Inicio")),
                ("end_date", models.DateField(verbose_name="Vencimiento")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("ACTIVE", "Activo"),
                            ("EXPIRED", "Vencido"),
                            ("RELEASED", "Liberado"),
                            ("CANCELLED", "Cancelado"),
                        ],
                        default="ACTIVE",
                        max_length=16,
                        verbose_name="Estado",
                    ),
                ),
                ("released_at", models.DateTimeField(blank=True, null=True, verbose_name="Liberado el")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creado")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Actualizado")),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="locker_rentals",
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
                        related_name="created_locker_rentals",
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
                        related_name="locker_rentals",
                        to="billing.invoiceline",
                        verbose_name="Línea de factura",
                    ),
                ),
                (
                    "locker",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="rentals",
                        to="lockers.locker",
                        verbose_name="Casillero",
                    ),
                ),
                (
                    "released_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="released_locker_rentals",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Liberado por",
                    ),
                ),
                (
                    "sale_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="locker_rentals",
                        to="billing.saleitem",
                        verbose_name="Tarifa cobrada",
                    ),
                ),
            ],
            options={
                "verbose_name": "Alquiler de casillero",
                "verbose_name_plural": "Alquileres de casilleros",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="lockerrental",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="ACTIVE"),
                fields=("locker",),
                name="unique_active_rental_per_locker",
            ),
        ),
        migrations.AddConstraint(
            model_name="lockerrental",
            constraint=models.UniqueConstraint(
                condition=models.Q(status="ACTIVE"),
                fields=("client",),
                name="unique_active_locker_rental_per_client",
            ),
        ),
    ]

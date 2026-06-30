from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("billing", "0019_invoice_payment_method"),
        ("clients", "0010_guest_pass_nullable_sponsor"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ClassSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("title", models.CharField(max_length=100, verbose_name="Nombre de la clase")),
                ("session_date", models.DateField(verbose_name="Fecha")),
                ("start_time", models.TimeField(verbose_name="Hora de inicio")),
                ("end_time", models.TimeField(blank=True, null=True, verbose_name="Hora de fin")),
                ("instructor_name", models.CharField(blank=True, max_length=255, verbose_name="Entrenador (texto)")),
                (
                    "price_usd",
                    models.DecimalField(
                        decimal_places=2,
                        default=Decimal("0.00"),
                        max_digits=12,
                        verbose_name="Precio por persona (USD)",
                    ),
                ),
                (
                    "capacity",
                    models.PositiveIntegerField(
                        blank=True,
                        help_text="Dejar vacío para cupo ilimitado.",
                        null=True,
                        verbose_name="Cupo máximo",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("SCHEDULED", "Programada"),
                            ("COMPLETED", "Realizada"),
                            ("CANCELLED", "Cancelada"),
                        ],
                        default="SCHEDULED",
                        max_length=16,
                        verbose_name="Estado",
                    ),
                ),
                (
                    "attendance_reported",
                    models.PositiveIntegerField(blank=True, null=True, verbose_name="Asistencia reportada"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="Notas")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creado")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Actualizado")),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_class_sessions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Registrado por",
                    ),
                ),
                (
                    "instructor",
                    models.ForeignKey(
                        blank=True,
                        limit_choices_to={"person_category": "TRAINER"},
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="taught_class_sessions",
                        to="clients.client",
                        verbose_name="Entrenador registrado",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sesión de clase",
                "verbose_name_plural": "Sesiones de clase",
                "ordering": ["-session_date", "-start_time", "-id"],
            },
        ),
        migrations.CreateModel(
            name="ClassRegistration",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("PENDING_PAYMENT", "Por cobrar"),
                            ("CONFIRMED", "Pagado"),
                            ("CANCELLED", "Cancelado"),
                        ],
                        default="PENDING_PAYMENT",
                        max_length=20,
                        verbose_name="Estado",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Creado")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Actualizado")),
                (
                    "client",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="class_registrations",
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
                        related_name="created_class_registrations",
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
                        related_name="class_registrations",
                        to="billing.invoiceline",
                        verbose_name="Línea de factura",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registrations",
                        to="classes.classsession",
                        verbose_name="Sesión",
                    ),
                ),
            ],
            options={
                "verbose_name": "Inscripción a clase",
                "verbose_name_plural": "Inscripciones a clase",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.AddConstraint(
            model_name="classregistration",
            constraint=models.UniqueConstraint(
                condition=models.Q(("status__in", ["PENDING_PAYMENT", "CONFIRMED"])),
                fields=("session", "client"),
                name="unique_active_class_registration_per_client_session",
            ),
        ),
    ]

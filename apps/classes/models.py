from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.clients.models import Client, PersonCategory


class ClassSession(models.Model):
    class Status(models.TextChoices):
        SCHEDULED = "SCHEDULED", "Programada"
        COMPLETED = "COMPLETED", "Realizada"
        CANCELLED = "CANCELLED", "Cancelada"

    title = models.CharField("Nombre de la clase", max_length=100)
    session_date = models.DateField("Fecha")
    start_time = models.TimeField("Hora de inicio")
    end_time = models.TimeField("Hora de fin", null=True, blank=True)
    instructor = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="taught_class_sessions",
        verbose_name="Entrenador registrado",
        limit_choices_to={"person_category": PersonCategory.TRAINER},
    )
    instructor_name = models.CharField("Entrenador (texto)", max_length=255, blank=True)
    price_usd = models.DecimalField(
        "Precio por persona (USD)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    capacity = models.PositiveIntegerField(
        "Cupo máximo",
        null=True,
        blank=True,
        help_text="Dejar vacío para cupo ilimitado.",
    )
    status = models.CharField(
        "Estado",
        max_length=16,
        choices=Status.choices,
        default=Status.SCHEDULED,
    )
    attendance_reported = models.PositiveIntegerField(
        "Asistencia reportada",
        null=True,
        blank=True,
    )
    notes = models.TextField("Notas", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_class_sessions",
        verbose_name="Registrado por",
    )
    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Sesión de clase"
        verbose_name_plural = "Sesiones de clase"
        ordering = ["-session_date", "-start_time", "-id"]

    @property
    def is_free(self):
        return self.price_usd <= 0

    @property
    def is_paid(self):
        return self.price_usd > 0

    @property
    def instructor_display(self):
        if self.instructor_id:
            return self.instructor.nombre
        return (self.instructor_name or "").strip() or "Sin asignar"

    @property
    def seats_taken(self):
        if not self.is_paid:
            return 0
        return self.registrations.filter(
            status__in=(
                ClassRegistration.Status.PENDING_PAYMENT,
                ClassRegistration.Status.CONFIRMED,
            )
        ).count()

    @property
    def seats_available(self):
        if self.capacity is None:
            return None
        return max(self.capacity - self.seats_taken, 0)

    @property
    def is_full(self):
        if self.capacity is None:
            return False
        return self.seats_taken >= self.capacity

    def clean(self):
        if self.instructor_id and self.instructor.person_category != PersonCategory.TRAINER:
            raise ValidationError({"instructor": "El entrenador debe ser personal tipo Entrenador (T-)."})
        if not self.instructor_id and not (self.instructor_name or "").strip():
            raise ValidationError("Indique el entrenador registrado o su nombre.")
        if self.price_usd < 0:
            raise ValidationError({"price_usd": "El precio no puede ser negativo."})
        if self.attendance_reported is not None and self.attendance_reported < 0:
            raise ValidationError({"attendance_reported": "La asistencia no puede ser negativa."})

    def __str__(self):
        return "{} — {}".format(self.title, self.session_date.strftime("%d/%m/%Y"))


class ClassRegistration(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "PENDING_PAYMENT", "Por cobrar"
        CONFIRMED = "CONFIRMED", "Pagado"
        CANCELLED = "CANCELLED", "Cancelado"

    session = models.ForeignKey(
        ClassSession,
        on_delete=models.CASCADE,
        related_name="registrations",
        verbose_name="Sesión",
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="class_registrations",
        verbose_name="Afiliado",
    )
    status = models.CharField(
        "Estado",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
    )
    invoice_line = models.ForeignKey(
        "billing.InvoiceLine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_registrations",
        verbose_name="Línea de factura",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_class_registrations",
        verbose_name="Registrado por",
    )
    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Inscripción a clase"
        verbose_name_plural = "Inscripciones a clase"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "client"],
                condition=Q(status__in=["PENDING_PAYMENT", "CONFIRMED"]),
                name="unique_active_class_registration_per_client_session",
            ),
        ]

    @property
    def is_pending_payment(self):
        return self.status == self.Status.PENDING_PAYMENT

    @property
    def is_confirmed(self):
        return self.status == self.Status.CONFIRMED

    def __str__(self):
        return "{} — {}".format(self.client.codigo_afiliado, self.session.title)

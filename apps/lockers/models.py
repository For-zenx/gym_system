from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Locker(models.Model):
    class Status(models.TextChoices):
        AVAILABLE = "AVAILABLE", "Disponible"
        OCCUPIED = "OCCUPIED", "Ocupado"
        MAINTENANCE = "MAINTENANCE", "Mantenimiento"
        INACTIVE = "INACTIVE", "Inactivo"

    number = models.CharField("Número", max_length=30, unique=True)
    status = models.CharField(
        "Estado",
        max_length=16,
        choices=Status.choices,
        default=Status.AVAILABLE,
    )
    notes = models.TextField("Notas", blank=True)
    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Casillero"
        verbose_name_plural = "Casilleros"
        ordering = ["number", "id"]

    @property
    def active_rental(self):
        today = timezone.localdate()
        return (
            self.rentals.select_related("client")
            .filter(status=LockerRental.Status.ACTIVE, end_date__gte=today)
            .order_by("end_date", "id")
            .first()
        )

    def __str__(self):
        return "Casillero {}".format(self.number)


class LockerRental(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Activo"
        EXPIRED = "EXPIRED", "Vencido"
        RELEASED = "RELEASED", "Liberado"
        CANCELLED = "CANCELLED", "Cancelado"

    client = models.ForeignKey(
        "clients.Client",
        on_delete=models.CASCADE,
        related_name="locker_rentals",
        verbose_name="Afiliado",
    )
    locker = models.ForeignKey(
        Locker,
        on_delete=models.PROTECT,
        related_name="rentals",
        verbose_name="Casillero",
    )
    sale_item = models.ForeignKey(
        "billing.SaleItem",
        on_delete=models.PROTECT,
        related_name="locker_rentals",
        verbose_name="Tarifa cobrada",
    )
    invoice_line = models.ForeignKey(
        "billing.InvoiceLine",
        on_delete=models.SET_NULL,
        related_name="locker_rentals",
        verbose_name="Línea de factura",
        null=True,
        blank=True,
    )
    membership = models.ForeignKey(
        "billing.Membership",
        on_delete=models.SET_NULL,
        related_name="locker_rentals",
        verbose_name="Membresía",
        null=True,
        blank=True,
    )
    start_date = models.DateField("Inicio")
    end_date = models.DateField("Vencimiento")
    status = models.CharField(
        "Estado",
        max_length=16,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="created_locker_rentals",
        verbose_name="Registrado por",
        null=True,
        blank=True,
    )
    released_at = models.DateTimeField("Liberado el", null=True, blank=True)
    released_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="released_locker_rentals",
        verbose_name="Liberado por",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Alquiler de casillero"
        verbose_name_plural = "Alquileres de casilleros"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["locker"],
                condition=Q(status="ACTIVE"),
                name="unique_active_rental_per_locker",
            ),
            models.UniqueConstraint(
                fields=["client"],
                condition=Q(status="ACTIVE"),
                name="unique_active_locker_rental_per_client",
            ),
        ]

    @property
    def is_current(self):
        return self.status == self.Status.ACTIVE and self.end_date >= timezone.localdate()

    def __str__(self):
        return "{} — {}".format(self.client.nombre, self.locker)

from django.conf import settings
from django.db import models

from .fields import SQLiteJSONField


class PersonCategory(models.TextChoices):
    MEMBER = "MEMBER", "Afiliado"
    EMPLOYEE = "EMPLOYEE", "Empleado"
    TRAINER = "TRAINER", "Entrenador"
    GUEST = "GUEST", "Invitado"


PERSON_CODE_PREFIX = {
    PersonCategory.MEMBER: "M",
    PersonCategory.EMPLOYEE: "E",
    PersonCategory.TRAINER: "T",
    PersonCategory.GUEST: "G",
}

STAFF_PERSON_CATEGORIES = frozenset({
    PersonCategory.EMPLOYEE,
    PersonCategory.TRAINER,
})


class Client(models.Model):
    SEXO_CHOICES = [
        ('', 'Sin especificar'),
        ('M', 'Masculino'),
        ('F', 'Femenino'),
    ]

    cedula = models.CharField("Cédula", max_length=20, unique=True, blank=True, null=True)
    nombre = models.CharField("Nombre Completo", max_length=255)
    telefono = models.CharField("Teléfono", max_length=20, blank=True, null=True)
    fecha_nacimiento = models.DateField("Fecha de Nacimiento", blank=True, null=True)
    sexo = models.CharField("Sexo", max_length=1, choices=SEXO_CHOICES, blank=True, default='')
    codigo_afiliado = models.CharField("Código", max_length=20, unique=True)
    person_category = models.CharField(
        "Categoría",
        max_length=10,
        choices=PersonCategory.choices,
        default=PersonCategory.MEMBER,
        db_index=True,
    )
    fecha_ingreso = models.DateField(auto_now_add=True)
    fecha_corte_dia = models.PositiveSmallIntegerField(
        "Día de corte (suscripción fija)",
        null=True,
        blank=True,
        help_text="Día del mes para renovación de plan fijo (1-31). Se asigna en el primer pago fijo.",
    )
    terms_accepted_at = models.DateTimeField(
        "Términos aceptados el",
        null=True,
        blank=True,
    )

    # foto_frente alimenta el motor de reconocimiento y la UI; perfiles legacy sin uso activo.
    foto_frente = models.ImageField(upload_to='clients/enrollment/', blank=True, null=True)
    foto_perfil_izq = models.ImageField(upload_to='clients/enrollment/', blank=True, null=True)
    foto_perfil_der = models.ImageField(upload_to='clients/enrollment/', blank=True, null=True)

    face_id_embeddings = SQLiteJSONField(blank=True, null=True)

    class Meta:
        verbose_name = "Afiliado"
        verbose_name_plural = "Afiliados"

    def __str__(self):
        return f"{self.nombre} ({self.codigo_afiliado})"

    @property
    def is_enrolled(self):
        return bool(self.foto_frente and self.face_id_embeddings)

    @property
    def is_member(self):
        return self.person_category == PersonCategory.MEMBER

    @property
    def is_staff_person(self):
        return self.person_category in STAFF_PERSON_CATEGORIES

    @property
    def is_guest(self):
        return self.person_category == PersonCategory.GUEST

    @property
    def access_requires_membership(self):
        return self.person_category == PersonCategory.MEMBER

    @property
    def access_requires_guest_pass(self):
        return self.person_category == PersonCategory.GUEST

    @property
    def can_purchase_membership(self):
        return self.person_category == PersonCategory.MEMBER

    def get_category_display_short(self):
        return self.get_person_category_display()

    @property
    def active_memberships(self):
        from datetime import date
        today = date.today()
        return self.memberships.filter(fecha_inicio__lte=today, fecha_fin__gte=today)

    @property
    def has_access_today(self):
        return self.active_memberships.exists()

    @property
    def has_active_flexible(self):
        from datetime import date
        from apps.billing.models import Plan

        today = date.today()
        return self.memberships.filter(
            plan__billing_type=Plan.BillingType.FLEXIBLE,
            fecha_inicio__lte=today,
            fecha_fin__gte=today,
        ).exists()

    @property
    def next_fixed_expiry(self):
        from datetime import date
        from apps.billing.models import Plan

        today = date.today()
        membership = (
            self.memberships.filter(
                plan__billing_type=Plan.BillingType.FIXED,
                fecha_fin__gte=today,
            )
            .order_by("fecha_fin")
            .first()
        )
        return membership.fecha_fin if membership else None

    @property
    def fixed_subscription_status(self):
        from datetime import date
        from apps.billing.models import Plan

        if not self.fecha_corte_dia:
            return 'NONE'
        today = date.today()
        if self.memberships.filter(
            plan__billing_type=Plan.BillingType.FIXED,
            fecha_inicio__lte=today,
            fecha_fin__gte=today,
        ).exists():
            return 'ACTIVE'
        return 'SUSPENDED'


class GuestPass(models.Model):
    guest = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="guest_passes",
        verbose_name="Invitado",
    )
    sponsor = models.ForeignKey(
        Client,
        on_delete=models.PROTECT,
        related_name="sponsored_guest_passes",
        verbose_name="Afiliado responsable",
        blank=True,
        null=True,
    )
    valid_from = models.DateField("Válido desde")
    valid_until = models.DateField("Válido hasta")
    registered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="registered_guest_passes",
        verbose_name="Registrado por",
        blank=True,
        null=True,
    )
    notes = models.CharField("Notas", max_length=500, blank=True)
    revoked_at = models.DateTimeField("Revocado el", blank=True, null=True)
    created_at = models.DateTimeField("Creado el", auto_now_add=True)

    class Meta:
        verbose_name = "Pase de invitado"
        verbose_name_plural = "Pases de invitado"
        ordering = ["-created_at"]

    def __str__(self):
        return "{} — {} hasta {}".format(
            self.guest.nombre,
            self.sponsor.nombre,
            self.valid_until.strftime("%d/%m/%Y"),
        )

from django.db import models

from .fields import SQLiteJSONField


class Client(models.Model):
    SEXO_CHOICES = [
        ('', 'Sin especificar'),
        ('M', 'Masculino'),
        ('F', 'Femenino'),
    ]

    cedula = models.CharField("Cédula", max_length=20, unique=True)
    nombre = models.CharField("Nombre Completo", max_length=255)
    telefono = models.CharField("Teléfono", max_length=20, blank=True, null=True)
    fecha_nacimiento = models.DateField("Fecha de Nacimiento", blank=True, null=True)
    sexo = models.CharField("Sexo", max_length=1, choices=SEXO_CHOICES, blank=True, default='')
    codigo_afiliado = models.CharField("Cód. Afiliado", max_length=20, unique=True)
    fecha_ingreso = models.DateField(auto_now_add=True)
    fecha_corte_dia = models.PositiveSmallIntegerField(
        "Día de corte (suscripción fija)",
        null=True,
        blank=True,
        help_text="Día del mes para renovación de plan fijo (1-31). Se asigna en el primer pago fijo.",
    )

    # Las 3 fotos de enrolamiento son el insumo del ai_engine; foto_frente se usa también para display en UI.
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
        return bool(self.foto_frente and self.foto_perfil_izq and self.foto_perfil_der and self.face_id_embeddings)

    @property
    def active_memberships(self):
        from datetime import date
        today = date.today()
        return self.memberships.filter(fecha_inicio__lte=today, fecha_fin__gte=today)

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

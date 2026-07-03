from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.clients.models import Client


class AccessSettings(models.Model):
    post_access_cooldown_seconds = models.PositiveIntegerField(
        "Enfriamiento post-acceso (segundos)",
        default=0,
        help_text="Tiempo mínimo entre accesos biométricos concedidos a la misma persona. 0 = desactivado.",
    )
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Configuración de acceso"
        verbose_name_plural = "Configuración de acceso"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("No se puede eliminar la configuración global de acceso.")

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"post_access_cooldown_seconds": 0})
        return obj

    @property
    def cooldown_enabled(self):
        return self.post_access_cooldown_seconds > 0

    def __str__(self):
        if not self.cooldown_enabled:
            return "Enfriamiento post-acceso desactivado"
        minutes, seconds = divmod(self.post_access_cooldown_seconds, 60)
        if seconds:
            return "Enfriamiento post-acceso: {} min {} s".format(minutes, seconds)
        return "Enfriamiento post-acceso: {} min".format(minutes)

class AccessLog(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="access_logs",
        verbose_name="Afiliado",
        null=True,
        blank=True,
    )
    timestamp = models.DateTimeField("Fecha/Hora", auto_now_add=True)
    resultado = models.BooleanField("Acceso Concedido", default=True)
    motivo = models.CharField("Motivo/Detalle", max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Log de Acceso"
        verbose_name_plural = "Logs de Acceso"
        ordering = ['-timestamp']

    def __str__(self):
        status = "EXITOSO" if self.resultado else "DENEGADO"
        name = self.client.nombre if self.client else "No reconocido"
        return f"{name} - {status} ({self.timestamp.strftime('%d/%m/%Y %H:%M')})"


class ManualTurnstileAccess(models.Model):
    class Reason(models.TextChoices):
        BIOMETRIC_FAILURE = "biometric_failure", "Falla biométrica"
        ADMIN_AUTHORIZATION = "admin_authorization", "Autorización administrativa"
        ENROLLMENT_PENDING = "enrollment_pending", "Enrolamiento pendiente"
        GUEST_OR_VENDOR = "guest_or_vendor", "Invitado o proveedor"
        PAY_LATER = "pay_later", "Paga después"
        EMERGENCY = "emergency", "Emergencia"
        UNSPECIFIED = "unspecified", "Sin razón especificada"
        OTHER = "other", "Otra"

    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        related_name="manual_turnstile_accesses",
        verbose_name="Afiliado",
        blank=True,
        null=True,
    )
    person_name = models.CharField("Nombre registrado", max_length=255)
    reason = models.CharField("Razón", max_length=40, choices=Reason.choices)
    custom_reason = models.CharField("Detalle adicional", max_length=255, blank=True)
    timestamp = models.DateTimeField("Fecha/Hora", auto_now_add=True)
    opened_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="manual_turnstile_accesses",
        verbose_name="Operador",
        blank=True,
        null=True,
    )
    hardware_success = models.BooleanField("Pulso enviado", default=False)
    hardware_error = models.CharField("Error de hardware", max_length=255, blank=True)
    membership_warning = models.CharField("Advertencia de acceso", max_length=255, blank=True)
    port_used = models.CharField("Puerto COM usado", max_length=32, blank=True)

    class Meta:
        verbose_name = "Apertura manual de torniquete"
        verbose_name_plural = "Aperturas manuales de torniquete"
        ordering = ["-timestamp"]

    def __str__(self):
        status = "OK" if self.hardware_success else "ERROR"
        return f"{self.person_name} - {status} ({self.timestamp.strftime('%d/%m/%Y %H:%M')})"

    @property
    def reason_label(self):
        return self.get_reason_display()

    @property
    def hardware_error_display(self):
        if self.hardware_success or not self.hardware_error:
            return ""
        technical_markers = (
            "FileNotFoundError",
            "could not open port",
            "Error de puerto serial",
            "SerialException",
            "TURNSTILE_COM_PORT",
        )
        if any(marker in self.hardware_error for marker in technical_markers):
            return (
                "No se pudo conectar con el torniquete. "
                "Avise al administrador."
            )
        return self.hardware_error

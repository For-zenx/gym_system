from django.conf import settings
from django.db import models
from apps.clients.models import Client

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
        EMERGENCY = "emergency", "Emergencia"
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

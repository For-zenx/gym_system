from django.db import models
from apps.clients.models import Client

class AccessLog(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='access_logs', verbose_name="Afiliado")
    timestamp = models.DateTimeField("Fecha/Hora", auto_now_add=True)
    resultado = models.BooleanField("Acceso Concedido", default=True)
    motivo = models.CharField("Motivo/Detalle", max_length=255, blank=True, null=True)

    class Meta:
        verbose_name = "Log de Acceso"
        verbose_name_plural = "Logs de Acceso"
        ordering = ['-timestamp']

    def __str__(self):
        status = "EXITOSO" if self.resultado else "DENEGADO"
        return f"{self.client.nombre} - {status} ({self.timestamp.strftime('%d/%m/%Y %H:%M')})"

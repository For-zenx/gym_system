from django.db import models
from datetime import timedelta
from django.utils import timezone
from apps.clients.models import Client

class Plan(models.Model):
    nombre = models.CharField("Nombre del Plan", max_length=50) # "Mensual", "Semanal", "Día"
    dias_duracion = models.PositiveIntegerField("Días de Duración") # 30, 7, 1
    precio = models.DecimalField("Precio (VES)", max_digits=12, decimal_places=2) # Siempre en VES

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Planes"

    def __str__(self):
        return f"{self.nombre} ({self.dias_duracion} días)"

class Membership(models.Model):
    # Relación 1:1 para saber el estado actual del cliente rápidamente
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='membership', verbose_name="Afiliado")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, verbose_name="Plan")
    fecha_inicio = models.DateField("Fecha de Inicio", default=timezone.now)
    fecha_fin = models.DateField("Fecha de Vencimiento", editable=False) # Se calcula sola

    class Meta:
        verbose_name = "Membresía"
        verbose_name_plural = "Membresías"

    def save(self, *args, **kwargs):
        # Lógica de cálculo: Se dispara al guardar
        if not self.fecha_fin:
            self.fecha_fin = self.fecha_inicio + timedelta(days=self.plan.dias_duracion)
        super().save(*args, **kwargs)

    @property
    def es_valida(self):
        from datetime import date
        return date.today() <= self.fecha_fin

    def __str__(self):
        return f"Membresía de {self.client.nombre} - Vence: {self.fecha_fin}"

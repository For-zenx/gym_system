from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.utils import timezone
from apps.clients.models import Client

class Plan(models.Model):
    nombre = models.CharField("Nombre del Plan", max_length=50) 
    dias_duracion = models.PositiveIntegerField("Días de Duración") 
    precio = models.DecimalField("Precio (VES)", max_digits=12, decimal_places=2) 

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Planes"

    def __str__(self):
        return f"{self.nombre} ({self.dias_duracion} días)"

class Membership(models.Model):
    client = models.OneToOneField(Client, on_delete=models.CASCADE, related_name='membership', verbose_name="Afiliado")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, verbose_name="Plan")
    fecha_inicio = models.DateField("Fecha de Inicio", default=timezone.now)
    fecha_fin = models.DateField("Fecha de Vencimiento", editable=False) 

    class Meta:
        verbose_name = "Membresía"
        verbose_name_plural = "Membresías"

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio >= self.fecha_fin:
            raise ValidationError("La fecha de inicio debe ser anterior a la de vencimiento.")

    def save(self, *args, **kwargs):
        if not self.fecha_fin:
            self.fecha_fin = self.fecha_inicio + timedelta(days=self.plan.dias_duracion)
        
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def es_valida(self):
        from datetime import date
        return date.today() <= self.fecha_fin

    def __str__(self):
        return f"Membresía de {self.client.nombre} - Vence: {self.fecha_fin}"

class Invoice(models.Model):
    membership = models.ForeignKey(Membership, on_delete=models.CASCADE, related_name='invoices', verbose_name="Membresía")
    monto_total = models.DecimalField("Monto Total (VES)", max_digits=12, decimal_places=2)
    nro_control = models.CharField("Nro. Control Fiscal", max_length=50)
    fecha_emision = models.DateTimeField("Fecha de Emisión", auto_now_add=True)

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        ordering = ['-fecha_emision']

    def __str__(self):
        return f"Factura {self.nro_control} - {self.membership.client.nombre}"

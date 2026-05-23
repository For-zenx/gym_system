from django.db import models
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.utils import timezone
from apps.clients.models import Client

class Plan(models.Model):
    nombre = models.CharField("Nombre del Plan", max_length=50) 
    dias_duracion = models.PositiveIntegerField("Días de Duración") 
    precio_usd = models.DecimalField("Precio (USD)", max_digits=12, decimal_places=2) 
    hora_inicio = models.TimeField("Hora de Inicio", null=True, blank=True, help_text="Dejar en blanco para acceso todo el día")
    hora_fin = models.TimeField("Hora de Fin", null=True, blank=True, help_text="Dejar en blanco para acceso todo el día")
    is_active = models.BooleanField("Activo", default=True, help_text="Si se desactiva, no podrá ser comprado pero mantendrá el historial")

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Planes"

    def __str__(self):
        return f"{self.nombre} ({self.dias_duracion} días) - ${self.precio_usd}"

class ExchangeRate(models.Model):
    tasa_ves = models.DecimalField("Tasa VES/$", max_digits=12, decimal_places=2)
    fecha = models.DateField("Fecha", auto_now_add=True)

    class Meta:
        verbose_name = "Tasa de Cambio"
        verbose_name_plural = "Tasas de Cambio"
        ordering = ['-fecha', '-id']

    @classmethod
    def get_latest(cls):
        return cls.objects.order_by('-fecha', '-id').first()

    def __str__(self):
        return f"{self.fecha}: {self.tasa_ves} VES/$"

class Membership(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='memberships', verbose_name="Afiliado")
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
        return self.fecha_inicio <= date.today() <= self.fecha_fin
        
    def is_valid_now(self, current_time=None):
        if not current_time:
            current_time = timezone.localtime().time()
        
        if not self.es_valida:
            return False
            
        if self.plan.hora_inicio and self.plan.hora_fin:
            return self.plan.hora_inicio <= current_time <= self.plan.hora_fin
        return True

    def __str__(self):
        return f"Membresía de {self.client.nombre} - Vence: {self.fecha_fin}"

class Invoice(models.Model):
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        related_name='invoices',
        verbose_name="Afiliado",
        null=True,
        blank=True,
    )
    membership = models.ForeignKey(Membership, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices', verbose_name="Membresía")
    client_nombre_snapshot = models.CharField("Nombre del Receptor", max_length=255, blank=True)
    client_cedula_snapshot = models.CharField("Cédula del Receptor", max_length=20, blank=True)
    client_codigo_snapshot = models.CharField("Cód. Afiliado (snapshot)", max_length=20, blank=True)
    plan_snapshot = models.CharField("Plan Comprado", max_length=100, blank=True)
    monto_total = models.DecimalField("Monto Total (VES)", max_digits=12, decimal_places=2)
    nro_control = models.CharField("Nro. Control Fiscal", max_length=50)
    fecha_emision = models.DateTimeField("Fecha de Emisión", auto_now_add=True)
    esta_impresa = models.BooleanField("¿Está Impresa?", default=False)

    class Meta:
        verbose_name = "Factura"
        verbose_name_plural = "Facturas"
        ordering = ['-fecha_emision']

    def set_client_snapshots(self, client):
        self.client_nombre_snapshot = client.nombre
        self.client_cedula_snapshot = client.cedula
        self.client_codigo_snapshot = client.codigo_afiliado

    @property
    def receptor_nombre(self):
        if self.client_nombre_snapshot:
            return self.client_nombre_snapshot
        if self.client:
            return self.client.nombre
        if self.membership and self.membership.client:
            return self.membership.client.nombre
        return "Sin Afiliado"

    @property
    def receptor_cedula(self):
        if self.client_cedula_snapshot:
            return self.client_cedula_snapshot
        if self.client:
            return self.client.cedula
        if self.membership and self.membership.client:
            return self.membership.client.cedula
        return "N/A"

    @property
    def receptor_codigo(self):
        if self.client_codigo_snapshot:
            return self.client_codigo_snapshot
        if self.client:
            return self.client.codigo_afiliado
        if self.membership and self.membership.client:
            return self.membership.client.codigo_afiliado
        return "N/A"

    def get_receptor_for_ticket(self):
        nombre = self.client_nombre_snapshot
        cedula = self.client_cedula_snapshot
        codigo = self.client_codigo_snapshot
        if nombre and cedula and codigo:
            return nombre, cedula, codigo
        if self.client:
            return self.client.nombre, self.client.cedula, self.client.codigo_afiliado
        if self.membership and self.membership.client:
            c = self.membership.client
            return c.nombre, c.cedula, c.codigo_afiliado
        raise ValueError("La factura no tiene datos del receptor.")

    def clean(self):
        if self.pk:
            original = Invoice.objects.get(pk=self.pk)
            if original.esta_impresa:
                raise ValidationError("No se puede editar una factura que ya ha sido impresa.")

    def __str__(self):
        return f"Factura {self.nro_control} - {self.receptor_nombre}"

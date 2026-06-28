from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from datetime import timedelta
from django.utils import timezone
from apps.clients.models import Client
from apps.clients.fields import SQLiteJSONField


class Plan(models.Model):
    class BillingType(models.TextChoices):
        FIXED = 'FIXED', 'Fijo'
        FLEXIBLE = 'FLEXIBLE', 'Flexible'

    nombre = models.CharField("Nombre del Plan", max_length=50)
    billing_type = models.CharField(
        "Tipo de facturación",
        max_length=10,
        choices=BillingType.choices,
        default=BillingType.FIXED,
    )
    dias_duracion = models.PositiveIntegerField(
        "Días de Duración",
        null=True,
        blank=True,
    )
    precio_usd = models.DecimalField("Precio (USD)", max_digits=12, decimal_places=2)
    hora_inicio = models.TimeField(
        "Hora de Inicio",
        null=True,
        blank=True,
        help_text="Dejar en blanco para acceso todo el día",
    )
    hora_fin = models.TimeField(
        "Hora de Fin",
        null=True,
        blank=True,
        help_text="Dejar en blanco para acceso todo el día",
    )
    is_active = models.BooleanField(
        "Activo",
        default=True,
        help_text="Si se desactiva, no podrá ser comprado pero mantendrá el historial",
    )

    class Meta:
        verbose_name = "Plan"
        verbose_name_plural = "Planes"

    def clean(self):
        if self.billing_type == self.BillingType.FLEXIBLE:
            if not self.dias_duracion or self.dias_duracion < 1:
                raise ValidationError(
                    {"dias_duracion": "Los planes flexibles requieren al menos 1 día de duración."}
                )
        elif self.dias_duracion is not None and self.dias_duracion < 1:
            raise ValidationError(
                {"dias_duracion": "La duración en días debe ser mayor a 0 si se especifica."}
            )

    def save(self, *args, **kwargs):
        if self.billing_type == self.BillingType.FIXED:
            self.dias_duracion = None
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def is_fixed(self):
        return self.billing_type == self.BillingType.FIXED

    @property
    def is_flexible(self):
        return self.billing_type == self.BillingType.FLEXIBLE

    @property
    def duracion_display(self):
        if self.is_fixed:
            return "Mensual"
        return f"{self.dias_duracion} días"

    def __str__(self):
        if self.is_fixed:
            return f"{self.nombre} (Fijo) - ${self.precio_usd}"
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


class BillingSettings(models.Model):
    multa_monto_usd = models.DecimalField(
        "Multa por morosidad (USD)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    fixed_grace_days = models.PositiveSmallIntegerField(
        "Días de gracia (plan fijo)",
        default=0,
        help_text="Días de acceso biométrico tras vencer el último periodo fijo pagado.",
    )
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Configuración de facturación"
        verbose_name_plural = "Configuración de facturación"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("No se puede eliminar la configuración global de facturación.")

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(
            pk=1,
            defaults={
                "multa_monto_usd": Decimal("0.00"),
                "fixed_grace_days": 0,
            },
        )
        return obj

    def __str__(self):
        return "Multa ${} USD · Gracia {} días".format(
            self.multa_monto_usd,
            self.fixed_grace_days,
        )


class ReportEmailSettings(models.Model):
    recipient_email = models.EmailField(
        "Correo del destinatario",
        blank=True,
        default="",
    )
    daily_send_limit = models.PositiveSmallIntegerField(
        "Límite de envíos por día",
        default=3,
    )
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Configuración de reportes por correo"
        verbose_name_plural = "Configuración de reportes por correo"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("No se puede eliminar la configuración de reportes.")

    @classmethod
    def get_settings(cls):
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"daily_send_limit": 3})
        return obj

    def __str__(self):
        if self.recipient_email:
            return f"Reportes → {self.recipient_email}"
        return "Reportes (sin correo destino)"


class ReportSendLog(models.Model):
    sent_at = models.DateTimeField("Enviado", auto_now_add=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="report_send_logs",
        verbose_name="Usuario",
    )
    period_days = models.PositiveSmallIntegerField("Días del período")
    recipient_email = models.EmailField("Destinatario")
    success = models.BooleanField("Éxito", default=False)
    error_message = models.TextField("Error", blank=True)

    class Meta:
        verbose_name = "Envío de reporte"
        verbose_name_plural = "Envíos de reportes"
        ordering = ["-sent_at"]

    def __str__(self):
        status = "OK" if self.success else "Error"
        return f"Reporte {self.period_days}d → {self.recipient_email} ({status})"


class SaleItem(models.Model):
    class ItemType(models.TextChoices):
        SERVICE = "SERVICE", "Servicio"
        PRODUCT = "PRODUCT", "Producto"

    class SystemCode(models.TextChoices):
        LOCKER_RENTAL = "LOCKER_RENTAL", "Alquiler de casillero"

    name = models.CharField("Nombre", max_length=100)
    description = models.TextField("Descripción", blank=True)
    item_type = models.CharField(
        "Tipo",
        max_length=10,
        choices=ItemType.choices,
        default=ItemType.SERVICE,
    )
    price_usd = models.DecimalField("Precio (USD)", max_digits=12, decimal_places=2)
    requires_locker_assignment = models.BooleanField("Requiere asignación de casillero", default=False)
    default_rental_days = models.PositiveSmallIntegerField("Días de alquiler por defecto", default=30)
    system_code = models.CharField(
        "Código de sistema",
        max_length=32,
        choices=SystemCode.choices,
        null=True,
        blank=True,
        unique=True,
    )
    is_active = models.BooleanField("Activo", default=True)
    sort_order = models.PositiveIntegerField("Orden", default=0)

    class Meta:
        verbose_name = "Producto o servicio"
        verbose_name_plural = "Productos y servicios"
        ordering = ["name", "id"]

    @property
    def is_system_managed(self):
        return bool(self.system_code)

    @property
    def is_plan_linked_service(self):
        return self.item_type == self.ItemType.SERVICE

    @classmethod
    def get_locker_rental_item(cls):
        return cls.objects.filter(
            system_code=cls.SystemCode.LOCKER_RENTAL,
            is_active=True,
        ).first()

    def __str__(self):
        return f"{self.name} (${self.price_usd})"


class ClientBillingEvent(models.Model):
    class EventType(models.TextChoices):
        CUT_DATE_CHANGED = "CUT_DATE_CHANGED", "Cambio de fecha de corte"
        SUBSCRIPTION_REACTIVATED = "SUBSCRIPTION_REACTIVATED", "Reactivación de suscripción"
        LATE_FEE_APPLIED = "LATE_FEE_APPLIED", "Multa aplicada"
        LATE_FEE_WAIVED = "LATE_FEE_WAIVED", "Multa omitida"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="billing_events",
        verbose_name="Afiliado",
    )
    event_type = models.CharField("Tipo", max_length=32, choices=EventType.choices)
    payload = SQLiteJSONField("Datos", default=dict, blank=True)
    motivo = models.TextField("Motivo", blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Registrado por",
    )
    created_at = models.DateTimeField("Fecha", auto_now_add=True)

    class Meta:
        verbose_name = "Evento de facturación"
        verbose_name_plural = "Eventos de facturación"
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.client.codigo_afiliado} — {self.get_event_type_display()}"


class Membership(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='memberships', verbose_name="Afiliado")
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, verbose_name="Plan")
    fecha_inicio = models.DateField("Fecha de Inicio", default=timezone.now)
    fecha_fin = models.DateField("Fecha de Vencimiento", editable=False)

    class Meta:
        verbose_name = "Membresía"
        verbose_name_plural = "Membresías"

    def clean(self):
        if self.fecha_inicio and self.fecha_fin and self.fecha_inicio > self.fecha_fin:
            raise ValidationError("La fecha de inicio debe ser anterior o igual a la de vencimiento.")

    def save(self, *args, **kwargs):
        if not self.fecha_fin:
            if self.plan.is_flexible:
                if not self.plan.dias_duracion:
                    raise ValidationError("El plan flexible no tiene días de duración configurados.")
                self.fecha_fin = self.fecha_inicio + timedelta(days=self.plan.dias_duracion)
            else:
                raise ValidationError("La membresía fija requiere fecha de vencimiento explícita.")

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


class ClientServicePeriod(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Activo"
        QUEUED = "QUEUED", "Por iniciar"
        EXPIRED = "EXPIRED", "Vencido"
        CANCELLED = "CANCELLED", "Cancelado"

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name="service_periods",
        verbose_name="Afiliado",
    )
    sale_item = models.ForeignKey(
        SaleItem,
        on_delete=models.PROTECT,
        related_name="service_periods",
        verbose_name="Servicio",
    )
    membership = models.ForeignKey(
        Membership,
        on_delete=models.PROTECT,
        related_name="service_periods",
        verbose_name="Membresía",
    )
    invoice_line = models.ForeignKey(
        "InvoiceLine",
        on_delete=models.SET_NULL,
        related_name="service_periods",
        verbose_name="Línea de factura",
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
        related_name="created_service_periods",
        verbose_name="Registrado por",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField("Creado", auto_now_add=True)
    updated_at = models.DateTimeField("Actualizado", auto_now=True)

    class Meta:
        verbose_name = "Periodo de servicio"
        verbose_name_plural = "Periodos de servicio"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["client", "sale_item"],
                condition=Q(status="ACTIVE"),
                name="unique_active_service_period_per_client_item",
            ),
        ]

    @property
    def is_current(self):
        return self.status == self.Status.ACTIVE and self.end_date >= timezone.localdate()

    def __str__(self):
        return "{} — {} ({} al {})".format(
            self.client.nombre,
            self.sale_item.name,
            self.start_date,
            self.end_date,
        )


class Invoice(models.Model):
    class PaymentMethod(models.TextChoices):
        CASH_VES = "CASH_VES", "Efectivo Bs"
        CASH_USD = "CASH_USD", "Efectivo $"
        DEBIT = "DEBIT", "Débito"
        MOBILE = "MOBILE", "Pago móvil"
        MIXED = "MIXED", "Mixto"

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
    multa_usd = models.DecimalField(
        "Multa (USD)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    multa_ves = models.DecimalField(
        "Multa (VES)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    monto_total = models.DecimalField("Monto Total (VES)", max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        "Forma de pago",
        max_length=16,
        choices=PaymentMethod.choices,
        null=True,
        blank=True,
    )
    payment_splits = SQLiteJSONField(
        "Desglose de pago mixto",
        default=list,
        blank=True,
    )
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

    def has_detail_lines(self):
        return self.lines.exists()

    @property
    def concept_display(self):
        """Etiqueta para listados: plan, productos, combinado o —."""
        plan_name = (self.plan_snapshot or "").strip()
        if not plan_name and self.membership_id:
            try:
                plan_name = self.membership.plan.nombre
            except Exception:
                plan_name = ""

        if self.has_detail_lines():
            kinds = set(self.lines.values_list("line_kind", flat=True))
            has_mem = InvoiceLine.LineKind.MEMBERSHIP in kinds
            has_prod = InvoiceLine.LineKind.PRODUCT in kinds
            if has_prod and not has_mem:
                return "Productos y servicios"
            if has_mem and has_prod:
                return "{} + productos".format(plan_name) if plan_name else "Membresía + productos"
            if has_mem:
                return plan_name or "Membresía"
            if has_prod:
                return "Productos y servicios"

        if plan_name:
            return plan_name
        if self.membership_id and not plan_name:
            return "Membresía"
        if not self.plan_snapshot and not self.membership_id:
            return "Productos y servicios"
        return "—"

    @property
    def payment_method_display(self):
        if not self.payment_method:
            return "No registrado"
        return self.get_payment_method_display()

    def get_payment_split_display_items(self):
        if self.payment_method != self.PaymentMethod.MIXED:
            return []
        labels = dict(self.PaymentMethod.choices)
        items = []
        for entry in self.payment_splits or []:
            method = entry.get("method", "")
            label = labels.get(method, method)
            amount_ves = entry.get("amount_ves")
            if method == self.PaymentMethod.CASH_USD and entry.get("amount_usd"):
                display = "$ {} (Bs {})".format(entry.get("amount_usd"), amount_ves)
            else:
                display = "Bs {}".format(amount_ves)
            items.append(
                {
                    "label": label,
                    "amount_ves": amount_ves,
                    "display": display,
                }
            )
        return items

    @property
    def monto_cuota_ves(self):
        if self.has_detail_lines():
            from django.db.models import Sum

            total = self.lines.filter(
                line_kind=InvoiceLine.LineKind.MEMBERSHIP
            ).aggregate(s=Sum("amount_ves"))["s"]
            return total or Decimal("0.00")
        return self.monto_total - self.multa_ves

    def __str__(self):
        return f"Factura {self.nro_control} - {self.receptor_nombre}"


class InvoiceLine(models.Model):
    class LineKind(models.TextChoices):
        MEMBERSHIP = "MEMBERSHIP", "Membresía"
        PRODUCT = "PRODUCT", "Producto o servicio"
        LATE_FEE = "LATE_FEE", "Multa"

    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.CASCADE,
        related_name="lines",
        verbose_name="Factura",
    )
    line_kind = models.CharField("Tipo de línea", max_length=16, choices=LineKind.choices)
    description = models.CharField("Descripción", max_length=255)
    quantity = models.PositiveIntegerField("Cantidad", default=1)
    unit_price_usd = models.DecimalField(
        "Precio unitario (USD)",
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )
    amount_ves = models.DecimalField("Monto (VES)", max_digits=12, decimal_places=2)
    sale_item = models.ForeignKey(
        SaleItem,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
        verbose_name="Ítem de catálogo",
    )
    membership = models.ForeignKey(
        Membership,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoice_lines",
        verbose_name="Membresía",
    )
    metadata = SQLiteJSONField("Metadatos", default=dict, blank=True)

    class Meta:
        verbose_name = "Línea de factura"
        verbose_name_plural = "Líneas de factura"
        ordering = ["id"]

    def __str__(self):
        return f"{self.description} — Bs {self.amount_ves}"

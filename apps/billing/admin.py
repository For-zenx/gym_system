from django.contrib import admin
from .models import (
    Plan,
    SaleItem,
    Membership,
    Invoice,
    InvoiceLine,
    ExchangeRate,
    BillingSettings,
    ClientBillingEvent,
    ClientServicePeriod,
)


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ("name", "item_type", "price_usd", "is_active")
    list_filter = ("item_type", "is_active")


@admin.register(ClientServicePeriod)
class ClientServicePeriodAdmin(admin.ModelAdmin):
    list_display = ("client", "sale_item", "start_date", "end_date", "status")
    list_filter = ("status",)
    raw_id_fields = ("client", "sale_item", "membership", "invoice_line")


@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'billing_type', 'dias_duracion', 'precio_usd')


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'tasa_ves')
    list_filter = ('fecha',)


@admin.register(BillingSettings)
class BillingSettingsAdmin(admin.ModelAdmin):
    list_display = ('multa_monto_usd', 'fixed_grace_days', 'updated_at')

    def has_add_permission(self, request):
        return not BillingSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ClientBillingEvent)
class ClientBillingEventAdmin(admin.ModelAdmin):
    list_display = ('client', 'event_type', 'created_at', 'created_by', 'motivo')
    list_filter = ('event_type', 'created_at')
    search_fields = ('client__nombre', 'client__cedula', 'client__codigo_afiliado', 'motivo')
    readonly_fields = ('client', 'event_type', 'payload', 'motivo', 'created_by', 'created_at')


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ('client', 'plan', 'fecha_inicio', 'fecha_fin', 'es_valida_status')
    list_filter = ('plan', 'fecha_fin')
    search_fields = ('client__nombre', 'client__cedula')

    def es_valida_status(self, obj):
        return obj.es_valida
    es_valida_status.boolean = True
    es_valida_status.short_description = "Vigente"


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = (
        'nro_control',
        'receptor_nombre',
        'client',
        'plan_snapshot',
        'multa_ves',
        'monto_total',
        'esta_impresa',
        'fecha_emision',
    )
    list_filter = ('esta_impresa', 'fecha_emision')
    search_fields = (
        'nro_control',
        'client__nombre',
        'client__cedula',
        'client__codigo_afiliado',
        'client_nombre_snapshot',
        'client_cedula_snapshot',
        'client_codigo_snapshot',
    )
    readonly_fields = (
        'fecha_emision',
        'client_nombre_snapshot',
        'client_cedula_snapshot',
        'client_codigo_snapshot',
        'plan_snapshot',
    )

from django.contrib import admin
from .models import Plan, Membership, Invoice, ExchangeRate

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'dias_duracion', 'precio_usd')

@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'tasa_ves')
    list_filter = ('fecha',)

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
    list_display = ('nro_control', 'receptor_nombre', 'client', 'plan_snapshot', 'monto_total', 'esta_impresa', 'fecha_emision')
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

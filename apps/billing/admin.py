from django.contrib import admin
from .models import Plan, Membership, Invoice

@admin.register(Plan)
class PlanAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'dias_duracion', 'precio')

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
    list_display = ('nro_control', 'membership', 'monto_total', 'fecha_emision')
    search_fields = ('nro_control', 'membership__client__nombre')
    readonly_fields = ('fecha_emision',)

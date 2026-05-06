from django.contrib import admin
from .models import Plan, Membership

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

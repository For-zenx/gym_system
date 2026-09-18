from django.contrib import admin
from .models import Client, ClientAdaptiveEmbedding, GuestPass


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cedula', 'codigo_afiliado', 'person_category', 'fecha_corte_dia', 'fixed_plan', 'fecha_nacimiento', 'sexo', 'fecha_ingreso')
    search_fields = ('nombre', 'cedula', 'codigo_afiliado')
    list_filter = ('person_category', 'fecha_ingreso', 'sexo')


@admin.register(GuestPass)
class GuestPassAdmin(admin.ModelAdmin):
    list_display = ('guest', 'sponsor', 'valid_from', 'valid_until', 'revoked_at', 'created_at')
    search_fields = ('guest__nombre', 'sponsor__nombre', 'guest__codigo_afiliado')
    list_filter = ('valid_from', 'valid_until')


@admin.register(ClientAdaptiveEmbedding)
class ClientAdaptiveEmbeddingAdmin(admin.ModelAdmin):
    list_display = ('client', 'best_distance', 'margin', 'created_at')
    search_fields = ('client__nombre', 'client__codigo_afiliado')
    list_filter = ('created_at',)
    readonly_fields = ('client', 'embedding', 'margin', 'best_distance', 'created_at')

    def has_add_permission(self, request):
        return False

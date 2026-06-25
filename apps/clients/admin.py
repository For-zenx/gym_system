from django.contrib import admin
from .models import Client, GuestPass


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cedula', 'codigo_afiliado', 'person_category', 'fecha_corte_dia', 'fecha_nacimiento', 'sexo', 'fecha_ingreso')
    search_fields = ('nombre', 'cedula', 'codigo_afiliado')
    list_filter = ('person_category', 'fecha_ingreso', 'sexo')


@admin.register(GuestPass)
class GuestPassAdmin(admin.ModelAdmin):
    list_display = ('guest', 'sponsor', 'valid_from', 'valid_until', 'revoked_at', 'created_at')
    search_fields = ('guest__nombre', 'sponsor__nombre', 'guest__codigo_afiliado')
    list_filter = ('valid_from', 'valid_until')

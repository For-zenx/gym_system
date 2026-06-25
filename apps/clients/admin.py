from django.contrib import admin
from .models import Client

@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'cedula', 'codigo_afiliado', 'person_category', 'fecha_corte_dia', 'fecha_nacimiento', 'sexo', 'fecha_ingreso')
    search_fields = ('nombre', 'cedula', 'codigo_afiliado')
    list_filter = ('person_category', 'fecha_ingreso', 'sexo')

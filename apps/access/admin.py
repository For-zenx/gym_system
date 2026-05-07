from django.contrib import admin
from .models import AccessLog

@admin.register(AccessLog)
class AccessLogAdmin(admin.ModelAdmin):
    list_display = ('client', 'timestamp', 'resultado', 'motivo')
    list_filter = ('resultado', 'timestamp')
    search_fields = ('client__nombre', 'client__cedula')
    readonly_fields = ('timestamp',)

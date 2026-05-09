from django.contrib import admin
from .models import PrinterConfig

@admin.register(PrinterConfig)
class PrinterConfigAdmin(admin.ModelAdmin):
    list_display = ('port', 'baudrate', 'is_active')

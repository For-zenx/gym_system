from django.contrib import admin
from .models import PrinterConfig

@admin.register(PrinterConfig)
class PrinterConfigAdmin(admin.ModelAdmin):
    list_display = ("printer_type", "port", "baudrate", "is_active", "updated_at")

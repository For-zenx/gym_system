from django.contrib import admin

from .models import Locker, LockerRental


@admin.register(Locker)
class LockerAdmin(admin.ModelAdmin):
    list_display = ("number", "status", "updated_at")
    list_filter = ("status",)
    search_fields = ("number", "notes")


@admin.register(LockerRental)
class LockerRentalAdmin(admin.ModelAdmin):
    list_display = ("locker", "client", "status", "start_date", "end_date")
    list_filter = ("status", "start_date", "end_date")
    search_fields = ("locker__number", "client__nombre", "client__cedula", "client__codigo_afiliado")
    raw_id_fields = ("client", "locker", "sale_item", "invoice_line", "created_by", "released_by")

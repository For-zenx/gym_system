from django.contrib import admin

from .models import ClassRegistration, ClassSession


class ClassRegistrationInline(admin.TabularInline):
    model = ClassRegistration
    extra = 0
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("client", "invoice_line", "created_by")


@admin.register(ClassSession)
class ClassSessionAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "session_date",
        "start_time",
        "instructor_display",
        "price_usd",
        "status",
        "attendance_reported",
    )
    list_filter = ("status", "session_date")
    search_fields = ("title", "instructor_name", "instructor__nombre")
    raw_id_fields = ("instructor", "created_by")
    inlines = [ClassRegistrationInline]


@admin.register(ClassRegistration)
class ClassRegistrationAdmin(admin.ModelAdmin):
    list_display = ("session", "client", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("client__nombre", "client__codigo_afiliado", "session__title")
    raw_id_fields = ("session", "client", "invoice_line", "created_by")

from django.contrib import admin

from .models import StaffProfile, StaffRole


@admin.register(StaffRole)
class StaffRoleAdmin(admin.ModelAdmin):
    list_display = ("name", "is_system", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "display_name", "created_from_role", "updated_at")
    search_fields = ("user__username", "display_name")
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("user", "created_from_role")

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.clients.fields import SQLiteJSONField

from .permissions import validate_permissions


def default_permissions_list():
    return []


class StaffRole(models.Model):
    """Plantilla reutilizable de permisos; no gobierna cuentas en runtime."""

    name = models.CharField(max_length=100, unique=True, verbose_name="Nombre")
    description = models.TextField(blank=True, verbose_name="Descripción")
    permissions = SQLiteJSONField(default=default_permissions_list, verbose_name="Permisos")
    is_system = models.BooleanField(default=False, verbose_name="Plantilla del sistema")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Plantilla de permisos"
        verbose_name_plural = "Plantillas de permisos"
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        self.permissions = validate_permissions(self.permissions or [])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if self.is_system:
            raise ValidationError("No se puede eliminar una plantilla del sistema.")
        super().delete(*args, **kwargs)


class StaffProfile(models.Model):
    """Permisos efectivos de cada cuenta operativa del gimnasio."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="staff_profile",
        verbose_name="Usuario",
    )
    display_name = models.CharField(max_length=150, verbose_name="Nombre visible")
    permissions = SQLiteJSONField(default=default_permissions_list, verbose_name="Permisos")
    created_from_role = models.ForeignKey(
        StaffRole,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derived_profiles",
        verbose_name="Plantilla de origen",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil operativo"
        verbose_name_plural = "Perfiles operativos"

    def __str__(self):
        return self.display_name or self.user.username

    def clean(self):
        super().clean()
        self.permissions = validate_permissions(self.permissions or [])

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

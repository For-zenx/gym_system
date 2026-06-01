import apps.clients.fields
import apps.users.models
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_roles_and_profiles(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")
    User = apps.get_model("auth", "User")

    from apps.users.permissions import (
        ADMINISTRATOR_PERMISSION_CODES,
        CASHIER_PERMISSION_CODES,
    )

    admin_role, _ = StaffRole.objects.get_or_create(
        name="Administrador",
        defaults={
            "description": "Acceso total al sistema operativo y configuración.",
            "permissions": ADMINISTRATOR_PERMISSION_CODES,
            "is_system": True,
        },
    )
    if admin_role.permissions != ADMINISTRATOR_PERMISSION_CODES:
        admin_role.permissions = ADMINISTRATOR_PERMISSION_CODES
        admin_role.is_system = True
        admin_role.save(update_fields=["permissions", "is_system"])

    cashier_role, _ = StaffRole.objects.get_or_create(
        name="Cajera",
        defaults={
            "description": "Operación diaria de caja, afiliados y consultas.",
            "permissions": CASHIER_PERMISSION_CODES,
            "is_system": True,
        },
    )
    if cashier_role.permissions != CASHIER_PERMISSION_CODES:
        cashier_role.permissions = CASHIER_PERMISSION_CODES
        cashier_role.is_system = True
        cashier_role.save(update_fields=["permissions", "is_system"])

    for user in User.objects.all():
        if StaffProfile.objects.filter(user_id=user.pk).exists():
            continue
        if user.is_superuser:
            permissions = ADMINISTRATOR_PERMISSION_CODES
            origin_role = admin_role
        else:
            permissions = CASHIER_PERMISSION_CODES
            origin_role = cashier_role
        display_name = user.username
        if getattr(user, "first_name", None):
            full = "%s %s" % (user.first_name, getattr(user, "last_name", "") or "")
            full = full.strip()
            if full:
                display_name = full
        StaffProfile.objects.create(
            user_id=user.pk,
            display_name=display_name,
            permissions=permissions,
            created_from_role_id=origin_role.pk,
        )


def unseed_roles_and_profiles(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")
    StaffProfile.objects.all().delete()
    StaffRole.objects.filter(is_system=True).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=100, unique=True, verbose_name="Nombre")),
                ("description", models.TextField(blank=True, verbose_name="Descripción")),
                ("permissions", apps.clients.fields.SQLiteJSONField(default=apps.users.models.default_permissions_list, verbose_name="Permisos")),
                ("is_system", models.BooleanField(default=False, verbose_name="Plantilla del sistema")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Plantilla de permisos",
                "verbose_name_plural": "Plantillas de permisos",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="StaffProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("display_name", models.CharField(max_length=150, verbose_name="Nombre visible")),
                ("permissions", apps.clients.fields.SQLiteJSONField(default=apps.users.models.default_permissions_list, verbose_name="Permisos")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_from_role",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="derived_profiles",
                        to="users.staffrole",
                        verbose_name="Plantilla de origen",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_profile",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="Usuario",
                    ),
                ),
            ],
            options={
                "verbose_name": "Perfil operativo",
                "verbose_name_plural": "Perfiles operativos",
            },
        ),
        migrations.RunPython(seed_roles_and_profiles, unseed_roles_and_profiles),
    ]

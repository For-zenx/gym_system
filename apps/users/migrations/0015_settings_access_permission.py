from django.db import migrations

SETTINGS_ACCESS = "settings.access"


def add_access_settings_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")

    for role in StaffRole.objects.filter(name="Administrador"):
        perms = list(role.permissions or [])
        if SETTINGS_ACCESS not in perms:
            perms.append(SETTINGS_ACCESS)
            role.permissions = perms
            role.save(update_fields=["permissions"])


def remove_access_settings_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p != SETTINGS_ACCESS]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0014_classes_permissions"),
    ]

    operations = [
        migrations.RunPython(add_access_settings_permission, remove_access_settings_permission),
    ]

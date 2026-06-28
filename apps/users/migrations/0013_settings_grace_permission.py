from django.db import migrations

SETTINGS_GRACE = "settings.grace"


def add_grace_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")

    for role in StaffRole.objects.filter(name="Administrador"):
        perms = list(role.permissions or [])
        if SETTINGS_GRACE not in perms:
            perms.append(SETTINGS_GRACE)
            role.permissions = perms
            role.save(update_fields=["permissions"])


def remove_grace_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p != SETTINGS_GRACE]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0012_guests_permissions"),
    ]

    operations = [
        migrations.RunPython(add_grace_permission, remove_grace_permission),
    ]

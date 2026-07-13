from django.db import migrations

SETTINGS_PRINTERS = "settings.printers"


def add_printers_settings_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.filter(name="Administrador"):
        perms = list(role.permissions or [])
        if SETTINGS_PRINTERS not in perms:
            perms.append(SETTINGS_PRINTERS)
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.all():
        perms = list(profile.permissions or [])
        if SETTINGS_PRINTERS in perms:
            continue
        if "roles.manage" in perms and "users.view" in perms:
            perms.append(SETTINGS_PRINTERS)
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


def remove_printers_settings_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p != SETTINGS_PRINTERS]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.all():
        perms = [p for p in (profile.permissions or []) if p != SETTINGS_PRINTERS]
        if perms != (profile.permissions or []):
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0015_settings_access_permission"),
    ]

    operations = [
        migrations.RunPython(
            add_printers_settings_permission,
            remove_printers_settings_permission,
        ),
    ]

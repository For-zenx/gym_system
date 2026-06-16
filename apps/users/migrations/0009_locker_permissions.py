from django.db import migrations

LOCKERS_VIEW = "lockers.view"
LOCKERS_MANAGE = "lockers.manage"


def add_locker_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        perms = list(role.permissions or [])
        changed = False
        if role.name in {"Administrador", "Encargado en caja"} and LOCKERS_VIEW not in perms:
            perms.append(LOCKERS_VIEW)
            changed = True
        if role.name == "Administrador" and LOCKERS_MANAGE not in perms:
            perms.append(LOCKERS_MANAGE)
            changed = True
        if changed:
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.select_related("user").all():
        perms = list(profile.permissions or [])
        changed = False
        if "roles.manage" in perms and "users.view" in perms:
            if LOCKERS_VIEW not in perms:
                perms.append(LOCKERS_VIEW)
                changed = True
            if LOCKERS_MANAGE not in perms:
                perms.append(LOCKERS_MANAGE)
                changed = True
        elif "billing.charge" in perms and "products.view" in perms and LOCKERS_VIEW not in perms:
            perms.append(LOCKERS_VIEW)
            changed = True
        if changed:
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


def remove_locker_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")
    locker_permissions = {LOCKERS_VIEW, LOCKERS_MANAGE}

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p not in locker_permissions]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.all():
        perms = [p for p in (profile.permissions or []) if p not in locker_permissions]
        if perms != (profile.permissions or []):
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0008_open_turnstile_permission"),
    ]

    operations = [
        migrations.RunPython(add_locker_permissions, remove_locker_permissions),
    ]

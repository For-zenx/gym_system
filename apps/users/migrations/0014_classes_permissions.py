from django.db import migrations

CLASSES_VIEW = "classes.view"
CLASSES_MANAGE = "classes.manage"
CLASSES_REGISTER = "classes.register"


def add_classes_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        perms = list(role.permissions or [])
        changed = False
        if role.name in {"Administrador", "Encargado en caja"} and CLASSES_VIEW not in perms:
            perms.append(CLASSES_VIEW)
            changed = True
        if role.name in {"Administrador", "Encargado en caja"} and CLASSES_REGISTER not in perms:
            perms.append(CLASSES_REGISTER)
            changed = True
        if role.name == "Administrador" and CLASSES_MANAGE not in perms:
            perms.append(CLASSES_MANAGE)
            changed = True
        if changed:
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.select_related("user").all():
        perms = list(profile.permissions or [])
        changed = False
        if "roles.manage" in perms and "users.view" in perms:
            for code in (CLASSES_VIEW, CLASSES_REGISTER, CLASSES_MANAGE):
                if code not in perms:
                    perms.append(code)
                    changed = True
        elif "billing.charge" in perms and "products.view" in perms:
            for code in (CLASSES_VIEW, CLASSES_REGISTER):
                if code not in perms:
                    perms.append(code)
                    changed = True
        if changed:
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


def remove_classes_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")
    class_permissions = {CLASSES_VIEW, CLASSES_MANAGE, CLASSES_REGISTER}

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p not in class_permissions]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.all():
        perms = [p for p in (profile.permissions or []) if p not in class_permissions]
        if perms != (profile.permissions or []):
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0013_settings_grace_permission"),
    ]

    operations = [
        migrations.RunPython(add_classes_permissions, remove_classes_permissions),
    ]

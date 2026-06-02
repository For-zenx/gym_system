from django.db import migrations


def add_products_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        perms = list(role.permissions or [])
        changed = False
        if role.name == "Administrador":
            for code in ("products.view", "products.manage"):
                if code not in perms:
                    perms.append(code)
                    changed = True
        elif role.name == "Cajera":
            if "products.view" not in perms:
                perms.append("products.view")
                changed = True
        if changed:
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.select_related("user").all():
        user = profile.user
        if not user or not user.is_staff:
            continue
        perms = list(profile.permissions or [])
        changed = False
        if "roles.manage" in perms or "users.view" in perms:
            for code in ("products.view", "products.manage"):
                if code not in perms:
                    perms.append(code)
                    changed = True
        elif "billing.charge" in perms and "products.view" not in perms:
            perms.append("products.view")
            changed = True
        if changed:
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


def remove_products_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")
    codes = frozenset(("products.view", "products.manage"))

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p not in codes]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.all():
        perms = [p for p in (profile.permissions or []) if p not in codes]
        if perms != (profile.permissions or []):
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0001_staff_rbac"),
    ]

    operations = [
        migrations.RunPython(add_products_permissions, remove_products_permissions),
    ]

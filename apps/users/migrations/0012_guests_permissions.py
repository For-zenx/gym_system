from django.db import migrations

GUESTS_PERMS = (
    "guests.view_list",
    "guests.view_profile",
    "guests.register",
    "guests.revoke_pass",
)

GUESTS_ADMIN_EXTRA = GUESTS_PERMS + ("guests.delete",)


def add_guests_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")

    for role in StaffRole.objects.all():
        perms = list(role.permissions or [])
        changed = False
        if role.name == "Administrador":
            for code in GUESTS_ADMIN_EXTRA:
                if code not in perms:
                    perms.append(code)
                    changed = True
        elif role.name in ("Encargado en caja", "Cajera"):
            for code in GUESTS_PERMS:
                if code not in perms:
                    perms.append(code)
                    changed = True
        if changed:
            role.permissions = perms
            role.save(update_fields=["permissions"])


def remove_guests_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    codes = set(GUESTS_ADMIN_EXTRA)

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p not in codes]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0011_staff_persons_permissions"),
    ]

    operations = [
        migrations.RunPython(add_guests_permissions, remove_guests_permissions),
    ]

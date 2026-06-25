from django.db import migrations

STAFF_PERSONS_PERMS = (
    "staff_persons.view_list",
    "staff_persons.view_profile",
    "staff_persons.edit",
    "staff_persons.enroll",
)

STAFF_PERSONS_ADMIN_EXTRA = STAFF_PERSONS_PERMS + ("staff_persons.delete",)


def add_staff_persons_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")

    for role in StaffRole.objects.all():
        perms = list(role.permissions or [])
        changed = False
        if role.name == "Administrador":
            for code in STAFF_PERSONS_ADMIN_EXTRA:
                if code not in perms:
                    perms.append(code)
                    changed = True
        elif role.name in ("Encargado en caja", "Cajera"):
            for code in STAFF_PERSONS_PERMS:
                if code not in perms:
                    perms.append(code)
                    changed = True
        if changed:
            role.permissions = perms
            role.save(update_fields=["permissions"])


def remove_staff_persons_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    codes = set(STAFF_PERSONS_ADMIN_EXTRA)

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p not in codes]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0010_stats_permission"),
    ]

    operations = [
        migrations.RunPython(add_staff_persons_permissions, remove_staff_persons_permissions),
    ]

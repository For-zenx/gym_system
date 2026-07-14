from django.db import migrations

PRINT_X = "reports.print_x"
PRINT_Z = "reports.print_z"

CASHIER_ROLE_NAMES = ("Encargado en caja", "Cajera")


def add_fiscal_report_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        perms = list(role.permissions or [])
        changed = False
        if role.name == "Administrador":
            for code in (PRINT_X, PRINT_Z):
                if code not in perms:
                    perms.append(code)
                    changed = True
        elif role.name in CASHIER_ROLE_NAMES:
            if PRINT_X not in perms:
                perms.append(PRINT_X)
                changed = True
        if changed:
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.all():
        perms = list(profile.permissions or [])
        changed = False
        is_admin_capable = "roles.manage" in perms and "users.view" in perms
        if is_admin_capable:
            for code in (PRINT_X, PRINT_Z):
                if code not in perms:
                    perms.append(code)
                    changed = True
        elif "billing.print_invoice" in perms or "reports.send" in perms:
            if PRINT_X not in perms:
                perms.append(PRINT_X)
                changed = True
        if changed:
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


def remove_fiscal_report_permissions(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")
    codes = {PRINT_X, PRINT_Z}

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
        ("users", "0016_printers_settings_permission"),
    ]

    operations = [
        migrations.RunPython(
            add_fiscal_report_permissions,
            remove_fiscal_report_permissions,
        ),
    ]

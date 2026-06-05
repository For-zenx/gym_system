from django.db import migrations

EDIT_INVOICE = "billing.edit_invoice"


def add_edit_invoice_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")

    for role in StaffRole.objects.all():
        if role.name != "Administrador":
            continue
        perms = list(role.permissions or [])
        if EDIT_INVOICE not in perms:
            perms.append(EDIT_INVOICE)
            role.permissions = perms
            role.save(update_fields=["permissions"])


def remove_edit_invoice_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p != EDIT_INVOICE]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0005_reports_permissions"),
    ]

    operations = [
        migrations.RunPython(add_edit_invoice_permission, remove_edit_invoice_permission),
    ]

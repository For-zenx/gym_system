from django.db import migrations

EDIT_INVOICE = "billing.edit_invoice"


def add_edit_invoice_to_admin_profiles(apps, schema_editor):
    StaffProfile = apps.get_model("users", "StaffProfile")

    for profile in StaffProfile.objects.select_related("user").all():
        user = profile.user
        if not user:
            continue
        perms = list(profile.permissions or [])
        if EDIT_INVOICE in perms:
            continue
        if "roles.manage" in perms and "users.view" in perms:
            perms.append(EDIT_INVOICE)
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


def remove_edit_invoice_from_admin_profiles(apps, schema_editor):
    StaffProfile = apps.get_model("users", "StaffProfile")

    for profile in StaffProfile.objects.all():
        perms = [p for p in (profile.permissions or []) if p != EDIT_INVOICE]
        if perms != (profile.permissions or []):
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0006_edit_invoice_permission"),
    ]

    operations = [
        migrations.RunPython(
            add_edit_invoice_to_admin_profiles,
            remove_edit_invoice_from_admin_profiles,
        ),
    ]

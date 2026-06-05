from django.db import migrations

VIEW_PHONE_CODE = "clients.view_phone"


def add_view_phone_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        if role.name != "Administrador":
            continue
        perms = list(role.permissions or [])
        if VIEW_PHONE_CODE not in perms:
            perms.append(VIEW_PHONE_CODE)
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.select_related("user").all():
        user = profile.user
        if not user:
            continue
        perms = list(profile.permissions or [])
        if VIEW_PHONE_CODE in perms:
            continue
        if "roles.manage" in perms and "users.view" in perms:
            perms.append(VIEW_PHONE_CODE)
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


def remove_view_phone_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p != VIEW_PHONE_CODE]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.all():
        perms = [p for p in (profile.permissions or []) if p != VIEW_PHONE_CODE]
        if perms != (profile.permissions or []):
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_rename_cashier_role"),
    ]

    operations = [
        migrations.RunPython(add_view_phone_permission, remove_view_phone_permission),
    ]

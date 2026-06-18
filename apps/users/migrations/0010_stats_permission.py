from django.db import migrations

STATS_VIEW = "stats.view"


def add_stats_view_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        if role.name != "Administrador":
            continue
        perms = list(role.permissions or [])
        if STATS_VIEW not in perms:
            perms.append(STATS_VIEW)
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.select_related("user").all():
        user = profile.user
        if not user:
            continue
        perms = list(profile.permissions or [])
        if STATS_VIEW in perms:
            continue
        if "roles.manage" in perms and "users.view" in perms:
            perms.append(STATS_VIEW)
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


def remove_stats_view_permission(apps, schema_editor):
    StaffRole = apps.get_model("users", "StaffRole")
    StaffProfile = apps.get_model("users", "StaffProfile")

    for role in StaffRole.objects.all():
        perms = [p for p in (role.permissions or []) if p != STATS_VIEW]
        if perms != (role.permissions or []):
            role.permissions = perms
            role.save(update_fields=["permissions"])

    for profile in StaffProfile.objects.all():
        perms = [p for p in (profile.permissions or []) if p != STATS_VIEW]
        if perms != (profile.permissions or []):
            profile.permissions = perms
            profile.save(update_fields=["permissions"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0009_locker_permissions"),
    ]

    operations = [
        migrations.RunPython(
            add_stats_view_permission,
            remove_stats_view_permission,
        ),
    ]

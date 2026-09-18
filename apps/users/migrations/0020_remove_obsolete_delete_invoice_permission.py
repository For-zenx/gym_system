from django.db import migrations


OBSOLETE_PERMISSION = "billing.delete_invoice"


def remove_obsolete_permission(apps, schema_editor):
    for model_name in ("StaffRole", "StaffProfile"):
        model = apps.get_model("users", model_name)
        for record in model.objects.all().iterator():
            permissions = record.permissions or []
            cleaned = [code for code in permissions if code != OBSOLETE_PERMISSION]
            if cleaned != permissions:
                record.permissions = cleaned
                record.save(update_fields=["permissions"])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0019_client_grant_admin_access_permission"),
    ]

    operations = [
        migrations.RunPython(remove_obsolete_permission, noop_reverse),
    ]

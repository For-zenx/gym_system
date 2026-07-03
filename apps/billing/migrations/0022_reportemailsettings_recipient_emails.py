from django.db import migrations

from apps.clients.fields import SQLiteJSONField


def copy_recipient_email_to_list(apps, schema_editor):
    ReportEmailSettings = apps.get_model("billing", "ReportEmailSettings")
    for settings_obj in ReportEmailSettings.objects.all():
        old_email = getattr(settings_obj, "recipient_email", "") or ""
        old_email = old_email.strip()
        if old_email:
            settings_obj.recipient_emails = [old_email]
            settings_obj.save(update_fields=["recipient_emails"])


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0021_invoice_anulada_por_invoice_esta_anulada_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportemailsettings",
            name="recipient_emails",
            field=SQLiteJSONField(
                blank=True,
                default=list,
                verbose_name="Correos destinatarios",
            ),
        ),
        migrations.RunPython(copy_recipient_email_to_list, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="reportemailsettings",
            name="recipient_email",
        ),
    ]

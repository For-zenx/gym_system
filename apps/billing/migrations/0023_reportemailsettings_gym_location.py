from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0022_reportemailsettings_recipient_emails"),
    ]

    operations = [
        migrations.AddField(
            model_name="reportemailsettings",
            name="gym_location",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Ciudad o sede opcional. Aparece en el asunto y cuerpo del correo de reportes.",
                max_length=100,
                verbose_name="Localidad del gimnasio",
            ),
        ),
    ]

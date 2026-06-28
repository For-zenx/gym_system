from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0017_alter_clientserviceperiod_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingsettings",
            name="fixed_grace_days",
            field=models.PositiveSmallIntegerField(
                default=0,
                help_text="Días de acceso biométrico tras vencer el último periodo fijo pagado.",
                verbose_name="Días de gracia (plan fijo)",
            ),
        ),
    ]

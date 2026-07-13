from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="printerconfig",
            name="baudrate",
            field=models.PositiveIntegerField(default=9600, verbose_name="Baudrate"),
        ),
    ]

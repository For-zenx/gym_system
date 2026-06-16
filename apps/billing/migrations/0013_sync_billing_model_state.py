from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0012_saleitem_locker_assignment"),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="saleitem",
            options={
                "ordering": ["name", "id"],
                "verbose_name": "Producto o servicio",
                "verbose_name_plural": "Productos y servicios",
            },
        ),
        migrations.AlterField(
            model_name="reportemailsettings",
            name="recipient_email",
            field=models.EmailField(blank=True, default="", max_length=254, verbose_name="Correo del destinatario"),
        ),
    ]

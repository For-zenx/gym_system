from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("clients", "0009_guest_category_and_guest_pass"),
    ]

    operations = [
        migrations.AlterField(
            model_name="guestpass",
            name="sponsor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="sponsored_guest_passes",
                to="clients.client",
                verbose_name="Afiliado responsable",
            ),
        ),
    ]

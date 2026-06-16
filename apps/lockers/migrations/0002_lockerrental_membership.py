from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0015_client_service_period"),
        ("lockers", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="lockerrental",
            name="membership",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="locker_rentals",
                to="billing.membership",
                verbose_name="Membresía",
            ),
        ),
    ]

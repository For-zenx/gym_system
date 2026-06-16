from decimal import Decimal

from django.db import migrations, models

LOCKER_RENTAL = "LOCKER_RENTAL"


def seed_locker_rental_item(apps, schema_editor):
    SaleItem = apps.get_model("billing", "SaleItem")

    existing_system = SaleItem.objects.filter(system_code=LOCKER_RENTAL).first()
    if existing_system:
        return

    locker_candidates = SaleItem.objects.filter(requires_locker_assignment=True).order_by("id")
    primary = locker_candidates.first()
    if primary:
        primary.system_code = LOCKER_RENTAL
        primary.requires_locker_assignment = True
        primary.item_type = "SERVICE"
        primary.is_active = True
        primary.save(
            update_fields=[
                "system_code",
                "requires_locker_assignment",
                "item_type",
                "is_active",
            ]
        )
        locker_candidates.exclude(pk=primary.pk).update(requires_locker_assignment=False)
        return

    SaleItem.objects.create(
        name="Alquiler de casillero",
        description="Tarifa de alquiler de casillero del gimnasio.",
        item_type="SERVICE",
        price_usd=Decimal("5.00"),
        requires_locker_assignment=True,
        default_rental_days=30,
        system_code=LOCKER_RENTAL,
        is_active=True,
    )


def unseed_locker_rental_item(apps, schema_editor):
    SaleItem = apps.get_model("billing", "SaleItem")
    SaleItem.objects.filter(system_code=LOCKER_RENTAL).update(system_code=None)


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0013_sync_billing_model_state"),
    ]

    operations = [
        migrations.AddField(
            model_name="saleitem",
            name="system_code",
            field=models.CharField(
                blank=True,
                choices=[("LOCKER_RENTAL", "Alquiler de casillero")],
                max_length=32,
                null=True,
                unique=True,
                verbose_name="Código de sistema",
            ),
        ),
        migrations.RunPython(seed_locker_rental_item, unseed_locker_rental_item),
    ]

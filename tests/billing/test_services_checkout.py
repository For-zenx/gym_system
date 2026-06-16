import pytest
from django.core.exceptions import ValidationError

from apps.billing.models import ClientServicePeriod, SaleItem
from apps.billing.services import register_checkout
from apps.lockers.models import LockerRental
from tests import factories


@pytest.mark.django_db
def test_register_checkout__service_without_plan_raises(
    create_client,
    create_sale_item,
    exchange_rate,
):
    client = create_client()
    towel = create_sale_item(item_type=SaleItem.ItemType.SERVICE, name="Toallas")

    with pytest.raises(ValidationError) as exc_info:
        register_checkout(
            client,
            product_lines=[{"item_id": towel.pk, "qty": 1}],
        )

    assert "servicios" in str(exc_info.value).lower()


@pytest.mark.django_db
def test_register_checkout__product_without_plan_ok(
    create_client,
    create_sale_item,
    exchange_rate,
):
    client = create_client()
    water = create_sale_item(item_type=SaleItem.ItemType.PRODUCT, name="Agua")

    result = register_checkout(
        client,
        product_lines=[{"item_id": water.pk, "qty": 2}],
    )

    assert result.invoice is not None
    assert result.membership is None
    assert result.invoice.lines.filter(sale_item=water).exists()


@pytest.mark.django_db
def test_register_checkout__towel_creates_service_period(
    create_client,
    create_plan,
    create_sale_item,
    exchange_rate,
):
    client = create_client()
    plan = create_plan()
    towel = create_sale_item(item_type=SaleItem.ItemType.SERVICE, name="Toallas")

    result = register_checkout(
        client,
        plan=plan,
        product_lines=[{"item_id": towel.pk, "qty": 1}],
    )

    period = ClientServicePeriod.objects.get(client=client, sale_item=towel)
    assert period.status == ClientServicePeriod.Status.ACTIVE
    assert period.start_date == result.membership.fecha_inicio
    assert period.end_date == result.membership.fecha_fin
    assert period.membership_id == result.membership.pk


@pytest.mark.django_db
def test_register_checkout__locker_uses_membership_dates(
    create_client,
    create_plan,
    exchange_rate,
):
    client = create_client()
    plan = create_plan()
    locker_item = factories.get_or_create_locker_rental_item()
    locker = factories.create_locker()

    result = register_checkout(
        client,
        plan=plan,
        product_lines=[
            {
                "item_id": locker_item.pk,
                "qty": 1,
                "locker_id": str(locker.pk),
                "locker_start": "2000-01-01",
                "locker_end": "2000-01-31",
            }
        ],
    )

    rental = LockerRental.objects.get(client=client)
    assert rental.start_date == result.membership.fecha_inicio
    assert rental.end_date == result.membership.fecha_fin
    assert rental.membership_id == result.membership.pk

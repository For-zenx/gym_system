from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.billing.models import ClientServicePeriod, Invoice, SaleItem
from apps.billing.services import register_checkout
from apps.lockers.models import LockerRental
from tests import factories

DEFAULT_PAYMENT = Invoice.PaymentMethod.CASH_VES


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
            payment_method=DEFAULT_PAYMENT,
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
        payment_method=DEFAULT_PAYMENT,
    )

    assert result.invoice is not None
    assert result.membership is None
    assert result.invoice.lines.filter(sale_item=water).exists()
    assert result.invoice.payment_method == DEFAULT_PAYMENT


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
        payment_method=DEFAULT_PAYMENT,
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
        payment_method=DEFAULT_PAYMENT,
    )

    rental = LockerRental.objects.get(client=client)
    assert rental.start_date == result.membership.fecha_inicio
    assert rental.end_date == result.membership.fecha_fin
    assert rental.membership_id == result.membership.pk


@pytest.mark.django_db
def test_register_checkout__missing_payment_method_raises(
    create_client,
    create_sale_item,
    exchange_rate,
):
    client = create_client()
    water = create_sale_item(
        item_type=SaleItem.ItemType.PRODUCT,
        name="Agua",
        price_usd=Decimal("10.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        register_checkout(
            client,
            product_lines=[{"item_id": water.pk, "qty": 1}],
            payment_method=None,
        )

    assert "forma de pago" in str(exc_info.value).lower() or "pago" in str(exc_info.value).lower()
    assert not Invoice.objects.filter(client=client).exists()


@pytest.mark.django_db
def test_register_checkout__mixed_payment_splits_ok(
    create_client,
    create_sale_item,
    exchange_rate,
):
    client = create_client()
    water = create_sale_item(
        item_type=SaleItem.ItemType.PRODUCT,
        name="Agua Mix",
        price_usd=Decimal("10.00"),
    )
    total_ves = (Decimal("10.00") * exchange_rate.tasa_ves).quantize(Decimal("0.01"))
    half = (total_ves / 2).quantize(Decimal("0.01"))
    other = total_ves - half

    result = register_checkout(
        client,
        product_lines=[{"item_id": water.pk, "qty": 1}],
        payment_method=Invoice.PaymentMethod.MIXED,
        payment_splits=[
            {"method": Invoice.PaymentMethod.CASH_VES, "amount_ves": str(half)},
            {"method": Invoice.PaymentMethod.DEBIT, "amount_ves": str(other)},
        ],
    )

    assert result.invoice is not None
    assert result.invoice.payment_method == Invoice.PaymentMethod.MIXED
    assert result.invoice.monto_total == total_ves
    assert len(result.invoice.payment_splits) == 2


@pytest.mark.django_db
def test_register_checkout__mixed_payment_splits_mismatch_raises(
    create_client,
    create_sale_item,
    exchange_rate,
):
    client = create_client()
    water = create_sale_item(
        item_type=SaleItem.ItemType.PRODUCT,
        name="Agua Bad Mix",
        price_usd=Decimal("10.00"),
    )

    with pytest.raises(ValidationError) as exc_info:
        register_checkout(
            client,
            product_lines=[{"item_id": water.pk, "qty": 1}],
            payment_method=Invoice.PaymentMethod.MIXED,
            payment_splits=[
                {"method": Invoice.PaymentMethod.CASH_VES, "amount_ves": "100.00"},
                {"method": Invoice.PaymentMethod.DEBIT, "amount_ves": "100.00"},
            ],
        )

    assert "coincide" in str(exc_info.value).lower() or "desglose" in str(exc_info.value).lower()
    assert not Invoice.objects.filter(client=client).exists()

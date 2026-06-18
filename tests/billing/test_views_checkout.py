import pytest
from datetime import date, timedelta
from django.urls import reverse

from apps.billing.models import Invoice, Membership
from apps.lockers.models import Locker, LockerRental
from tests.billing.conftest import build_checkout_post
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed
from tests import factories

CHARGE_PERMISSION = "billing.charge"
PRODUCTS_PERMISSION = "products.view"
CUT_DATE_PERMISSION = "billing.change_cut_date"
MEMBERSHIP_DELETE_PERMISSION = "billing.delete_queued_membership"


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [CHARGE_PERMISSION])],
)
@pytest.mark.django_db
def test_charge_checkout__access(
    client,
    create_staff_user,
    create_client,
    create_plan,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    create_plan()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:charge_checkout", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, CHARGE_PERMISSION, url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [CHARGE_PERMISSION])],
)
@pytest.mark.django_db
def test_renew_plan__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:renew_plan", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.post(url, {"origin": "profile"})
    assert_access(
        response,
        is_logged_in,
        permissions,
        CHARGE_PERMISSION,
        url,
        get_login_url,
        success_status=302,
    )


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [CUT_DATE_PERMISSION])],
)
@pytest.mark.django_db
def test_change_cut_date__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:change_cut_date", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.post(url, {"cut_day": "15"})
    assert_access(
        response,
        is_logged_in,
        permissions,
        CUT_DATE_PERMISSION,
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and CUT_DATE_PERMISSION in permissions:
        assert response.url == reverse(
            "clients:profile",
            kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
        )


@pytest.mark.django_db
def test_charge_checkout__post_locker_without_products_view(
    client,
    create_staff_user,
    create_client,
    create_plan,
    exchange_rate,
):
    affiliate = create_client()
    plan = create_plan()
    locker_item = factories.get_or_create_locker_rental_item()
    locker = factories.create_locker()
    staff = create_staff_user(permissions=[CHARGE_PERMISSION])
    client.force_login(staff)

    url = reverse("billing:charge_checkout", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    post_data = build_checkout_post(
        plan,
        product_lines=[
            {
                "item_id": locker_item.pk,
                "qty": 1,
                "locker_id": locker.pk,
            }
        ],
    )
    response = client.post(url, post_data)

    assert response.status_code == 302
    assert "cobro-exito" not in response.url
    assert not Invoice.objects.filter(client=affiliate).exists()
    assert not LockerRental.objects.filter(client=affiliate).exists()
    locker.refresh_from_db()
    assert locker.status == Locker.Status.AVAILABLE


@pytest.mark.django_db
def test_charge_checkout__post_plan_and_locker(
    client,
    create_staff_user,
    create_client,
    create_plan,
    exchange_rate,
):
    affiliate = create_client()
    plan = create_plan()
    locker_item = factories.get_or_create_locker_rental_item()
    locker = factories.create_locker()
    staff = create_staff_user(permissions=[CHARGE_PERMISSION, PRODUCTS_PERMISSION])
    client.force_login(staff)

    url = reverse("billing:charge_checkout", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    post_data = build_checkout_post(
        plan,
        product_lines=[
            {
                "item_id": locker_item.pk,
                "qty": 1,
                "locker_id": locker.pk,
                "locker_start": "2000-01-01",
                "locker_end": "2000-01-31",
            }
        ],
    )
    response = client.post(url, post_data)

    assert response.status_code == 302
    assert "cobro-exito" in response.url

    rental = LockerRental.objects.get(client=affiliate)
    membership = rental.membership
    assert membership is not None
    assert rental.start_date == membership.fecha_inicio
    assert rental.end_date == membership.fecha_fin
    locker.refresh_from_db()
    assert locker.status == Locker.Status.OCCUPIED


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [MEMBERSHIP_DELETE_PERMISSION])],
)
@pytest.mark.django_db
def test_membership_delete__access(
    client,
    create_staff_user,
    create_membership,
    get_login_url,
    is_logged_in,
    permissions,
):
    membership = create_membership(fecha_inicio=date.today() + timedelta(days=7))
    affiliate = membership.client
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:membership_delete", kwargs={"pk": membership.pk})
    response = client.post(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        MEMBERSHIP_DELETE_PERMISSION,
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and MEMBERSHIP_DELETE_PERMISSION in permissions:
        assert response.url == reverse(
            "clients:profile",
            kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
        )


@pytest.mark.django_db
def test_membership_delete__post_queued_deletes(client, create_staff_user, create_membership):
    membership = create_membership(fecha_inicio=date.today() + timedelta(days=7))
    membership_pk = membership.pk
    affiliate = membership.client
    staff = create_staff_user(permissions=[MEMBERSHIP_DELETE_PERMISSION])
    client.force_login(staff)

    url = reverse("billing:membership_delete", kwargs={"pk": membership_pk})
    response = client.post(url)

    assert response.status_code == 302
    assert response.url == reverse(
        "clients:profile",
        kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
    )
    assert not Membership.objects.filter(pk=membership_pk).exists()


@pytest.mark.django_db
def test_membership_delete__post_active_persists(client, create_staff_user, create_membership):
    membership = create_membership(fecha_inicio=date.today())
    membership_pk = membership.pk
    staff = create_staff_user(permissions=[MEMBERSHIP_DELETE_PERMISSION])
    client.force_login(staff)

    url = reverse("billing:membership_delete", kwargs={"pk": membership_pk})
    response = client.post(url)

    assert response.status_code == 302
    assert Membership.objects.filter(pk=membership_pk).exists()

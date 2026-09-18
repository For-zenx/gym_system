import pytest
from datetime import date, timedelta
from django.urls import reverse
from unittest.mock import MagicMock

from apps.billing.models import Invoice, Membership, Plan, SaleItem
from apps.access.services import evaluate_access_integrity
from apps.billing.cycle import next_cut_on_or_after
from apps.billing.services import grant_admin_access, preview_membership_period, register_checkout
from apps.clients.models import Client
from apps.clients.validation import split_cedula
from tests.core.conftest import FAKE_PHOTO_B64
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed

REENROLL_JSON_HEADER = {"HTTP_X_REENROLL_SUBMIT": "1"}
GRANT_ADMIN_PERMISSION = "clients.grant_admin_access"


def _edit_post_data(affiliate):
    prefix, numero = split_cedula(affiliate.cedula)
    return {
        "nombre": affiliate.nombre,
        "cedula_prefix": prefix,
        "cedula_numero": numero,
        "telefono": affiliate.telefono or "",
        "fecha_nacimiento": "",
        "sexo": affiliate.sexo or "",
    }


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["clients.view_list"])],
)
@pytest.mark.django_db
def test_client_list__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("clients:client_list")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "clients.view_list", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["clients.view_profile"])],
)
@pytest.mark.django_db
def test_client_profile__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("clients:profile", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "clients.view_profile", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["clients.edit"])],
)
@pytest.mark.django_db
def test_edit_client__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("clients:edit_client", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.post(url, _edit_post_data(affiliate))
    assert_access(
        response,
        is_logged_in,
        permissions,
        "clients.edit",
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and "clients.edit" in permissions:
        assert response.url == reverse(
            "clients:profile",
            kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
        )


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["clients.delete"])],
)
@pytest.mark.django_db
def test_client_delete__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("clients:delete_client", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.post(url, {"confirm_delete": "0"})
    assert_access(
        response,
        is_logged_in,
        permissions,
        "clients.delete",
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and "clients.delete" in permissions:
        assert Client.objects.filter(pk=affiliate.pk).exists()


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["clients.delete"])],
)
@pytest.mark.django_db
def test_inactive_clients_preview__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    base_url = reverse("clients:inactive_clients_preview")
    url = base_url + "?years=1"
    response = client.get(base_url, {"years": "1"})
    assert_access(
        response,
        is_logged_in,
        permissions,
        "clients.delete",
        url,
        get_login_url,
        success_status=200,
    )
    if is_logged_in and "clients.delete" in permissions:
        payload = response.json()
        assert payload["status"] == "success"
        assert "count" in payload
        assert "sample" in payload


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["clients.delete"])],
)
@pytest.mark.django_db
def test_inactive_clients_bulk_delete__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("clients:inactive_clients_bulk_delete")
    response = client.post(url, {})
    assert_access(
        response,
        is_logged_in,
        permissions,
        "clients.delete",
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and "clients.delete" in permissions:
        assert Client.objects.filter(pk=affiliate.pk).exists()


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["clients.edit"])],
)
@pytest.mark.django_db
def test_re_enroll__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("clients:re_enroll", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "clients.edit", url, get_login_url)


@pytest.mark.django_db
def test_re_enroll__post_missing_photo(client, create_staff_user, create_client):
    affiliate = create_client()
    staff = create_staff_user(permissions=["clients.edit"])
    client.force_login(staff)

    url = reverse("clients:re_enroll", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.post(url, {}, **REENROLL_JSON_HEADER)

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "error"
    assert "foto" in payload["message"].lower()


@pytest.mark.django_db
def test_re_enroll__post_success_json(client, create_staff_user, create_client, monkeypatch):
    mock_replace_photo = MagicMock(side_effect=lambda affiliate, _photo: affiliate)
    monkeypatch.setattr("apps.clients.views.replace_client_front_photo", mock_replace_photo)
    affiliate = create_client()
    staff = create_staff_user(permissions=["clients.edit"])
    client.force_login(staff)

    url = reverse("clients:re_enroll", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.post(
        url,
        {"foto_frente_base64": FAKE_PHOTO_B64},
        **REENROLL_JSON_HEADER,
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["redirect_url"] == reverse(
        "clients:profile",
        kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
    )
    mock_replace_photo.assert_called_once()


@pytest.mark.django_db
def test_client_profile__active_services_display(
    client,
    create_staff_user,
    create_client,
    create_plan,
    create_sale_item,
    exchange_rate,
):
    affiliate = create_client()
    plan = create_plan()
    towel = create_sale_item(item_type=SaleItem.ItemType.SERVICE, name="Toallas Test")
    register_checkout(
        affiliate,
        plan=plan,
        product_lines=[{"item_id": towel.pk, "qty": 1}],
        payment_method="CASH_VES",
    )

    staff = create_staff_user(permissions=["clients.view_profile"])
    client.force_login(staff)

    url = reverse("clients:profile", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Toallas Test" in content
    assert "Extras vigentes" in content


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [GRANT_ADMIN_PERMISSION])],
)
@pytest.mark.django_db
def test_grant_admin_access__access(
    client,
    create_staff_user,
    create_client,
    create_plan,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    plan = create_plan(billing_type=Plan.BillingType.FIXED)
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse(
        "clients:grant_admin_access",
        kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
    )
    response = client.post(
        url,
        {
            "confirm_admin_access": "1",
            "plan_id": str(plan.pk),
            "valid_until": (date.today() + timedelta(days=30)).isoformat(),
        },
    )
    assert_access(
        response,
        is_logged_in,
        permissions,
        GRANT_ADMIN_PERMISSION,
        url,
        get_login_url,
        success_status=302,
    )


@pytest.mark.django_db
def test_grant_admin_access__post_grants_membership(
    client,
    create_staff_user,
    create_client,
    create_plan,
):
    affiliate = create_client()
    plan = create_plan(billing_type=Plan.BillingType.FIXED)
    valid_until = date.today() + timedelta(days=45)
    staff = create_staff_user(permissions=[GRANT_ADMIN_PERMISSION])
    client.force_login(staff)

    url = reverse(
        "clients:grant_admin_access",
        kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
    )
    response = client.post(
        url,
        {
            "plan_id": str(plan.pk),
            "valid_until": valid_until.isoformat(),
        },
    )

    assert response.status_code == 302
    membership = Membership.objects.get(client=affiliate)
    assert membership.plan_id == plan.pk
    assert membership.fecha_fin == valid_until
    assert not Invoice.objects.filter(client=affiliate).exists()


@pytest.mark.django_db
def test_grant_admin_access__optional_cut_date_change(
    client,
    create_staff_user,
    create_client,
    create_plan,
):
    affiliate = create_client()
    affiliate.fecha_corte_dia = 16
    affiliate.save(update_fields=["fecha_corte_dia"])
    plan = create_plan(billing_type=Plan.BillingType.FIXED)
    valid_until = date(2026, 12, 31)
    staff = create_staff_user(permissions=[GRANT_ADMIN_PERMISSION])
    client.force_login(staff)

    response = client.post(
        reverse(
            "clients:grant_admin_access",
            kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
        ),
        {
            "plan_id": str(plan.pk),
            "valid_until": valid_until.isoformat(),
            "change_cut_date": "1",
        },
    )

    assert response.status_code == 302
    affiliate.refresh_from_db()
    assert affiliate.fecha_corte_dia == 31


@pytest.mark.django_db
def test_admin_access__only_grant_permission_can_revoke(
    client,
    create_staff_user,
    create_client,
    create_plan,
):
    affiliate = create_client()
    plan = create_plan(billing_type=Plan.BillingType.FIXED)
    membership = grant_admin_access(
        affiliate,
        plan,
        date.today() + timedelta(days=30),
        None,
    )
    url = reverse("billing:delete_membership_action", kwargs={"pk": membership.pk})
    billing_staff = create_staff_user(permissions=["billing.delete_membership"])
    client.force_login(billing_staff)

    denied = client.post(url)

    assert denied.status_code == 403
    membership.refresh_from_db()
    assert membership.status == Membership.Status.ACTIVE

    admin_staff = create_staff_user(permissions=[GRANT_ADMIN_PERMISSION])
    client.force_login(admin_staff)
    allowed = client.post(url)

    assert allowed.status_code == 302
    membership.refresh_from_db()
    assert membership.status == Membership.Status.VOIDED


@pytest.mark.django_db
def test_grant_admin_access__preserves_paid_membership_invoice_cut_and_next_charge(
    create_client,
    create_plan,
    exchange_rate,
):
    affiliate = create_client()
    paid_plan = create_plan(billing_type=Plan.BillingType.FIXED)
    admin_plan = create_plan(billing_type=Plan.BillingType.FIXED)
    paid = register_checkout(
        affiliate,
        plan=paid_plan,
        payment_cut_day=16,
        payment_method=Invoice.PaymentMethod.CASH_VES,
    )
    affiliate.refresh_from_db()
    original_plan_id = affiliate.fixed_plan_id
    original_cut_day = affiliate.fecha_corte_dia

    admin_membership = grant_admin_access(
        affiliate,
        admin_plan,
        date.today() + timedelta(days=90),
        None,
    )

    paid.membership.refresh_from_db()
    paid.invoice.refresh_from_db()
    affiliate.refresh_from_db()
    assert paid.membership.status == Membership.Status.ACTIVE
    assert paid.invoice.esta_anulada is False
    assert affiliate.fixed_plan_id == original_plan_id
    assert affiliate.fecha_corte_dia == original_cut_day
    assert admin_membership.origen == Membership.Origin.ADMIN
    assert admin_membership.fecha_corte_dia is None

    preview = preview_membership_period(affiliate, paid_plan)
    assert preview["fecha_inicio"] == next_cut_on_or_after(
        paid.membership.fecha_fin,
        original_cut_day,
    )
    assert preview["fecha_inicio"] < admin_membership.fecha_fin


@pytest.mark.django_db
def test_grant_admin_access__replaces_only_previous_admin(create_client, create_plan):
    affiliate = create_client()
    plan = create_plan(billing_type=Plan.BillingType.FIXED)
    paid_membership = Membership.objects.create(
        client=affiliate,
        plan=plan,
        fecha_inicio=date.today(),
        fecha_fin=date.today() + timedelta(days=30),
        origen=Membership.Origin.UNKNOWN,
    )
    first_admin = grant_admin_access(
        affiliate,
        plan,
        date.today() + timedelta(days=60),
        None,
    )

    second_admin = grant_admin_access(
        affiliate,
        plan,
        date.today() + timedelta(days=90),
        None,
    )

    paid_membership.refresh_from_db()
    first_admin.refresh_from_db()
    assert paid_membership.status == Membership.Status.ACTIVE
    assert first_admin.status == Membership.Status.CLOSED
    assert second_admin.status == Membership.Status.ACTIVE
    assert Membership.objects.for_billing().filter(pk=paid_membership.pk).exists()
    assert not Membership.objects.for_billing().filter(pk=second_admin.pk).exists()


@pytest.mark.django_db
def test_admin_access__grants_entry_without_marking_paid_subscription_active(
    create_client,
    create_plan,
):
    affiliate = create_client()
    affiliate.fecha_corte_dia = 16
    affiliate.save(update_fields=["fecha_corte_dia"])
    plan = create_plan(billing_type=Plan.BillingType.FIXED)
    grant_admin_access(
        affiliate,
        plan,
        date.today() + timedelta(days=30),
        None,
    )

    granted, _ = evaluate_access_integrity(affiliate)

    assert granted is True
    assert affiliate.fixed_subscription_status == "SUSPENDED"

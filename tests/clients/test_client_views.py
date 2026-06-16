import pytest
from django.urls import reverse

from apps.clients.models import Client
from apps.clients.validation import split_cedula
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed


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


@pytest.mark.django_db
def test_client_profile__active_services_display(
    client,
    create_staff_user,
    create_client,
    create_plan,
    create_sale_item,
    exchange_rate,
):
    from apps.billing.models import SaleItem
    from apps.billing.services import register_checkout

    affiliate = create_client()
    plan = create_plan()
    towel = create_sale_item(item_type=SaleItem.ItemType.SERVICE, name="Toallas Test")
    register_checkout(
        affiliate,
        plan=plan,
        product_lines=[{"item_id": towel.pk, "qty": 1}],
    )

    staff = create_staff_user(permissions=["clients.view_profile"])
    client.force_login(staff)

    url = reverse("clients:profile", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert "Toallas Test" in content
    assert "Servicios activos" in content

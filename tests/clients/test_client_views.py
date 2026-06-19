import pytest
from django.urls import reverse
from unittest.mock import MagicMock

from apps.clients.models import Client
from apps.clients.validation import split_cedula
from tests.core.conftest import FAKE_PHOTO_B64
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed

REENROLL_JSON_HEADER = {"HTTP_X_REENROLL_SUBMIT": "1"}


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
    assert "Extras vigentes" in content

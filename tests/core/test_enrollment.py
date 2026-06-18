import pytest
from django.urls import reverse
from unittest.mock import MagicMock

from apps.clients.models import Client
from tests.core.conftest import FAKE_PHOTO_B64, build_enrollment_post
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed

ENROLL_PERMISSION = "clients.enroll"
JSON_SUBMIT_HEADER = {"HTTP_X_ENROLLMENT_SUBMIT": "1"}


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [ENROLL_PERMISSION])],
)
@pytest.mark.django_db
def test_enrollment__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("enrollment")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, ENROLL_PERMISSION, url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [ENROLL_PERMISSION])],
)
@pytest.mark.django_db
def test_enrollment_cedula_check__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("enrollment_cedula_check")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, ENROLL_PERMISSION, url, get_login_url)
    if is_logged_in and ENROLL_PERMISSION in permissions:
        assert response.json()["exists"] is False


@pytest.mark.django_db
def test_enrollment_cedula_check__unknown_cedula(client, create_staff_user):
    staff = create_staff_user(permissions=[ENROLL_PERMISSION])
    client.force_login(staff)

    url = reverse("enrollment_cedula_check")
    response = client.get(url, {"cedula_prefix": "V-", "cedula_numero": "99999999"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["exists"] is False
    assert payload["profile_url"] is None
    assert payload["re_enroll_url"] is None


@pytest.mark.django_db
def test_enrollment_cedula_check__existing_cedula(client, create_staff_user, create_client):
    affiliate = create_client(cedula="V-12345678")
    staff = create_staff_user(permissions=[ENROLL_PERMISSION])
    client.force_login(staff)

    url = reverse("enrollment_cedula_check")
    response = client.get(url, {"cedula_prefix": "V-", "cedula_numero": "12345678"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["exists"] is True
    assert payload["profile_url"] == reverse(
        "clients:profile",
        kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
    )
    assert payload["re_enroll_url"] == reverse(
        "clients:re_enroll",
        kwargs={"codigo_afiliado": affiliate.codigo_afiliado},
    )


@pytest.mark.django_db
def test_enrollment__post_missing_photo(client, create_staff_user):
    staff = create_staff_user(permissions=[ENROLL_PERMISSION])
    client.force_login(staff)

    url = reverse("enrollment")
    post_data = build_enrollment_post(foto_frente_base64="")
    response = client.post(url, post_data, **JSON_SUBMIT_HEADER)

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "error"
    assert "foto" in payload["message"].lower()


@pytest.mark.django_db
def test_enrollment__post_missing_terms(client, create_staff_user):
    staff = create_staff_user(permissions=[ENROLL_PERMISSION])
    client.force_login(staff)

    url = reverse("enrollment")
    post_data = build_enrollment_post()
    post_data.pop("terms_accepted")
    response = client.post(url, post_data, **JSON_SUBMIT_HEADER)

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "error"
    assert "términos" in payload["message"].lower() or "terminos" in payload["message"].lower()


@pytest.mark.django_db
def test_enrollment__post_duplicate_cedula(client, create_staff_user, create_client):
    create_client(cedula="V-87654321")
    staff = create_staff_user(permissions=[ENROLL_PERMISSION])
    client.force_login(staff)

    url = reverse("enrollment")
    response = client.post(url, build_enrollment_post(), **JSON_SUBMIT_HEADER)

    assert response.status_code == 400
    payload = response.json()
    assert payload["status"] == "error"
    assert "registrado" in payload["message"].lower()
    assert Client.objects.filter(cedula="V-87654321").count() == 1


@pytest.mark.django_db
def test_enrollment__post_success_json(client, create_staff_user, monkeypatch):
    mock_apply_photo = MagicMock(side_effect=lambda affiliate, _photo: affiliate)
    monkeypatch.setattr("apps.core.views.apply_front_photo_from_b64", mock_apply_photo)
    staff = create_staff_user(permissions=[ENROLL_PERMISSION])
    client.force_login(staff)

    url = reverse("enrollment")
    response = client.post(url, build_enrollment_post(), **JSON_SUBMIT_HEADER)

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert "/billing/cobro/" in payload["redirect_url"]
    assert "origin=enrollment" in payload["redirect_url"]

    new_client = Client.objects.get(cedula="V-87654321")
    assert new_client.nombre == "Nuevo Afiliado Test"
    assert new_client.terms_accepted_at is not None
    mock_apply_photo.assert_called_once()


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [ENROLL_PERMISSION])],
)
@pytest.mark.django_db
def test_enrollment_billing__access(
    client,
    create_staff_user,
    create_client,
    get_login_url,
    is_logged_in,
    permissions,
):
    affiliate = create_client()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("enrollment_billing", kwargs={"codigo_afiliado": affiliate.codigo_afiliado})
    response = client.get(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        ENROLL_PERMISSION,
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and ENROLL_PERMISSION in permissions:
        assert "/billing/cobro/" in response.url
        assert affiliate.codigo_afiliado in response.url
        assert "origin=enrollment" in response.url

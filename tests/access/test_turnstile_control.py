import pytest
from django.urls import reverse

from apps.access.hardware import TurnstilePulseResult
from apps.access.models import ManualTurnstileAccess
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed

TURNSTILE_PERMISSION = "access.open_turnstile"


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [TURNSTILE_PERMISSION])],
)
@pytest.mark.django_db
def test_turnstile_control__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("access:turnstile_control")
    response = client.get(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        TURNSTILE_PERMISSION,
        url,
        get_login_url,
    )


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [TURNSTILE_PERMISSION])],
)
@pytest.mark.django_db
def test_turnstile_client_search__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("access:turnstile_client_search")
    response = client.get(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        TURNSTILE_PERMISSION,
        url,
        get_login_url,
    )
    if is_logged_in and TURNSTILE_PERMISSION in permissions:
        assert response.json()["results"] == []


@pytest.mark.django_db
def test_turnstile_client_search__short_query_returns_empty(client, create_staff_user, create_client):
    create_client(nombre="Juan Perez Test")
    staff = create_staff_user(permissions=[TURNSTILE_PERMISSION])
    client.force_login(staff)

    url = reverse("access:turnstile_client_search")
    response = client.get(url, {"q": "J"})

    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.django_db
def test_turnstile_client_search__finds_client(client, create_staff_user, create_client):
    affiliate = create_client(nombre="Maria Lopez Turnstile", cedula="V-11112222")
    staff = create_staff_user(permissions=[TURNSTILE_PERMISSION])
    client.force_login(staff)

    url = reverse("access:turnstile_client_search")
    response = client.get(url, {"q": "Maria Lopez"})

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0]["id"] == affiliate.pk
    assert results[0]["codigo_afiliado"] == affiliate.codigo_afiliado
    assert "access_warning" in results[0]


@pytest.mark.django_db
def test_turnstile_control__post_guest_persists(client, create_staff_user, monkeypatch):
    monkeypatch.setattr(
        "apps.access.views.open_turnstile",
        lambda: TurnstilePulseResult(True, "COM_TEST", 1.0),
    )
    staff = create_staff_user(permissions=[TURNSTILE_PERMISSION])
    client.force_login(staff)

    url = reverse("access:turnstile_control")
    response = client.post(
        url,
        {
            "person_name": "Proveedor Demo",
            "reason": ManualTurnstileAccess.Reason.GUEST_OR_VENDOR,
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("access:turnstile_control")

    record = ManualTurnstileAccess.objects.get()
    assert record.person_name == "Proveedor Demo"
    assert record.client is None
    assert record.reason == ManualTurnstileAccess.Reason.GUEST_OR_VENDOR
    assert record.opened_by == staff
    assert record.hardware_success is True
    assert record.port_used == "COM_TEST"


@pytest.mark.django_db
def test_turnstile_control__post_with_client_persists(
    client,
    create_staff_user,
    create_client,
    monkeypatch,
):
    monkeypatch.setattr(
        "apps.access.views.open_turnstile",
        lambda: TurnstilePulseResult(True, "COM_TEST", 1.0),
    )
    affiliate = create_client()
    staff = create_staff_user(permissions=[TURNSTILE_PERMISSION])
    client.force_login(staff)

    url = reverse("access:turnstile_control")
    response = client.post(
        url,
        {
            "client_id": affiliate.pk,
            "reason": ManualTurnstileAccess.Reason.BIOMETRIC_FAILURE,
        },
    )

    assert response.status_code == 302
    record = ManualTurnstileAccess.objects.get()
    assert record.client == affiliate
    assert record.person_name == affiliate.nombre
    assert record.reason == ManualTurnstileAccess.Reason.BIOMETRIC_FAILURE

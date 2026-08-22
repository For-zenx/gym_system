from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.clients.models import Client, GuestPass, PersonCategory
from tests import factories
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed


@pytest.mark.django_db
def test_guest_profile__renders_when_pass_has_no_sponsor(client, create_staff_user):
    staff = create_staff_user(permissions=["guests.view_profile"])
    client.force_login(staff)

    guest = factories.create_client(person_category=PersonCategory.GUEST)
    GuestPass.objects.create(
        guest=guest,
        sponsor=None,
        valid_from=date.today(),
        valid_until=date.today() + timedelta(days=1),
    )

    url = reverse("guests:profile", kwargs={"codigo_afiliado": guest.codigo_afiliado})
    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_guest_issue_pass__blocked_when_active_pass_exists(client, create_staff_user):
    staff = create_staff_user(permissions=["guests.register", "guests.view_profile"])
    client.force_login(staff)

    guest = factories.create_guest()
    profile_url = reverse("guests:profile", kwargs={"codigo_afiliado": guest.codigo_afiliado})
    today = date.today()

    response = client.post(
        reverse("guests:issue_pass", kwargs={"codigo_afiliado": guest.codigo_afiliado}),
        {
            "valid_from": today.isoformat(),
            "valid_until": (today + timedelta(days=3)).isoformat(),
            "notes": "",
        },
    )

    assert response.status_code == 302
    assert response.url == profile_url
    assert guest.guest_passes.count() == 1


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["guests.view_profile"])],
)
@pytest.mark.django_db
def test_guest_profile__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    guest = factories.create_guest()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("guests:profile", kwargs={"codigo_afiliado": guest.codigo_afiliado})
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "guests.view_profile", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["guests.revoke_pass"])],
)
@pytest.mark.django_db
def test_guest_revoke_pass__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    guest = factories.create_guest()
    guest_pass = guest.guest_passes.latest("created_at")
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("guests:revoke_pass", kwargs={"codigo_afiliado": guest.codigo_afiliado})
    response = client.post(url, {"pass_id": str(guest_pass.pk)})
    assert_access(
        response,
        is_logged_in,
        permissions,
        "guests.revoke_pass",
        url,
        get_login_url,
        success_status=302,
    )


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["guests.delete"])],
)
@pytest.mark.django_db
def test_guest_delete__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    guest = factories.create_guest()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("guests:delete", kwargs={"codigo_afiliado": guest.codigo_afiliado})
    response = client.post(
        url,
        {
            "confirm_delete": "0",
            "confirm_codigo": guest.codigo_afiliado,
        },
    )
    assert_access(
        response,
        is_logged_in,
        permissions,
        "guests.delete",
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and "guests.delete" in permissions:
        assert Client.objects.filter(pk=guest.pk).exists()


@pytest.mark.django_db
def test_guest_revoke_pass__post_revokes_active_pass(client, create_staff_user):
    staff = create_staff_user(permissions=["guests.revoke_pass"])
    client.force_login(staff)

    guest = factories.create_guest()
    guest_pass = guest.guest_passes.latest("created_at")
    assert guest_pass.revoked_at is None

    url = reverse("guests:revoke_pass", kwargs={"codigo_afiliado": guest.codigo_afiliado})
    response = client.post(url, {"pass_id": str(guest_pass.pk)})

    assert response.status_code == 302
    guest_pass.refresh_from_db()
    assert guest_pass.revoked_at is not None


@pytest.mark.django_db
def test_guest_delete__post_with_confirm_deletes(client, create_staff_user):
    staff = create_staff_user(permissions=["guests.delete"])
    client.force_login(staff)

    guest = factories.create_guest()
    guest_pk = guest.pk
    codigo = guest.codigo_afiliado

    url = reverse("guests:delete", kwargs={"codigo_afiliado": codigo})
    response = client.post(
        url,
        {
            "confirm_delete": "1",
            "confirm_codigo": codigo,
        },
    )

    assert response.status_code == 302
    assert not Client.objects.filter(pk=guest_pk).exists()

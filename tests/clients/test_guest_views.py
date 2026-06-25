from datetime import date, timedelta

import pytest
from django.urls import reverse

from apps.clients.models import GuestPass, PersonCategory
from tests import factories


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

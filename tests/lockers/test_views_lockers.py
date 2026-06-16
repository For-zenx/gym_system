import pytest
from django.urls import reverse

from apps.lockers.models import Locker
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed
from tests import factories

LOCKER_VIEW = "lockers.view"
LOCKER_MANAGE = "lockers.manage"


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [LOCKER_VIEW])],
)
@pytest.mark.django_db
def test_locker_list__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    factories.create_locker()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("lockers:locker_list")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, LOCKER_VIEW, url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [LOCKER_MANAGE])],
)
@pytest.mark.django_db
def test_locker_create__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("lockers:locker_create")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, LOCKER_MANAGE, url, get_login_url)


@pytest.mark.django_db
def test_locker_create__post_persists(
    client,
    create_staff_user,
):
    staff = create_staff_user(permissions=[LOCKER_MANAGE])
    client.force_login(staff)

    url = reverse("lockers:locker_create")
    response = client.post(
        url,
        {
            "number": "HTTP-99",
            "status": Locker.Status.AVAILABLE,
            "notes": "",
        },
    )

    assert response.status_code == 302
    assert Locker.objects.filter(number="HTTP-99").exists()


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [LOCKER_MANAGE])],
)
@pytest.mark.django_db
def test_locker_update__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    locker = factories.create_locker()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("lockers:locker_update", kwargs={"pk": locker.pk})
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, LOCKER_MANAGE, url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [LOCKER_VIEW])],
)
@pytest.mark.django_db
def test_locker_release__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    locker = factories.create_locker()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("lockers:locker_release", kwargs={"pk": locker.pk})
    response = client.post(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        LOCKER_VIEW,
        url,
        get_login_url,
        success_status=302,
    )

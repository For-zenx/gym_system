import pytest
from django.urls import reverse
from django.utils import timezone

from apps.access.models import AccessLog
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed

STATS_PERMISSION = "stats.view"


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [STATS_PERMISSION])],
)
@pytest.mark.django_db
def test_entry_hours__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("stats:entry_hours")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, STATS_PERMISSION, url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [STATS_PERMISSION])],
)
@pytest.mark.django_db
def test_entry_hours_data__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("stats:entry_hours_data")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, STATS_PERMISSION, url, get_login_url)
    if is_logged_in and STATS_PERMISSION in permissions:
        payload = response.json()
        assert payload["period_days"] == 7
        assert len(payload["counts"]) == 24


@pytest.mark.django_db
def test_entry_hours_data__returns_stats_json(client, create_staff_user, create_client):
    affiliate = create_client()
    AccessLog.objects.create(client=affiliate, resultado=True, timestamp=timezone.now())
    AccessLog.objects.create(client=affiliate, resultado=False, timestamp=timezone.now())

    staff = create_staff_user(permissions=[STATS_PERMISSION])
    client.force_login(staff)

    url = reverse("stats:entry_hours_data")
    response = client.get(url, {"period": "7"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["period_days"] == 7
    assert payload["total_entries"] == 1
    assert len(payload["labels"]) == 24
    assert len(payload["counts"]) == 24
    assert sum(payload["counts"]) == 1


@pytest.mark.django_db
def test_entry_hours_data__invalid_period_falls_back_to_7(client, create_staff_user):
    staff = create_staff_user(permissions=[STATS_PERMISSION])
    client.force_login(staff)

    url = reverse("stats:entry_hours_data")
    response = client.get(url, {"period": "invalid"})

    assert response.status_code == 200
    assert response.json()["period_days"] == 7

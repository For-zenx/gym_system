import pytest
from django.urls import reverse

from tests.helpers import ACCESS_PARAMS, assert_access, assert_any_permission_access, login_if_needed

CONFIG_HOME_PERMISSIONS = (
    "users.view",
    "roles.manage",
    "settings.billing",
    "settings.grace",
    "settings.reports",
)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    [
        (False, []),
        (True, []),
        (True, ["users.view"]),
        (True, ["roles.manage"]),
        (True, ["settings.billing"]),
        (True, ["settings.grace"]),
        (True, ["settings.reports"]),
    ],
)
@pytest.mark.django_db
def test_config_home__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:config_home")
    response = client.get(url)
    assert_any_permission_access(
        response,
        is_logged_in,
        permissions,
        CONFIG_HOME_PERMISSIONS,
        url,
        get_login_url,
    )


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["settings.billing"])],
)
@pytest.mark.django_db
def test_billing_settings__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:billing_settings")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "settings.billing", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["settings.grace"])],
)
@pytest.mark.django_db
def test_grace_settings__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:grace_settings")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "settings.grace", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["settings.reports"])],
)
@pytest.mark.django_db
def test_report_settings__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:report_settings")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "settings.reports", url, get_login_url)

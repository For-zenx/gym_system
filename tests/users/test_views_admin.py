import pytest
from django.urls import reverse

from apps.users.permissions import ALL_PERMISSION_CODES, CASHIER_PERMISSION_CODES, validate_permissions
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed


def test_permission_catalog__corporate_delete_is_manual_and_invoice_delete_is_removed():
    assert "corporate.delete_groups" in ALL_PERMISSION_CODES
    assert "corporate.delete_groups" not in CASHIER_PERMISSION_CODES
    assert "billing.delete_invoice" not in ALL_PERMISSION_CODES
    assert validate_permissions(["billing.delete_invoice", "corporate.delete_groups"]) == [
        "corporate.delete_groups"
    ]


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["roles.manage"])],
)
@pytest.mark.django_db
def test_role_list__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:role_list")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "roles.manage", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["roles.manage"])],
)
@pytest.mark.django_db
def test_role_create__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:role_create")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "roles.manage", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["roles.manage"])],
)
@pytest.mark.django_db
def test_role_update__access(
    client,
    create_staff_user,
    create_staff_role,
    get_login_url,
    is_logged_in,
    permissions,
):
    role = create_staff_role()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:role_update", kwargs={"pk": role.pk})
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "roles.manage", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["roles.manage"])],
)
@pytest.mark.django_db
def test_role_delete__access(
    client,
    create_staff_user,
    create_staff_role,
    get_login_url,
    is_logged_in,
    permissions,
):
    role = create_staff_role()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:role_delete", kwargs={"pk": role.pk})
    response = client.post(url)
    assert_access(
        response,
        is_logged_in,
        permissions,
        "roles.manage",
        url,
        get_login_url,
        success_status=302,
    )


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["users.view"])],
)
@pytest.mark.django_db
def test_staff_user_list__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:staff_user_list")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "users.view", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["users.create"])],
)
@pytest.mark.django_db
def test_staff_user_create__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:staff_user_create")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "users.create", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["users.edit"])],
)
@pytest.mark.django_db
def test_staff_user_update__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    target = create_staff_user(permissions=["dashboard.view"], username="target_staff")
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("users:staff_user_update", kwargs={"pk": target.pk})
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "users.edit", url, get_login_url)

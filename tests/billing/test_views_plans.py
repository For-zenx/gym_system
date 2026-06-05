import pytest
from django.urls import reverse

ACCESS_PARAMS = [
    (False, []),
    (True, []),
]


def _login_if_needed(client, create_staff_user, is_logged_in, permissions):
    if is_logged_in:
        staff = create_staff_user(permissions=permissions)
        client.force_login(staff)


def _assert_access(response, is_logged_in, permissions, required_permission, url, get_login_url, success_status=200):
    if not is_logged_in:
        assert response.status_code == 302
        assert response.url == get_login_url(url)
    elif required_permission not in permissions:
        assert response.status_code == 403
    else:
        assert response.status_code == success_status


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["plans.view"])],
)
@pytest.mark.django_db
def test_plan_list__access(
    client,
    create_staff_user,
    create_plan,
    get_login_url,
    is_logged_in,
    permissions,
):
    create_plan()
    _login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:plan_list")
    response = client.get(url)
    _assert_access(response, is_logged_in, permissions, "plans.view", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["plans.create"])],
)
@pytest.mark.django_db
def test_plan_create__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    _login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:plan_create")
    response = client.get(url)
    _assert_access(response, is_logged_in, permissions, "plans.create", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["plans.edit"])],
)
@pytest.mark.django_db
def test_plan_update__access(
    client,
    create_staff_user,
    create_plan,
    get_login_url,
    is_logged_in,
    permissions,
):
    plan = create_plan()
    _login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:plan_update", kwargs={"pk": plan.pk})
    response = client.get(url)
    _assert_access(response, is_logged_in, permissions, "plans.edit", url, get_login_url)


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["plans.delete"])],
)
@pytest.mark.django_db
def test_plan_delete__access(
    client,
    create_staff_user,
    create_plan,
    get_login_url,
    is_logged_in,
    permissions,
):
    plan = create_plan()
    _login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:plan_delete", kwargs={"pk": plan.pk})
    response = client.post(url)
    _assert_access(
        response,
        is_logged_in,
        permissions,
        "plans.delete",
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and "plans.delete" in permissions:
        assert response.url == reverse("billing:plan_list")

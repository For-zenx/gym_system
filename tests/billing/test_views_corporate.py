import pytest
from django.urls import reverse

from apps.billing.models import CorporateGroup, Plan
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed


DELETE_GROUPS_PERMISSION = "corporate.delete_groups"


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, ["corporate.view"])],
)
@pytest.mark.django_db
def test_corporate_group_list__access(
    client,
    create_staff_user,
    get_login_url,
    is_logged_in,
    permissions,
):
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:corporate_group_list")
    response = client.get(url)
    assert_access(response, is_logged_in, permissions, "corporate.view", url, get_login_url)


@pytest.mark.django_db
def test_corporate_group_create__post_creates_group(
    client,
    create_staff_user,
    create_client,
    create_plan,
):
    subscriber = create_client()
    plan = create_plan(billing_type=Plan.BillingType.CORPORATE, max_members=10)
    staff = create_staff_user(permissions=["corporate.manage_groups"])
    client.force_login(staff)

    url = reverse("billing:corporate_group_create")
    response = client.post(
        url,
        {
            "subscriber_id": str(subscriber.pk),
            "plan_id": str(plan.pk),
        },
    )

    assert response.status_code == 302
    group = CorporateGroup.objects.get(subscriber=subscriber)
    assert group.plan_id == plan.pk
    assert group.status == CorporateGroup.Status.SUSPENDED
    assert reverse("billing:corporate_group_detail", kwargs={"pk": group.pk}) in response.url


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS
    + [
        (True, ["corporate.manage_groups"]),
        (True, ["corporate.remove_members"]),
        (True, [DELETE_GROUPS_PERMISSION]),
    ],
)
@pytest.mark.django_db
def test_corporate_group_dissolve__access(
    client,
    create_staff_user,
    create_corporate_group,
    get_login_url,
    is_logged_in,
    permissions,
):
    group = create_corporate_group()
    group_pk = group.pk
    login_if_needed(client, create_staff_user, is_logged_in, permissions)
    url = reverse("billing:corporate_group_dissolve", kwargs={"pk": group_pk})

    response = client.post(url)

    assert_access(
        response,
        is_logged_in,
        permissions,
        DELETE_GROUPS_PERMISSION,
        url,
        get_login_url,
        success_status=302,
    )
    if is_logged_in and DELETE_GROUPS_PERMISSION in permissions:
        assert not CorporateGroup.objects.filter(pk=group_pk).exists()
    else:
        assert CorporateGroup.objects.filter(pk=group_pk).exists()


@pytest.mark.parametrize(
    ("permissions", "shows_delete"),
    [
        (["corporate.view", "corporate.manage_groups"], False),
        (["corporate.view", "corporate.remove_members"], False),
        (["corporate.view", DELETE_GROUPS_PERMISSION], True),
    ],
)
@pytest.mark.django_db
def test_corporate_group_detail__destructive_buttons_require_permission(
    client,
    create_staff_user,
    create_corporate_group,
    permissions,
    shows_delete,
):
    group = create_corporate_group()
    staff = create_staff_user(permissions=permissions)
    client.force_login(staff)

    response = client.get(
        reverse("billing:corporate_group_detail", kwargs={"pk": group.pk})
    )

    assert response.status_code == 200
    content = response.content.decode("utf-8")
    assert ("Disolver" in content) is shows_delete
    assert ("Eliminar Grupo Permanente" in content) is shows_delete


@pytest.mark.django_db
def test_remove_member__subscriber_cannot_bypass_delete_permission(
    client,
    create_staff_user,
    create_corporate_group,
):
    group = create_corporate_group()
    staff = create_staff_user(permissions=["corporate.remove_members"])
    client.force_login(staff)

    response = client.post(
        reverse("billing:corporate_group_remove_member", kwargs={"pk": group.pk}),
        {"client_id": str(group.subscriber_id)},
    )

    assert response.status_code == 302
    group.refresh_from_db()
    assert group.status != CorporateGroup.Status.DISSOLVED

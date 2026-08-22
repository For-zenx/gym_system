import pytest
from django.urls import reverse

from apps.billing.models import CorporateGroup, Plan
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed


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

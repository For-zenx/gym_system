import pytest
from datetime import date, timedelta

from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.billing.corporate_services import (
    add_member_to_group,
    grant_corporate_admin_access,
    remove_member_from_group,
)
from apps.billing.models import ClientBillingEvent, CorporateGroup, Invoice, Membership, Plan
from tests import factories
from tests.helpers import ACCESS_PARAMS, assert_access, login_if_needed

CORP_ADMIN_PERMISSION = "corporate.grant_admin_access"


@pytest.mark.django_db
def test_grant_corporate_admin_access__cascade_to_active_members():
    plan = factories.create_plan(billing_type=Plan.BillingType.CORPORATE, max_members=10)
    subscriber = factories.create_client()
    member_a = factories.create_client()
    member_b = factories.create_client()
    group = factories.create_corporate_group(plan=plan, subscriber=subscriber)
    add_member_to_group(group, member_a)
    add_member_to_group(group, member_b)

    valid_until = date.today() + timedelta(days=30)
    staff = factories.create_staff_user(permissions=[CORP_ADMIN_PERMISSION])

    clients = grant_corporate_admin_access(group, valid_until, staff)

    assert len(clients) == 3
    for client in (subscriber, member_a, member_b):
        membership = Membership.objects.get(client=client, plan=plan)
        assert membership.fecha_fin == valid_until
        client.refresh_from_db()
        assert client.fixed_plan_id == plan.pk
        assert client.fecha_corte_dia == min(valid_until.day, 28)

    group.refresh_from_db()
    assert group.status == CorporateGroup.Status.ACTIVE
    assert group.fecha_corte_dia == min(valid_until.day, 28)
    assert not Invoice.objects.filter(corporate_group=group).exists()


@pytest.mark.django_db
def test_grant_corporate_admin_access__skips_removed_members():
    plan = factories.create_plan(billing_type=Plan.BillingType.CORPORATE, max_members=10)
    subscriber = factories.create_client()
    member = factories.create_client()
    removed = factories.create_client()
    group = factories.create_corporate_group(plan=plan, subscriber=subscriber)
    add_member_to_group(group, member)
    add_member_to_group(group, removed)
    remove_member_from_group(group, removed)

    valid_until = date.today() + timedelta(days=20)
    grant_corporate_admin_access(group, valid_until, None)

    assert Membership.objects.filter(client=removed, plan=plan).count() == 0
    assert Membership.objects.filter(client__in=[subscriber, member], plan=plan).count() == 2


@pytest.mark.django_db
def test_grant_corporate_admin_access__removes_flexible_membership():
    plan = factories.create_plan(billing_type=Plan.BillingType.CORPORATE, max_members=10)
    subscriber = factories.create_client()
    flex_plan = factories.create_plan(billing_type=Plan.BillingType.FLEXIBLE)
    factories.create_membership(client=subscriber, plan=flex_plan)
    group = factories.create_corporate_group(plan=plan, subscriber=subscriber)

    valid_until = date.today() + timedelta(days=15)
    grant_corporate_admin_access(group, valid_until, None)

    assert not Membership.objects.filter(client=subscriber, plan=flex_plan).exists()
    assert Membership.objects.filter(client=subscriber, plan=plan).exists()


@pytest.mark.django_db
def test_grant_corporate_admin_access__past_valid_until_keeps_group_active():
    plan = factories.create_plan(billing_type=Plan.BillingType.CORPORATE, max_members=10)
    subscriber = factories.create_client()
    group = factories.create_corporate_group(plan=plan, subscriber=subscriber)
    group.status = CorporateGroup.Status.ACTIVE
    group.save(update_fields=["status"])

    valid_until = date.today() - timedelta(days=3)
    grant_corporate_admin_access(group, valid_until, None)

    membership = Membership.objects.get(client=subscriber, plan=plan)
    assert membership.fecha_fin == valid_until
    assert membership.fecha_inicio == valid_until
    group.refresh_from_db()
    assert group.status == CorporateGroup.Status.ACTIVE


@pytest.mark.django_db
def test_grant_corporate_admin_access__activates_suspended_group():
    plan = factories.create_plan(billing_type=Plan.BillingType.CORPORATE, max_members=10)
    subscriber = factories.create_client()
    group = factories.create_corporate_group(plan=plan, subscriber=subscriber)
    assert group.status == CorporateGroup.Status.SUSPENDED

    grant_corporate_admin_access(group, date.today() + timedelta(days=10), None)

    group.refresh_from_db()
    assert group.status == CorporateGroup.Status.ACTIVE


@pytest.mark.django_db
def test_grant_corporate_admin_access__dissolved_group_rejected():
    plan = factories.create_plan(billing_type=Plan.BillingType.CORPORATE, max_members=10)
    subscriber = factories.create_client()
    group = factories.create_corporate_group(plan=plan, subscriber=subscriber)
    group.status = CorporateGroup.Status.DISSOLVED
    group.save(update_fields=["status"])

    with pytest.raises(ValidationError):
        grant_corporate_admin_access(group, date.today() + timedelta(days=5), None)


@pytest.mark.django_db
def test_grant_corporate_admin_access__audits_each_member():
    plan = factories.create_plan(billing_type=Plan.BillingType.CORPORATE, max_members=10)
    subscriber = factories.create_client()
    group = factories.create_corporate_group(plan=plan, subscriber=subscriber)

    grant_corporate_admin_access(group, date.today() + timedelta(days=7), None)

    event = ClientBillingEvent.objects.filter(
        client=subscriber,
        event_type=ClientBillingEvent.EventType.ADMIN_ACCESS_GRANTED,
    ).latest("created_at")
    assert event.payload.get("corporate") is True
    assert event.payload.get("group_id") == group.pk


@pytest.mark.parametrize(
    ("is_logged_in", "permissions"),
    ACCESS_PARAMS + [(True, [CORP_ADMIN_PERMISSION])],
)
@pytest.mark.django_db
def test_corporate_group_grant_admin_access_view__access(
    client,
    create_staff_user,
    create_corporate_group,
    get_login_url,
    is_logged_in,
    permissions,
):
    group = create_corporate_group()
    login_if_needed(client, create_staff_user, is_logged_in, permissions)

    url = reverse("billing:corporate_group_grant_admin_access", kwargs={"pk": group.pk})
    response = client.post(
        url,
        {
            "confirm_corporate_admin_access": "1",
            "valid_until": (date.today() + timedelta(days=14)).isoformat(),
        },
    )
    assert_access(
        response,
        is_logged_in,
        permissions,
        CORP_ADMIN_PERMISSION,
        url,
        get_login_url,
        success_status=302,
    )

from datetime import date, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.billing.models import CorporateGroup, Membership, Plan
from apps.billing.services import preview_membership_period, register_checkout
from tests import factories


@pytest.mark.django_db
def test_register_checkout__sub_affiliate_pays_corporate_group(create_corporate_group):
    group = create_corporate_group()
    sub = factories.create_client(nombre="Sub Afiliado")
    group.members.create(client=sub, is_active=True)
    group.fecha_corte_dia = 31
    group.save(update_fields=["fecha_corte_dia"])
    factories.create_exchange_rate()

    result = register_checkout(
        sub,
        plan=group.plan,
        payment_cut_day=31,
        payment_method="ZELLE",
    )

    group.refresh_from_db()
    assert group.status == CorporateGroup.Status.ACTIVE
    assert result.invoice.client_id == sub.pk
    assert result.invoice.corporate_group_id == group.pk
    assert result.membership.client_id == sub.pk

    for client in (group.subscriber, sub):
        assert client.memberships.filter(plan=group.plan).exists()


@pytest.mark.django_db
def test_register_checkout__owner_pays_corporate_group_regression(create_corporate_group):
    group = create_corporate_group()
    factories.create_exchange_rate()

    result = register_checkout(
        group.subscriber,
        plan=group.plan,
        payment_cut_day=31,
        payment_method="MOBILE",
    )

    assert result.invoice.client_id == group.subscriber_id
    assert result.invoice.corporate_group_id == group.pk


@pytest.mark.django_db
def test_register_checkout__non_member_cannot_pay_corporate_plan(create_corporate_group):
    group = create_corporate_group()
    outsider = factories.create_client(nombre="Externo")
    factories.create_exchange_rate()

    with pytest.raises(ValidationError, match="miembro activo"):
        register_checkout(
            outsider,
            plan=group.plan,
            payment_cut_day=31,
            payment_method="ZELLE",
        )


@pytest.mark.django_db
def test_charge_checkout_get__sub_affiliate_sees_corporate_plan(
    client,
    create_staff_user,
    create_corporate_group,
):
    group = create_corporate_group()
    sub = factories.create_client(nombre="Sub Afiliado")
    group.members.create(client=sub, is_active=True)
    staff = create_staff_user(permissions=["billing.charge"])
    client.force_login(staff)

    url = reverse("billing:charge_checkout", kwargs={"codigo_afiliado": sub.codigo_afiliado})
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert group.plan.nombre in content
    assert "plan grupal" in content.lower() or "grupo" in content.lower()


@pytest.mark.django_db
def test_is_corporate_group_member_helpers(create_corporate_group):
    from apps.billing.corporate_services import (
        get_corporate_checkout_context,
        is_corporate_group_member,
    )

    group = create_corporate_group()
    sub = factories.create_client(nombre="Sub")
    group.members.create(client=sub, is_active=True)
    outsider = factories.create_client(nombre="Externo")

    assert is_corporate_group_member(group.subscriber, group) is True
    assert is_corporate_group_member(sub, group) is True
    assert is_corporate_group_member(outsider, group) is False

    sub_ctx = get_corporate_checkout_context(sub)
    assert sub_ctx["can_pay_corporate"] is True
    assert sub_ctx["plan"].pk == group.plan_id

    outsider_ctx = get_corporate_checkout_context(outsider)
    assert outsider_ctx["can_pay_corporate"] is False


@pytest.mark.django_db
def test_corporate_prepaid_advances_to_next_period(create_corporate_group):
    group = create_corporate_group()
    group.fecha_corte_dia = 31
    group.save(update_fields=["fecha_corte_dia"])
    factories.create_exchange_rate()
    today = date.today()
    covered_until = today + timedelta(days=30)
    Membership.objects.create(
        client=group.subscriber,
        plan=group.plan,
        fecha_inicio=today,
        fecha_fin=covered_until,
    )

    preview = preview_membership_period(
        group.subscriber,
        group.plan,
        cut_day_override=31,
        corp_group=group,
    )
    assert preview["fecha_fin"] > covered_until

    result = register_checkout(
        group.subscriber,
        plan=group.plan,
        payment_cut_day=31,
        payment_method="ZELLE",
    )
    assert result.membership.fecha_fin > covered_until
    assert result.membership.fecha_inicio >= covered_until

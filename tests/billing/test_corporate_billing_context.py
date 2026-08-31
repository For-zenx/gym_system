import datetime

import pytest

from apps.billing.corporate_services import (
    get_corporate_group_billing_context,
    register_corporate_checkout,
)
from apps.billing.models import CorporateGroup, Membership, Plan
from tests import factories


@pytest.mark.django_db
def test_corporate_billing_context__next_cut_uses_paid_period_end(create_corporate_group):
    group = create_corporate_group()
    group.fecha_corte_dia = 31
    group.save(update_fields=["fecha_corte_dia"])

    payment_day = datetime.date(2026, 8, 31)
    membership = Membership.objects.create(
        client=group.subscriber,
        plan=group.plan,
        fecha_inicio=payment_day,
        fecha_fin=datetime.date(2026, 9, 30),
    )

    ctx = get_corporate_group_billing_context(group)

    assert ctx["is_active"] is True
    assert ctx["covered_until_display"] == "30/09/2026"
    assert ctx["next_cut_display"] == "30/09/2026"
    assert ctx["active_membership"].pk == membership.pk


@pytest.mark.django_db
def test_register_corporate_checkout__creates_memberships_for_all_members(create_corporate_group):
    group = create_corporate_group()
    member_client = factories.create_client(nombre="Sub Afiliado")
    group.members.create(client=member_client, is_active=True)
    group.subscriber.fecha_corte_dia = 31
    group.subscriber.save(update_fields=["fecha_corte_dia"])
    factories.create_exchange_rate()

    invoice = register_corporate_checkout(
        group=group,
        payer=group.subscriber,
        payment_cut_day=31,
        payment_method="ZELLE",
    )

    group.refresh_from_db()
    assert group.status == CorporateGroup.Status.ACTIVE
    assert invoice.corporate_group_id == group.pk

    for client in (group.subscriber, member_client):
        active = client.memberships.filter(
            plan=group.plan,
            fecha_fin__gte=invoice.membership.fecha_fin,
        ).exists()
        assert active, "Expected corporate membership for {}".format(client.nombre)

    ctx = get_corporate_group_billing_context(group)
    assert ctx["is_active"] is True
    assert ctx["next_cut_display"] == ctx["covered_until_display"]

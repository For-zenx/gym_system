from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

from .cycle import billing_period_start, subscription_period_bounds
from .models import Membership, Invoice, ExchangeRate, Plan


def register_membership_renewal(client, plan, nro_control=None, monto_ves=None):
    """
    Registra administrativamente la renovación.
    Si monto_ves es None, lo calcula usando la tasa más reciente.
    """
    if monto_ves is None:
        tasa = ExchangeRate.get_latest()
        if not tasa:
            raise ValidationError("No hay una tasa de cambio registrada en el sistema.")
        monto_ves = plan.precio_usd * tasa.tasa_ves

    with transaction.atomic():
        hoy = timezone.localdate()

        if plan.is_fixed:
            membership = _create_fixed_membership(client, plan, hoy)
        else:
            membership = _create_flexible_membership(client, plan, hoy)

        invoice = Invoice(
            client=client,
            membership=membership,
            plan_snapshot=plan.nombre,
            monto_total=monto_ves,
            nro_control=nro_control or "PENDING",
        )
        invoice.set_client_snapshots(client)
        invoice.save()

        if not nro_control:
            invoice.nro_control = f"F-{timezone.now().strftime('%Y%m%d')}-{invoice.pk:05d}"
            invoice.save(update_fields=['nro_control'])

        return membership, invoice


def _create_flexible_membership(client, plan, hoy):
    return Membership.objects.create(
        client=client,
        plan=plan,
        fecha_inicio=hoy,
    )


def _create_fixed_membership(client, plan, hoy):
    cut_day = client.fecha_corte_dia
    if cut_day is None:
        cut_day = hoy.day
        client.fecha_corte_dia = cut_day
        client.save(update_fields=['fecha_corte_dia'])

    latest_fixed = (
        client.memberships.filter(plan__billing_type=Plan.BillingType.FIXED)
        .order_by('-fecha_fin')
        .first()
    )

    if latest_fixed and latest_fixed.fecha_fin >= hoy:
        period_start = latest_fixed.fecha_fin + timedelta(days=1)
    else:
        period_start = billing_period_start(cut_day, hoy)

    fecha_inicio, fecha_fin = subscription_period_bounds(cut_day, period_start)

    return Membership.objects.create(
        client=client,
        plan=plan,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta

from .cycle import (
    billing_period_start,
    subscription_period_bounds,
    is_subscription_suspended,
    unpaid_fixed_periods,
    days_since_last_unpaid_cut,
)
from .models import (
    Membership,
    Invoice,
    ExchangeRate,
    Plan,
    BillingSettings,
    ClientBillingEvent,
)


@dataclass
class RenewalResult:
    membership: Membership
    invoice: Invoice
    warnings: list = field(default_factory=list)
    was_reactivation: bool = False
    late_fee_applied: bool = False

    def __iter__(self):
        yield self.membership
        yield self.invoice


def log_billing_event(client, event_type, payload=None, motivo="", user=None):
    return ClientBillingEvent.objects.create(
        client=client,
        event_type=event_type,
        payload=payload or {},
        motivo=motivo,
        created_by=user,
    )


def change_client_cut_date(client, new_day, motivo, user=None):
    if not isinstance(new_day, int) or new_day < 1 or new_day > 31:
        raise ValidationError("La fecha de corte debe ser un día entre 1 y 31.")

    motivo = (motivo or "").strip()
    if not motivo:
        raise ValidationError("Debe indicar un motivo para cambiar la fecha de corte.")

    old_day = client.fecha_corte_dia
    client.fecha_corte_dia = new_day
    client.save(update_fields=["fecha_corte_dia"])

    log_billing_event(
        client,
        ClientBillingEvent.EventType.CUT_DATE_CHANGED,
        payload={"old_day": old_day, "new_day": new_day},
        motivo=motivo,
        user=user,
    )
    return client


def get_client_billing_context(client):
    billing_settings = BillingSettings.get_settings()
    suspended = is_subscription_suspended(client)
    unpaid = unpaid_fixed_periods(client)

    return {
        "fecha_corte_dia": client.fecha_corte_dia,
        "fixed_status": client.fixed_subscription_status,
        "unpaid_periods": unpaid,
        "unpaid_period_count": len(unpaid),
        "days_since_last_unpaid_cut": days_since_last_unpaid_cut(client),
        "suggested_late_fee_usd": billing_settings.multa_monto_usd,
        "default_apply_late_fee": suspended,
        "warnings_on_flexible_purchase": suspended,
    }


def register_membership_renewal(
    client,
    plan,
    nro_control=None,
    monto_ves=None,
    apply_late_fee=False,
    late_fee_usd=None,
    acting_user=None,
):
    """
    Registra administrativamente la renovación.
    Si monto_ves es None, lo calcula usando la tasa más reciente.
    Retorna RenewalResult (compatible con desempaquetado membership, invoice).
    """
    tasa = ExchangeRate.get_latest()
    if not tasa:
        raise ValidationError("No hay una tasa de cambio registrada en el sistema.")

    if monto_ves is None:
        monto_ves = plan.precio_usd * tasa.tasa_ves

    with transaction.atomic():
        hoy = timezone.localdate()
        was_suspended = is_subscription_suspended(client, hoy)
        warnings = []

        if plan.is_flexible and was_suspended:
            warnings.append("flexible_on_suspended_subscription")

        if plan.is_fixed:
            membership = _create_fixed_membership(client, plan, hoy)
        else:
            membership = _create_flexible_membership(client, plan, hoy)

        multa_usd = Decimal("0.00")
        multa_ves = Decimal("0.00")
        late_fee_applied = False
        was_reactivation = False

        if plan.is_fixed and was_suspended:
            was_reactivation = True
            if apply_late_fee:
                multa_usd = (
                    Decimal(str(late_fee_usd))
                    if late_fee_usd is not None
                    else BillingSettings.get_settings().multa_monto_usd
                )
                if multa_usd > 0:
                    multa_ves = multa_usd * tasa.tasa_ves
                    late_fee_applied = True

        invoice = Invoice(
            client=client,
            membership=membership,
            plan_snapshot=plan.nombre,
            multa_usd=multa_usd,
            multa_ves=multa_ves,
            monto_total=monto_ves + multa_ves,
            nro_control=nro_control or "PENDING",
        )
        invoice.set_client_snapshots(client)
        invoice.save()

        if not nro_control:
            invoice.nro_control = f"F-{timezone.now().strftime('%Y%m%d')}-{invoice.pk:05d}"
            invoice.save(update_fields=["nro_control"])

        if was_reactivation:
            log_billing_event(
                client,
                ClientBillingEvent.EventType.SUBSCRIPTION_REACTIVATED,
                payload={
                    "membership_id": membership.pk,
                    "invoice_id": invoice.pk,
                    "period_start": membership.fecha_inicio.isoformat(),
                    "period_end": membership.fecha_fin.isoformat(),
                },
                user=acting_user,
            )
            if late_fee_applied:
                log_billing_event(
                    client,
                    ClientBillingEvent.EventType.LATE_FEE_APPLIED,
                    payload={
                        "invoice_id": invoice.pk,
                        "multa_usd": str(multa_usd),
                        "multa_ves": str(multa_ves),
                    },
                    user=acting_user,
                )
            else:
                log_billing_event(
                    client,
                    ClientBillingEvent.EventType.LATE_FEE_WAIVED,
                    payload={"invoice_id": invoice.pk},
                    user=acting_user,
                )

        return RenewalResult(
            membership=membership,
            invoice=invoice,
            warnings=warnings,
            was_reactivation=was_reactivation,
            late_fee_applied=late_fee_applied,
        )


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
        client.save(update_fields=["fecha_corte_dia"])

    latest_fixed = (
        client.memberships.filter(plan__billing_type=Plan.BillingType.FIXED)
        .order_by("-fecha_fin")
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

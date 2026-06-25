import datetime
import logging

from apps.billing.cycle import (
    days_until_next_cut_date,
    is_subscription_suspended,
    next_cut_date,
    unpaid_fixed_periods,
)
from apps.billing.services import get_profile_subscription_summary
from apps.clients.services import get_active_guest_pass

from .hardware import open_turnstile
from .models import AccessLog

logger = logging.getLogger(__name__)


def _evaluate_guest_access(client, today=None):
    if today is None:
        today = datetime.date.today()

    active_pass = get_active_guest_pass(client, on_date=today)
    if active_pass:
        if active_pass.sponsor_id:
            return True, "Invitado — acompaña a {}".format(active_pass.sponsor.nombre)
        return True, "Invitado — pase vigente"

    latest_pass = (
        client.guest_passes.select_related("sponsor")
        .order_by("-valid_until", "-created_at")
        .first()
    )
    if not latest_pass:
        return False, "Sin autorización de invitado"

    if latest_pass.revoked_at:
        return False, "Pase de invitado revocado"

    if latest_pass.valid_until < today:
        return False, "Pase de invitado vencido el {}".format(
            latest_pass.valid_until.strftime("%d/%m/%Y")
        )

    if latest_pass.valid_from > today:
        return False, "Pase de invitado aún no vigente"

    return False, "Pase de invitado no vigente"


def evaluate_access_integrity(client):
    if client.is_guest:
        return _evaluate_guest_access(client)

    if not client.access_requires_membership:
        return True, "Acceso personal"

    active_memberships = client.active_memberships

    if not active_memberships.exists():
        if is_subscription_suspended(client):
            motivo = f"Suscripción suspendida (corte: día {client.fecha_corte_dia})"
        elif client.memberships.exists():
            latest = client.memberships.order_by('-fecha_fin').first()
            motivo = f"Membresía vencida el {latest.fecha_fin.strftime('%d/%m/%Y')}"
        else:
            motivo = "Sin membresía registrada"
        return False, motivo

    from django.utils import timezone

    current_time = timezone.localtime().time()

    for membership in active_memberships:
        if membership.is_valid_now(current_time):
            return True, "Acceso concedido"

    return False, "Fuera de horario permitido"


def check_access_integrity(client):
    granted, motivo = evaluate_access_integrity(client)
    if not granted:
        AccessLog.objects.create(
            client=client,
            resultado=granted,
            motivo=motivo,
        )
        return granted, motivo

    AccessLog.objects.create(
        client=client,
        resultado=True,
        motivo=motivo,
    )
    return granted, motivo


def _suspended_since_display(client, today=None):
    if today is None:
        today = datetime.date.today()
    unpaid = unpaid_fixed_periods(client, today)
    if unpaid:
        return unpaid[0][0].strftime("%d/%m/%Y")

    from apps.billing.models import Plan

    latest_fixed = (
        client.memberships.filter(
            plan__billing_type=Plan.BillingType.FIXED,
            fecha_fin__lt=today,
        )
        .order_by("-fecha_fin")
        .first()
    )
    if latest_fixed:
        return (latest_fixed.fecha_fin + datetime.timedelta(days=1)).strftime("%d/%m/%Y")
    return None


def _classify_denied_variant(client, detail):
    detail_lower = (detail or "").lower()
    if client.is_guest:
        if "vencido" in detail_lower:
            return "denied_other"
        if "revocado" in detail_lower:
            return "denied_other"
    if "fuera de horario" in detail_lower:
        return "denied_schedule"
    if is_subscription_suspended(client) or "suspendida" in detail_lower:
        return "denied_suspended"
    return "denied_other"


def _tablet_covered_until_display(client):
    summary = get_profile_subscription_summary(client)
    fixed = summary.get("fixed_line") or {}
    if fixed.get("kind") == "active":
        return fixed.get("covered_until_display")
    flex = summary.get("flexible_line")
    if flex:
        return flex.get("until_display")
    return None


def pulse_turnstile_if_granted(granted):
    if not granted:
        return
    result = open_turnstile()
    if not result.success:
        logger.error("Fallo al abrir torniquete tras acceso concedido: %s", result.message)


def build_tablet_access_payload(client, granted, detail, membership_data=None):
    today = datetime.date.today()
    next_cut = next_cut_date(client, today)
    days_until_cut = days_until_next_cut_date(client, today)
    active_guest_pass = get_active_guest_pass(client, on_date=today) if client.is_guest else None

    payload = {
        "name": client.nombre,
        "detail": detail,
        "cut_day": client.fecha_corte_dia,
        "days_until_cut": days_until_cut,
        "next_cut_display": next_cut.strftime("%d/%m/%Y") if next_cut else None,
        "days_membership_left": None,
        "plan_name": None,
        "suspended_since_display": None,
        "covered_until_display": None,
        "sponsor_name": None,
        "pass_until_display": None,
    }

    if membership_data:
        payload["days_membership_left"] = max(membership_data.get("days_left", 0), 0)
        payload["plan_name"] = membership_data.get("plan_name")

    if active_guest_pass:
        if active_guest_pass.sponsor_id:
            payload["sponsor_name"] = active_guest_pass.sponsor.nombre
        payload["pass_until_display"] = active_guest_pass.valid_until.strftime("%d/%m/%Y")

    if granted:
        payload["status"] = "GRANTED"
        if client.is_guest:
            payload["variant"] = "granted_guest"
        elif client.access_requires_membership:
            payload["variant"] = "granted"
            payload["covered_until_display"] = _tablet_covered_until_display(client)
        else:
            payload["variant"] = "granted_staff"
        return payload

    payload["status"] = "DENIED"
    payload["variant"] = _classify_denied_variant(client, detail)
    if payload["variant"] == "denied_suspended":
        payload["suspended_since_display"] = _suspended_since_display(client, today)
    return payload

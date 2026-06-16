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
    InvoiceLine,
    ExchangeRate,
    Plan,
    SaleItem,
    BillingSettings,
    ClientBillingEvent,
    ClientServicePeriod,
)

CUT_DATE_CHANGE_REASONS = (
    "Reingreso tras ausencia prolongada",
    "Ajuste acordado con el afiliado",
    "Corrección de error en caja",
    "Cambio de quincena de pago",
)

CUT_DATE_MOTIVO_OTHER = "__other__"


@dataclass
class RenewalResult:
    membership: Membership = None
    invoice: Invoice = None
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
        "warnings_on_flexible_purchase": suspended and bool(client.fecha_corte_dia),
    }


def _has_fixed_coverage(client, today):
    return client.memberships.filter(
        plan__billing_type=Plan.BillingType.FIXED,
        fecha_fin__gte=today,
    ).exists()


def _has_flexible_active_or_future(client, today):
    return client.memberships.filter(
        plan__billing_type=Plan.BillingType.FLEXIBLE,
        fecha_fin__gte=today,
    ).exists()


def validate_plan_purchase(client, plan, today=None):
    if today is None:
        today = timezone.localdate()

    if plan.is_flexible:
        if _has_flexible_active_or_future(client, today):
            raise ValidationError(
                "Ya existe un pase flexible vigente. Espere a que venza antes de vender otro."
            )
        suspended = is_subscription_suspended(client, today)
        if _has_fixed_coverage(client, today) and not suspended:
            raise ValidationError(
                "No se puede vender un pase flexible mientras la suscripción mensual esté al día."
            )
    return True


def get_chargeable_plans(client, plans, today=None):
    if today is None:
        today = timezone.localdate()
    chargeable = []
    for plan in plans:
        try:
            validate_plan_purchase(client, plan, today)
            chargeable.append(plan)
        except ValidationError:
            continue
    return chargeable


def _finalize_fixed_group(group, today):
    if group["start"] <= today <= group["end"]:
        status = "active"
    elif group["start"] > today:
        status = "queued"
    else:
        status = "expired"

    prepaid_count = 0
    if status == "active":
        prepaid_count = max(0, group["period_count"] - 1)
    elif status == "queued":
        prepaid_count = group["period_count"]

    group["status"] = status
    group["prepaid_count"] = prepaid_count
    group["start_display"] = group["start"].strftime("%d/%m/%Y")
    group["end_display"] = group["end"].strftime("%d/%m/%Y")
    return group


def group_consecutive_fixed_memberships(memberships, today=None):
    if today is None:
        today = timezone.localdate()

    fixed = sorted(
        (m for m in memberships if m.plan.billing_type == Plan.BillingType.FIXED),
        key=lambda m: m.fecha_inicio,
    )

    groups = []
    current = None
    for mem in fixed:
        if current is None:
            current = {
                "plan_name": mem.plan.nombre,
                "plan_id": mem.plan_id,
                "start": mem.fecha_inicio,
                "end": mem.fecha_fin,
                "period_count": 1,
            }
            continue

        if (
            mem.plan_id == current["plan_id"]
            and mem.fecha_inicio == current["end"] + timedelta(days=1)
        ):
            current["end"] = mem.fecha_fin
            current["period_count"] += 1
        else:
            groups.append(_finalize_fixed_group(current, today))
            current = {
                "plan_name": mem.plan.nombre,
                "plan_id": mem.plan_id,
                "start": mem.fecha_inicio,
                "end": mem.fecha_fin,
                "period_count": 1,
            }

    if current:
        groups.append(_finalize_fixed_group(current, today))
    return groups


def get_profile_subscription_summary(client):
    today = timezone.localdate()
    memberships = list(client.memberships.select_related("plan").order_by("fecha_inicio"))

    active_memberships = [
        m for m in memberships if m.fecha_inicio <= today <= m.fecha_fin
    ]
    has_access = bool(active_memberships)

    fixed_groups = group_consecutive_fixed_memberships(memberships, today)
    current_fixed_group = None
    for group in fixed_groups:
        if group["status"] in ("active", "queued") and group["end"] >= today:
            current_fixed_group = group
            break

    fixed_status = client.fixed_subscription_status
    fixed_line = {"kind": "none"}
    if fixed_status == "SUSPENDED" and client.fecha_corte_dia:
        expired_fixed = [
            m for m in memberships
            if m.plan.billing_type == Plan.BillingType.FIXED and m.fecha_fin < today
        ]
        last_paid_end = (
            max(m.fecha_fin for m in expired_fixed) if expired_fixed else None
        )
        fixed_line = {
            "kind": "suspended",
            "unpaid_count": len(unpaid_fixed_periods(client, today)),
            "last_paid_end": last_paid_end,
            "last_paid_end_display": (
                last_paid_end.strftime("%d/%m/%Y") if last_paid_end else None
            ),
        }
    elif current_fixed_group:
        fixed_line = {
            "kind": "active",
            "plan_name": current_fixed_group["plan_name"],
            "covered_until": current_fixed_group["end"],
            "covered_until_display": current_fixed_group["end_display"],
            "prepaid_count": current_fixed_group["prepaid_count"],
            "period_count": current_fixed_group["period_count"],
        }

    flexible_line = None
    flexible_active = [
        m for m in active_memberships
        if m.plan.billing_type == Plan.BillingType.FLEXIBLE
    ]
    if flexible_active:
        mem = flexible_active[0]
        flexible_line = {
            "plan_name": mem.plan.nombre,
            "until_display": mem.fecha_fin.strftime("%d/%m/%Y"),
        }

    if client.fecha_corte_dia:
        cut_date_display = "Día {} de cada mes".format(client.fecha_corte_dia)
    else:
        cut_date_display = "Sin asignar"

    next_charge_hint = None
    if current_fixed_group:
        next_start = current_fixed_group["end"] + timedelta(days=1)
        next_charge_hint = next_start.strftime("%d/%m/%Y")

    return {
        "has_access": has_access,
        "cut_date_display": cut_date_display,
        "fixed_line": fixed_line,
        "flexible_line": flexible_line,
        "fixed_groups_detail": fixed_groups,
        "next_charge_hint": next_charge_hint,
        "show_unpaid_detail": fixed_status == "SUSPENDED",
    }


def get_membership_feed_lines(client):
    """Líneas estructuradas para el bloque de membresía en inicio (feed en vivo)."""
    summary = get_profile_subscription_summary(client)
    lines = []

    fixed = summary.get("fixed_line") or {}
    kind = fixed.get("kind")
    if kind == "active":
        secondary = None
        prepaid = fixed.get("prepaid_count") or 0
        if prepaid > 0:
            mes_word = "mes" if prepaid == 1 else "meses"
            pag_word = "pagado" if prepaid == 1 else "pagados"
            secondary = "{} {} {} por adelantado".format(prepaid, mes_word, pag_word)
        lines.append(
            {
                "status": "active",
                "title": "Suscripción mensual",
                "primary": "Al día hasta {}".format(fixed["covered_until_display"]),
                "secondary": secondary,
            }
        )
    elif kind == "suspended":
        parts = ["Suspendida"]
        unpaid = fixed.get("unpaid_count") or 0
        if unpaid > 0:
            period_word = "periodo" if unpaid == 1 else "periodos"
            imp_word = "impago" if unpaid == 1 else "impagos"
            parts.append("{} {} {}".format(unpaid, period_word, imp_word))
        secondary = None
        if fixed.get("last_paid_end_display"):
            secondary = "Último periodo pagado hasta {}".format(
                fixed["last_paid_end_display"]
            )
        lines.append(
            {
                "status": "suspended",
                "title": "Suscripción mensual",
                "primary": " · ".join(parts),
                "secondary": secondary,
            }
        )
    else:
        lines.append(
            {
                "status": "none",
                "title": "Suscripción mensual",
                "primary": "Sin suscripción mensual",
                "secondary": None,
            }
        )

    flex = summary.get("flexible_line")
    if flex:
        lines.append(
            {
                "status": "flexible",
                "title": "Pase flexible",
                "primary": "{} hasta {}".format(
                    flex["plan_name"],
                    flex["until_display"],
                ),
                "secondary": None,
            }
        )

    if not summary.get("has_access") and len(lines) == 1 and lines[0]["status"] == "none":
        return [
            {
                "status": "empty",
                "title": "Sin plan activo",
                "primary": None,
                "secondary": None,
            }
        ]

    return lines


def get_membership_status_display(client):
    """Texto plano (respaldo); preferir get_membership_feed_lines + plantilla."""
    parts = []
    for line in get_membership_feed_lines(client):
        if line["status"] == "empty":
            return line["title"]
        chunk = line["title"]
        if line.get("primary"):
            chunk += ": " + line["primary"]
        if line.get("secondary"):
            chunk += " (" + line["secondary"] + ")"
        parts.append(chunk)
    return " · ".join(parts) if parts else "Sin plan activo"


def preview_membership_period(client, plan, cut_day_override=None):
    hoy = timezone.localdate()
    if plan.is_flexible:
        return {
            "fecha_inicio": hoy,
            "fecha_fin": hoy + timedelta(days=plan.dias_duracion),
            "assigns_cut_date": False,
        }

    if cut_day_override is not None:
        cut_day = cut_day_override
    else:
        cut_day = client.fecha_corte_dia or hoy.day

    _, period_start, _ = _resolve_fixed_period(client, hoy, cut_day=cut_day)
    fecha_inicio, fecha_fin = subscription_period_bounds(cut_day, period_start)
    return {
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "assigns_cut_date": True,
    }


def parse_payment_cut_day_from_post(post):
    raw = (post.get("payment_cut_day") or post.get("cut_day") or "").strip()
    if not raw:
        return None
    try:
        day = int(raw)
    except (ValueError, TypeError):
        raise ValidationError("El día de corte debe ser un número entre 1 y 31.")
    if day < 1 or day > 31:
        raise ValidationError("El día de corte debe estar entre 1 y 31.")
    return day


def resolve_cut_date_motivo(post, prefix=""):
    preset = (post.get("{0}motivo_preset".format(prefix)) or "").strip()
    custom = (post.get("{0}motivo_custom".format(prefix)) or "").strip()

    if preset == CUT_DATE_MOTIVO_OTHER:
        if not custom:
            raise ValidationError("Debe describir el motivo del cambio.")
        return custom
    if not preset:
        raise ValidationError("Debe seleccionar un motivo.")
    return preset


def parse_payment_cut_from_post(post):
    cut_day = parse_payment_cut_day_from_post(post)
    editing = post.get("payment_cut_editing") == "1"
    initial_raw = (post.get("payment_cut_initial") or "").strip()

    initial_day = None
    if initial_raw:
        try:
            initial_day = int(initial_raw)
        except (ValueError, TypeError):
            raise ValidationError("El día de corte inicial no es válido.")

    motivo = ""
    if editing and initial_day is not None and cut_day != initial_day:
        motivo = resolve_cut_date_motivo(post, prefix="payment_cut_")

    return cut_day, motivo


def apply_cut_day_from_payment(client, cut_day, user=None, motivo=""):
    if not isinstance(cut_day, int) or cut_day < 1 or cut_day > 31:
        raise ValidationError("El día de corte debe estar entre 1 y 31.")

    old_day = client.fecha_corte_dia
    if old_day == cut_day:
        return client

    client.fecha_corte_dia = cut_day
    client.save(update_fields=["fecha_corte_dia"])

    if motivo:
        event_motivo = motivo
    elif old_day is None:
        event_motivo = "Asignado en cobro"
    else:
        event_motivo = "Actualizado en cobro"

    log_billing_event(
        client,
        ClientBillingEvent.EventType.CUT_DATE_CHANGED,
        payload={"old_day": old_day, "new_day": cut_day, "source": "payment"},
        motivo=event_motivo,
        user=user,
    )
    return client


def parse_late_fee_from_post(post):
    apply_late_fee = post.get("apply_late_fee") == "on"
    late_fee_usd = None
    raw = (post.get("late_fee_usd") or "").strip().replace(",", ".")
    if raw:
        late_fee_usd = Decimal(raw)
    return apply_late_fee, late_fee_usd


def parse_product_lines_from_post(post):
    lines = []
    for raw_id in post.getlist("product_ids"):
        try:
            item_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        qty_raw = (post.get("product_qty_{}".format(item_id)) or "1").strip()
        try:
            qty = int(qty_raw)
        except (TypeError, ValueError):
            qty = 0
        if qty > 0:
            lines.append(
                {
                    "item_id": item_id,
                    "qty": qty,
                    "locker_id": (post.get("locker_id_{}".format(item_id)) or "").strip(),
                    "locker_start": (post.get("locker_start_{}".format(item_id)) or "").strip(),
                    "locker_end": (post.get("locker_end_{}".format(item_id)) or "").strip(),
                }
            )
    return lines


def _normalize_product_line(product_line):
    if isinstance(product_line, dict):
        return product_line
    item_id, qty = product_line
    return {
        "item_id": item_id,
        "qty": qty,
        "locker_id": "",
        "locker_start": "",
        "locker_end": "",
    }


def _validate_checkout_product_lines(product_lines, plan):
    for product_line in product_lines:
        product_line = _normalize_product_line(product_line)
        sale_item = SaleItem.objects.filter(pk=product_line["item_id"], is_active=True).first()
        if sale_item and sale_item.is_plan_linked_service and not plan:
            raise ValidationError(
                "Los servicios requieren seleccionar un plan en el mismo cobro."
            )


def expire_overdue_service_periods():
    today = timezone.localdate()
    ClientServicePeriod.objects.filter(
        status=ClientServicePeriod.Status.ACTIVE,
        end_date__lt=today,
    ).update(status=ClientServicePeriod.Status.EXPIRED)


def validate_service_period_available(client, sale_item):
    expire_overdue_service_periods()
    if ClientServicePeriod.objects.filter(
        client=client,
        sale_item=sale_item,
        status=ClientServicePeriod.Status.ACTIVE,
    ).exists():
        raise ValidationError(
            "Este afiliado ya tiene el servicio «{}» activo.".format(sale_item.name)
        )


@transaction.atomic
def create_service_period(
    client,
    sale_item,
    membership,
    invoice_line=None,
    start_date=None,
    end_date=None,
    user=None,
):
    validate_service_period_available(client, sale_item)
    if start_date is None:
        start_date = membership.fecha_inicio
    if end_date is None:
        end_date = membership.fecha_fin
    return ClientServicePeriod.objects.create(
        client=client,
        sale_item=sale_item,
        membership=membership,
        invoice_line=invoice_line,
        start_date=start_date,
        end_date=end_date,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )


def get_active_service_periods_for_client(client):
    expire_overdue_service_periods()
    today = timezone.localdate()
    return (
        ClientServicePeriod.objects.filter(
            client=client,
            status=ClientServicePeriod.Status.ACTIVE,
            end_date__gte=today,
        )
        .select_related("sale_item", "membership")
        .order_by("end_date", "id")
    )


def get_recent_service_periods_for_client(client, limit=5):
    return (
        ClientServicePeriod.objects.filter(client=client)
        .select_related("sale_item", "membership", "invoice_line__invoice")
        .order_by("-created_at", "-id")[:limit]
    )


def _membership_line_description(membership, plan):
    if plan.is_fixed and membership.fecha_fin:
        return "Cuota {} ({} al {})".format(
            plan.nombre,
            membership.fecha_inicio.strftime("%d/%m/%Y"),
            membership.fecha_fin.strftime("%d/%m/%Y"),
        )
    return "Cuota {} (desde {})".format(
        plan.nombre,
        membership.fecha_inicio.strftime("%d/%m/%Y"),
    )


def register_checkout(
    client,
    plan=None,
    product_lines=None,
    nro_control=None,
    apply_late_fee=False,
    late_fee_usd=None,
    acting_user=None,
    payment_cut_day=None,
    payment_cut_motivo="",
):
    product_lines = product_lines or []
    if not plan and not product_lines:
        raise ValidationError("Debe incluir al menos una membresía o un producto en el cobro.")

    _validate_checkout_product_lines(product_lines, plan)

    tasa = ExchangeRate.get_latest()
    if not tasa:
        raise ValidationError("No hay una tasa de cambio registrada en el sistema.")

    with transaction.atomic():
        membership = None
        warnings = []
        was_reactivation = False
        late_fee_applied = False
        multa_usd = Decimal("0.00")
        multa_ves = Decimal("0.00")
        pending_lines = []

        if plan:
            hoy = timezone.localdate()
            validate_plan_purchase(client, plan, hoy)
            was_suspended = is_subscription_suspended(client, hoy)

            if plan.is_flexible and was_suspended:
                warnings.append("flexible_on_suspended_subscription")

            if plan.is_fixed:
                if payment_cut_day is None:
                    raise ValidationError("Debe indicar el día de corte para el plan mensual.")
                apply_cut_day_from_payment(
                    client, payment_cut_day, acting_user, motivo=payment_cut_motivo
                )
                membership = _create_fixed_membership(client, plan, hoy)
            else:
                membership = _create_flexible_membership(client, plan, hoy)

            membership_ves = plan.precio_usd * tasa.tasa_ves
            pending_lines.append(
                {
                    "line_kind": InvoiceLine.LineKind.MEMBERSHIP,
                    "description": _membership_line_description(membership, plan),
                    "quantity": 1,
                    "unit_price_usd": plan.precio_usd,
                    "amount_ves": membership_ves,
                    "sale_item": None,
                    "membership": membership,
                    "metadata": {},
                }
            )

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
                        pending_lines.append(
                            {
                                "line_kind": InvoiceLine.LineKind.LATE_FEE,
                                "description": "Multa por morosidad",
                                "quantity": 1,
                                "unit_price_usd": multa_usd,
                                "amount_ves": multa_ves,
                                "sale_item": None,
                                "membership": membership,
                                "metadata": {},
                            }
                        )

        for product_line in product_lines:
            product_line = _normalize_product_line(product_line)
            item_id = product_line["item_id"]
            qty = product_line["qty"]
            sale_item = SaleItem.objects.filter(pk=item_id, is_active=True).first()
            if not sale_item:
                raise ValidationError("Uno de los productos seleccionados no está disponible.")
            metadata = {}
            locker_payload = None
            service_payload = None
            line_membership = None

            if sale_item.is_plan_linked_service:
                if not membership:
                    raise ValidationError(
                        "Los servicios requieren seleccionar un plan en el mismo cobro."
                    )
                line_membership = membership

            if sale_item.requires_locker_assignment:
                if qty != 1:
                    raise ValidationError("Los servicios de casillero se cobran de uno en uno.")
                from apps.lockers.services import (
                    build_locker_checkout_metadata,
                    validate_locker_checkout,
                )

                start_date = membership.fecha_inicio
                end_date = membership.fecha_fin
                locker = validate_locker_checkout(
                    client,
                    sale_item,
                    product_line.get("locker_id"),
                    start_date,
                    end_date,
                )
                metadata = build_locker_checkout_metadata(locker, start_date, end_date)
                locker_payload = {
                    "locker_id": locker.pk,
                    "start_date": start_date,
                    "end_date": end_date,
                    "sale_item": sale_item,
                }
            elif sale_item.is_plan_linked_service:
                validate_service_period_available(client, sale_item)
                service_payload = {
                    "sale_item": sale_item,
                    "start_date": membership.fecha_inicio,
                    "end_date": membership.fecha_fin,
                }
            line_ves = sale_item.price_usd * tasa.tasa_ves * qty
            desc = sale_item.name
            if locker_payload:
                desc = "{} - Casillero {}".format(sale_item.name, metadata["locker_number"])
            if qty > 1:
                desc = "{} x{}".format(sale_item.name, qty)
            pending_lines.append(
                {
                    "line_kind": InvoiceLine.LineKind.PRODUCT,
                    "description": desc,
                    "quantity": qty,
                    "unit_price_usd": sale_item.price_usd,
                    "amount_ves": line_ves,
                    "sale_item": sale_item,
                    "membership": line_membership,
                    "metadata": metadata,
                    "locker_payload": locker_payload,
                    "service_payload": service_payload,
                }
            )

        monto_total = sum(line["amount_ves"] for line in pending_lines)

        invoice = Invoice(
            client=client,
            membership=membership,
            plan_snapshot=plan.nombre if plan else "",
            multa_usd=multa_usd,
            multa_ves=multa_ves,
            monto_total=monto_total,
            nro_control=nro_control or "PENDING",
        )
        invoice.set_client_snapshots(client)
        invoice.save()

        if not nro_control:
            invoice.nro_control = "F-{}-{:05d}".format(
                timezone.now().strftime("%Y%m%d"),
                invoice.pk,
            )
            invoice.save(update_fields=["nro_control"])

        for line_data in pending_lines:
            locker_payload = line_data.pop("locker_payload", None)
            service_payload = line_data.pop("service_payload", None)
            invoice_line = InvoiceLine.objects.create(invoice=invoice, **line_data)
            if service_payload:
                create_service_period(
                    client,
                    service_payload["sale_item"],
                    membership,
                    invoice_line=invoice_line,
                    start_date=service_payload["start_date"],
                    end_date=service_payload["end_date"],
                    user=acting_user,
                )
            if locker_payload:
                from apps.lockers.services import create_locker_rental

                create_locker_rental(
                    client,
                    locker_payload["sale_item"],
                    locker_payload["locker_id"],
                    locker_payload["start_date"],
                    locker_payload["end_date"],
                    invoice_line=invoice_line,
                    membership=membership,
                    user=acting_user,
                )

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


def register_membership_renewal(
    client,
    plan,
    nro_control=None,
    monto_ves=None,
    apply_late_fee=False,
    late_fee_usd=None,
    acting_user=None,
    payment_cut_day=None,
    payment_cut_motivo="",
):
    """DEPRECATED: usar register_checkout — conservado para llamadas legacy."""
    return register_checkout(
        client,
        plan=plan,
        product_lines=[],
        nro_control=nro_control,
        apply_late_fee=apply_late_fee,
        late_fee_usd=late_fee_usd,
        acting_user=acting_user,
        payment_cut_day=payment_cut_day,
        payment_cut_motivo=payment_cut_motivo,
    )


def _create_flexible_membership(client, plan, hoy):
    return Membership.objects.create(
        client=client,
        plan=plan,
        fecha_inicio=hoy,
    )


def _resolve_fixed_period(client, hoy, cut_day=None):
    if cut_day is None:
        cut_day = client.fecha_corte_dia or hoy.day

    latest_fixed = (
        client.memberships.filter(plan__billing_type=Plan.BillingType.FIXED)
        .order_by("-fecha_fin")
        .first()
    )

    if latest_fixed and latest_fixed.fecha_fin >= hoy:
        period_start = latest_fixed.fecha_fin + timedelta(days=1)
    else:
        period_start = billing_period_start(cut_day, hoy)

    assigns_cut = client.fecha_corte_dia is None
    return cut_day, period_start, assigns_cut


def _create_fixed_membership(client, plan, hoy):
    cut_day = client.fecha_corte_dia
    cut_day, period_start, _ = _resolve_fixed_period(client, hoy, cut_day=cut_day)

    fecha_inicio, fecha_fin = subscription_period_bounds(cut_day, period_start)

    return Membership.objects.create(
        client=client,
        plan=plan,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )


def update_late_fee_amount_usd(amount_raw):
    amount_str = (amount_raw or "").strip().replace(",", ".")
    if not amount_str:
        raise ValidationError("El monto de la multa no puede estar vacío.")
    try:
        amount = Decimal(amount_str)
    except Exception as exc:
        raise ValidationError("El monto de la multa no es un número válido.") from exc
    if amount < 0:
        raise ValidationError("El monto de la multa no puede ser negativo.")

    settings_obj = BillingSettings.get_settings()
    settings_obj.multa_monto_usd = amount
    settings_obj.save(update_fields=["multa_monto_usd", "updated_at"])
    return settings_obj


def update_report_recipient_email(email_raw):
    from .models import ReportEmailSettings

    email = (email_raw or "").strip()
    if email and "@" not in email:
        raise ValidationError("El correo del dueño no es válido.")

    settings_obj = ReportEmailSettings.get_settings()
    settings_obj.recipient_email = email
    settings_obj.save(update_fields=["recipient_email", "updated_at"])
    return settings_obj


@transaction.atomic
def delete_invoice(invoice):
    nro_control = invoice.nro_control
    invoice.delete()
    return nro_control


def _parse_ves_amount(amount_raw):
    amount_str = (amount_raw or "").strip()
    if not amount_str:
        raise ValidationError("El monto no puede estar vacío.")
    normalized = amount_str.replace("Bs", "").strip()
    if "," in normalized and "." in normalized:
        normalized = normalized.replace(".", "").replace(",", ".")
    else:
        normalized = normalized.replace(",", ".")
    try:
        amount = Decimal(normalized)
    except Exception as exc:
        raise ValidationError("El monto no es un número válido.") from exc
    if amount < 0:
        raise ValidationError("El monto no puede ser negativo.")
    return amount.quantize(Decimal("0.01"))


def parse_invoice_amount_edits_from_post(post_data, invoice):
    from .models import InvoiceLine

    edits = {}
    if invoice.has_detail_lines():
        for line in invoice.lines.all():
            key = "line_amount_{}".format(line.pk)
            if key not in post_data:
                continue
            edits[line.pk] = _parse_ves_amount(post_data.get(key))
        return edits

    if "legacy_monto_total" in post_data:
        edits["legacy_total"] = _parse_ves_amount(post_data.get("legacy_monto_total"))
    return edits


def build_amount_overrides_from_post(post_data, invoice):
    edits = parse_invoice_amount_edits_from_post(post_data, invoice)
    if invoice.has_detail_lines():
        return edits
    if "legacy_total" in edits:
        return {"legacy_total": edits["legacy_total"]}
    return {}


def invoice_amount_edits_differ_from_stored(invoice, edits):
    if not edits:
        return False

    if invoice.has_detail_lines():
        stored = {line.pk: line.amount_ves for line in invoice.lines.all()}
        for line_id, amount in edits.items():
            stored_amount = stored.get(int(line_id))
            if stored_amount is None:
                continue
            if amount != stored_amount:
                return True
        return False

    if "legacy_total" in edits:
        return edits["legacy_total"] != invoice.monto_total
    return False


def post_amount_edits_differ_from_stored(post_data, invoice):
    try:
        edits = parse_invoice_amount_edits_from_post(post_data, invoice)
    except ValidationError:
        return True
    return invoice_amount_edits_differ_from_stored(invoice, edits)


@transaction.atomic
def apply_invoice_amount_edits(invoice, edits):
    from .models import InvoiceLine

    if invoice.esta_impresa:
        raise ValidationError("No se puede editar una factura que ya ha sido impresa.")

    if not edits:
        return invoice

    if invoice.has_detail_lines():
        line_map = {line.pk: line for line in invoice.lines.select_for_update()}
        total = Decimal("0.00")
        multa_ves = Decimal("0.00")

        for line_id, amount in edits.items():
            line = line_map.get(int(line_id))
            if line is None:
                continue
            line.amount_ves = amount
            line.save(update_fields=["amount_ves"])

        for line in invoice.lines.all():
            total += line.amount_ves
            if line.line_kind == InvoiceLine.LineKind.LATE_FEE:
                multa_ves += line.amount_ves

        invoice.monto_total = total
        invoice.multa_ves = multa_ves
        if multa_ves > 0:
            tasa = ExchangeRate.get_latest()
            if tasa and tasa.tasa_ves:
                invoice.multa_usd = (multa_ves / tasa.tasa_ves).quantize(Decimal("0.01"))
        else:
            invoice.multa_usd = Decimal("0.00")
        invoice.save(update_fields=["monto_total", "multa_ves", "multa_usd"])
        return invoice

    if "legacy_total" in edits:
        invoice.monto_total = edits["legacy_total"]
        invoice.save(update_fields=["monto_total"])
    return invoice

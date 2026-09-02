"""
Servicios de negocio para Grupos Corporativos.

Flujo principal:
1. create_corporate_group() — crea el grupo, hard reset del suscriptor
2. add_member_to_group()    — agrega sub-afiliado, hard reset, warning si ya está en otro grupo
3. register_corporate_checkout() — paga el grupo: crea Membership para TODOS los miembros activos
4. remove_member_from_group()    — desvincula sub-afiliado
5. dissolve_corporate_group()    — suscriptor sale → grupo disuelto, miembros desvinculados
"""

from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from .cycle import (
    next_cut_on_or_after,
    subscription_period_bounds,
)
from .models import (
    CorporateGroup,
    CorporateGroupMember,
    Invoice,
    InvoiceLine,
    Membership,
    Plan,
    ExchangeRate,
    ClientBillingEvent,
    ClientServicePeriod,
)
from apps.clients.models import Client


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_active_fixed_memberships(client, today=None):
    """True si el cliente tiene alguna membresía fija o corporativa activa/futura."""
    if today is None:
        today = timezone.localdate()
    return client.memberships.filter(
        plan__billing_type__in=[Plan.BillingType.FIXED, Plan.BillingType.CORPORATE],
        fecha_fin__gte=today,
    ).exists()


def _get_active_corporate_group_for_client(client):
    """Retorna el CorporateGroup activo al que pertenece el cliente, si existe.

    El cliente puede ser suscriptor principal o sub-afiliado.
    """
    # ¿Es suscriptor?
    grp = CorporateGroup.objects.filter(
        subscriber=client,
        status__in=[CorporateGroup.Status.ACTIVE, CorporateGroup.Status.SUSPENDED],
    ).first()
    if grp:
        return grp
    # ¿Es sub-afiliado activo?
    membership_record = CorporateGroupMember.objects.filter(
        client=client,
        is_active=True,
    ).select_related("group").first()
    if membership_record:
        group = membership_record.group
        if group.status in [CorporateGroup.Status.ACTIVE, CorporateGroup.Status.SUSPENDED]:
            return group
    return None


def _cancel_client_fixed_memberships(client, today=None):
    """Cancela membresías fijas/corporativas activas o futuras del cliente.

    Retorna la lista de planes cancelados para mostrar en el warning.
    """
    if today is None:
        today = timezone.localdate()

    memberships_to_cancel = list(
        client.memberships.filter(
            plan__billing_type__in=[Plan.BillingType.FIXED, Plan.BillingType.CORPORATE],
            fecha_fin__gte=today,
        ).select_related("plan")
    )

    cancelled_info = []
    for mem in memberships_to_cancel:
        cancelled_info.append({
            "plan_nombre": mem.plan.nombre,
            "billing_type": mem.plan.billing_type,
            "fecha_fin": mem.fecha_fin.strftime("%d/%m/%Y"),
        })
        mem.delete()

    # Resetear campos del cliente
    update_fields = []
    if client.fixed_plan_id is not None:
        client.fixed_plan = None
        update_fields.append("fixed_plan")
    if client.fecha_corte_dia is not None:
        client.fecha_corte_dia = None
        update_fields.append("fecha_corte_dia")
    if update_fields:
        Client.objects.filter(pk=client.pk).update(
            fixed_plan=None, fecha_corte_dia=None
        )
        client.fixed_plan = None
        client.fecha_corte_dia = None

    ClientBillingEvent.objects.create(
        client=client,
        event_type=ClientBillingEvent.EventType.MEMBERSHIP_DELETED,
        payload={"cancelled_by": "corporate_group_join", "plans": cancelled_info},
        motivo="Vinculado a grupo corporativo — membresías previas canceladas automáticamente.",
    )

    return cancelled_info


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class CorporateGroupResult:
    group: CorporateGroup = None
    warnings: list = field(default_factory=list)


@transaction.atomic
def create_corporate_group(plan, subscriber, created_by=None):
    """Crea un nuevo CorporateGroup.

    - Valida que el plan sea de tipo CORPORATE.
    - Valida que el suscriptor no esté ya en otro grupo activo.
    - Hard reset de membresías fijas del suscriptor.
    - El grupo nace en estado SUSPENDED (no activo hasta primer pago).
    """
    if plan.billing_type != Plan.BillingType.CORPORATE:
        raise ValidationError("El plan seleccionado no es de tipo corporativo.")

    if not subscriber.is_member:
        raise ValidationError("Solo los afiliados pueden ser suscriptores de un grupo corporativo.")

    cut_day = subscriber.fecha_corte_dia or timezone.localdate().day

    # Check si ya está en otro grupo
    existing = _get_active_corporate_group_for_client(subscriber)
    warnings = []
    if existing:
        warnings.append({
            "type": "already_in_group",
            "client_nombre": subscriber.nombre,
            "group_id": existing.pk,
        })

    # Hard reset membresías fijas
    cancelled = _cancel_client_fixed_memberships(subscriber)
    if cancelled:
        warnings.append({
            "type": "memberships_cancelled",
            "client_nombre": subscriber.nombre,
            "cancelled": cancelled,
        })

    group = CorporateGroup.objects.create(
        plan=plan,
        subscriber=subscriber,
        fecha_corte_dia=cut_day,
        status=CorporateGroup.Status.SUSPENDED,
        created_by=created_by,
    )

    # El dueño del grupo queda amarrado al plan corporativo
    Client.objects.filter(pk=subscriber.pk).update(fixed_plan=plan, fecha_corte_dia=cut_day)
    subscriber.fixed_plan = plan
    subscriber.fecha_corte_dia = cut_day

    return CorporateGroupResult(group=group, warnings=warnings)


@transaction.atomic
def add_member_to_group(group, client, added_by=None):
    """Agrega un sub-afiliado al grupo corporativo.

    - Warning (no error) si el cliente ya está en otro grupo.
    - Error si el grupo está disuelto o lleno.
    - Hard reset de membresías fijas del cliente.
    - Retorna warnings para mostrar al usuario.
    """
    if group.status == CorporateGroup.Status.DISSOLVED:
        raise ValidationError("No se pueden agregar miembros a un grupo disuelto.")

    if not client.is_member:
        raise ValidationError("Solo los afiliados pueden pertenecer a un grupo corporativo.")

    if client.pk == group.subscriber_id:
        raise ValidationError("El suscriptor principal ya forma parte del grupo.")

    if group.is_at_capacity:
        raise ValidationError(
            "El grupo ha alcanzado su capacidad máxima de {} personas.".format(
                group.plan.max_members
            )
        )

    warnings = []

    # Check si ya está en otro grupo activo (warning, no error)
    existing_group = _get_active_corporate_group_for_client(client)
    if existing_group and existing_group.pk != group.pk:
        warnings.append({
            "type": "already_in_group",
            "client_nombre": client.nombre,
            "group_id": existing_group.pk,
        })

    # Check si ya es miembro activo de ESTE grupo
    if CorporateGroupMember.objects.filter(group=group, client=client, is_active=True).exists():
        raise ValidationError("{} ya es miembro activo de este grupo.".format(client.nombre))

    # Hard reset membresías fijas
    cancelled = _cancel_client_fixed_memberships(client)
    if cancelled:
        warnings.append({
            "type": "memberships_cancelled",
            "client_nombre": client.nombre,
            "cancelled": cancelled,
        })

    # Si estaba en otro grupo como miembro, desactivarlo allí
    if existing_group:
        CorporateGroupMember.objects.filter(
            client=client, is_active=True
        ).update(
            is_active=False,
            removed_at=timezone.now(),
            removed_by=added_by,
        )

    CorporateGroupMember.objects.create(
        group=group,
        client=client,
        added_by=added_by,
    )

    # Si el grupo está activo, generar membresía inmediatamente para este nuevo miembro
    if group.status == CorporateGroup.Status.ACTIVE:
        today = timezone.localdate()
        subscriber_mem = group.subscriber.memberships.filter(
            plan=group.plan,
            fecha_fin__gte=today,
        ).order_by("-fecha_fin").first()
        if subscriber_mem:
            _create_corporate_membership_for_client(
                client=client,
                group=group,
                fecha_inicio=today,
                fecha_fin=subscriber_mem.fecha_fin,
                acting_user=added_by
            )
            Client.objects.filter(pk=client.pk).update(fixed_plan=group.plan, fecha_corte_dia=group.fecha_corte_dia)
            client.fixed_plan = group.plan
            client.fecha_corte_dia = group.fecha_corte_dia

    return warnings


@transaction.atomic
def remove_member_from_group(group, client, removed_by=None):
    """Desvincula un sub-afiliado del grupo.

    - Cancela las membresías activas que el cliente tenga del plan del grupo.
    - Marca el CorporateGroupMember como is_active=False.
    - Si el cliente es el suscriptor → dissolve_corporate_group().
    - NO afecta al resto de los miembros del grupo.
    """
    if client.pk == group.subscriber_id:
        # El suscriptor sale → disolver el grupo
        return dissolve_corporate_group(group, dissolved_by=removed_by)

    member = CorporateGroupMember.objects.filter(
        group=group, client=client, is_active=True
    ).first()
    if not member:
        raise ValidationError("{} no es miembro activo de este grupo.".format(client.nombre))

    # Cancelar membresías activas del plan corporativo para este cliente
    today = timezone.localdate()
    client.memberships.filter(
        plan=group.plan,
        fecha_fin__gte=today,
    ).delete()

    member.is_active = False
    member.removed_at = timezone.now()
    member.removed_by = removed_by
    member.save(update_fields=["is_active", "removed_at", "removed_by"])

    # Hard reset of client profile
    Client.objects.filter(pk=client.pk).update(fixed_plan=None, fecha_corte_dia=None)
    client.fixed_plan = None
    client.fecha_corte_dia = None

    return []


@transaction.atomic
def dissolve_corporate_group(group, dissolved_by=None):
    """Disuelve el grupo: cancela membresías activas de todos los miembros
    del plan corporativo y marca el grupo como DISSOLVED.
    """
    if group.status == CorporateGroup.Status.DISSOLVED:
        raise ValidationError("El grupo ya está disuelto.")

    today = timezone.localdate()

    # Cancelar membresías activas del plan corporativo para todos los miembros
    all_client_ids = list(
        group.members.filter(is_active=True).values_list("client_id", flat=True)
    ) + [group.subscriber_id]

    from apps.billing.models import Membership as M
    M.objects.filter(
        client_id__in=all_client_ids,
        plan=group.plan,
        fecha_fin__gte=today,
    ).delete()

    # Desactivar todos los miembros
    group.members.filter(is_active=True).update(
        is_active=False,
        removed_at=timezone.now(),
        removed_by=dissolved_by,
    )

    # Hard reset of client profiles for all affected members
    from apps.clients.models import Client
    Client.objects.filter(id__in=all_client_ids).update(fixed_plan=None, fecha_corte_dia=None)

    group.status = CorporateGroup.Status.DISSOLVED
    group.dissolved_by = dissolved_by
    group.dissolved_at = timezone.now()
    group.save(update_fields=["status", "dissolved_by", "dissolved_at", "updated_at"])

    return group


def get_group_for_client(client):
    """Retorna el CorporateGroup activo/suspendido al que pertenece el cliente.

    Returns None si no está en ningún grupo.
    """
    return _get_active_corporate_group_for_client(client)


def collect_group_clients(group):
    """Suscriptor principal + sub-afiliados activos del grupo."""
    member_ids = list(
        group.active_members.values_list("client_id", flat=True)
    )
    client_ids = [group.subscriber_id] + member_ids
    return list(Client.objects.filter(pk__in=client_ids).order_by("nombre", "pk"))


def find_memberships_for_corporate_invoice(invoice):
    """Membresías del periodo corporativo ligado a la factura (pagador + hermanos).

    Recupera por plan + fechas exactas entre suscriptor y miembros del grupo
    (activos o no), para no dejar huérfanos si alguien salió después del cobro.
    """
    if not invoice.corporate_group_id or not invoice.membership_id:
        return []

    group = invoice.corporate_group
    period = invoice.membership
    if group is None or period is None:
        return []

    client_ids = set(
        CorporateGroupMember.objects.filter(group_id=group.pk).values_list(
            "client_id", flat=True
        )
    )
    client_ids.add(group.subscriber_id)

    return list(
        Membership.objects.filter(
            client_id__in=client_ids,
            plan_id=period.plan_id,
            fecha_inicio=period.fecha_inicio,
            fecha_fin=period.fecha_fin,
        )
        .select_related("client", "plan")
        .order_by("client_id", "id")
    )


def is_corporate_group_member(client, group):
    """True si el cliente es suscriptor o sub-afiliado activo del grupo."""
    if group is None or group.is_dissolved:
        return False
    if group.subscriber_id == client.pk:
        return True
    return group.active_members.filter(client_id=client.pk).exists()


def get_corporate_checkout_context(client):
    """Contexto de cobro corporativo para un afiliado."""
    corp_group = get_group_for_client(client)
    if not corp_group or corp_group.is_dissolved:
        return {
            "corp_group": None,
            "plan": None,
            "can_pay_corporate": False,
        }
    return {
        "corp_group": corp_group,
        "plan": corp_group.plan,
        "can_pay_corporate": is_corporate_group_member(client, corp_group),
    }


def apply_corporate_group_payment(
    group,
    payer,
    payment_cut_day,
    acting_user=None,
    payment_cut_motivo="",
):
    """Crea membresías corporativas para todos los miembros activos del grupo.

    Retorna dict con payer_membership, plan, fechas y conteo para facturación.
    """
    from .services import apply_cut_day_from_payment

    if not isinstance(payment_cut_day, int) or payment_cut_day < 1 or payment_cut_day > 31:
        raise ValidationError("El día de corte debe ser un número entre 1 y 31.")

    if group.status == CorporateGroup.Status.DISSOLVED:
        raise ValidationError("No se puede cobrar un grupo disuelto.")

    if not is_corporate_group_member(payer, group):
        raise ValidationError("Solo un miembro activo del grupo puede pagar este plan corporativo.")

    hoy = timezone.localdate()
    latest = (
        group.subscriber.memberships.filter(plan=group.plan)
        .order_by("-fecha_fin")
        .first()
    )
    if latest and latest.fecha_fin >= hoy:
        period_start = next_cut_on_or_after(latest.fecha_fin, payment_cut_day)
    else:
        period_start = hoy
    fecha_inicio, fecha_fin = subscription_period_bounds(payment_cut_day, period_start)

    group.fecha_corte_dia = payment_cut_day
    group.save(update_fields=["fecha_corte_dia", "updated_at"])

    apply_cut_day_from_payment(
        group.subscriber, payment_cut_day, acting_user, motivo=payment_cut_motivo
    )

    active_member_ids = list(
        group.active_members.values_list("client_id", flat=True)
    )
    all_client_ids = [group.subscriber_id] + active_member_ids
    all_clients = list(Client.objects.filter(pk__in=all_client_ids))

    plan = group.plan
    payer_membership = None
    for member_client in all_clients:
        membership = Membership(
            client=member_client,
            plan=plan,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        )
        membership.full_clean()
        membership.save()
        Client.objects.filter(pk=member_client.pk).update(
            fixed_plan=plan,
            fecha_corte_dia=payment_cut_day,
        )
        if member_client.pk == payer.pk:
            payer_membership = membership

    if payer_membership is None:
        payer_membership = Membership.objects.filter(
            client=payer,
            plan=plan,
            fecha_inicio=fecha_inicio,
            fecha_fin=fecha_fin,
        ).first()

    if group.status == CorporateGroup.Status.SUSPENDED:
        group.status = CorporateGroup.Status.ACTIVE
        group.save(update_fields=["status", "updated_at"])

    return {
        "group": group,
        "plan": plan,
        "payer_membership": payer_membership,
        "fecha_inicio": fecha_inicio,
        "fecha_fin": fecha_fin,
        "member_count": len(all_clients),
    }


@transaction.atomic
def grant_corporate_admin_access(group, valid_until, user):
    """Asigna acceso administrativo corporativo sin cobro a todo el grupo.

    - Soft-cierra membresías activas/encoladas (no borra vencidas ni filas).
    - No anula facturas corporativas (cascada pendiente); cancela periodos de servicio abiertos.
    - Crea Membership CORPORATE con las mismas fechas para todos.
    - Sincroniza fixed_plan y fecha_corte_dia en clientes y grupo.
    """
    from datetime import date as date_cls

    from .services import log_billing_event, soft_close_membership

    if group.status == CorporateGroup.Status.DISSOLVED:
        raise ValidationError("No se puede asignar acceso administrativo a un grupo disuelto.")

    if not group.plan or group.plan.billing_type != Plan.BillingType.CORPORATE:
        raise ValidationError("El grupo no tiene un plan corporativo válido.")

    if not isinstance(valid_until, date_cls):
        raise ValidationError("La fecha de vigencia no es válida.")

    today = timezone.localdate()
    clients = collect_group_clients(group)
    if not clients:
        raise ValidationError("El grupo no tiene miembros para asignar acceso.")

    cut_day = max(1, min(valid_until.day, 28))
    fecha_inicio = valid_until if valid_until < today else today
    client_pks = [client.pk for client in clients]

    for client in clients:
        soft_closed_ids = []
        open_memberships = list(
            client.memberships.filter(fecha_fin__gte=today)
            .select_related("plan")
            .order_by("fecha_inicio")
        )
        for membership in open_memberships:
            ClientServicePeriod.objects.filter(membership=membership).exclude(
                status=ClientServicePeriod.Status.CANCELLED
            ).update(status=ClientServicePeriod.Status.CANCELLED)
            soft_close_membership(
                membership,
                user,
                motivo="Cierre por acceso administrativo corporativo (grupo #{})".format(
                    group.pk
                ),
            )
            soft_closed_ids.append(membership.pk)

        ClientServicePeriod.objects.filter(client=client).filter(
            status__in=(
                ClientServicePeriod.Status.ACTIVE,
                ClientServicePeriod.Status.QUEUED,
            )
        ).update(status=ClientServicePeriod.Status.CANCELLED)

        new_membership = Membership(
            client=client,
            plan=group.plan,
            fecha_inicio=fecha_inicio,
            fecha_fin=valid_until,
        )
        new_membership.full_clean()
        new_membership.save()

        log_billing_event(
            client,
            ClientBillingEvent.EventType.ADMIN_ACCESS_GRANTED,
            payload={
                "corporate": True,
                "group_id": group.pk,
                "plan_id": group.plan.pk,
                "plan_name": group.plan.nombre,
                "fecha_inicio": fecha_inicio.isoformat(),
                "fecha_fin": valid_until.isoformat(),
                "membership_id": new_membership.pk,
                "soft_closed_membership_ids": soft_closed_ids,
                "fecha_corte_dia": cut_day,
                "member_count": len(clients),
            },
            motivo="Acceso administrativo corporativo sin cobro (grupo #{}) por {}".format(
                group.pk,
                user.username if user else "sistema",
            ),
            user=user,
        )

    Client.objects.filter(pk__in=client_pks).update(
        fixed_plan=group.plan,
        fecha_corte_dia=cut_day,
    )

    group.fecha_corte_dia = cut_day
    update_fields = ["fecha_corte_dia", "updated_at"]
    if group.status == CorporateGroup.Status.SUSPENDED:
        group.status = CorporateGroup.Status.ACTIVE
        update_fields.append("status")
    group.save(update_fields=update_fields)

    return clients


def get_hard_reset_preview(client):
    """Preview sin ejecutar: qué membresías fijas perdería al unirse a un grupo."""
    today = timezone.localdate()
    memberships = list(
        client.memberships.filter(
            plan__billing_type__in=[Plan.BillingType.FIXED, Plan.BillingType.CORPORATE],
            fecha_fin__gte=today,
        ).select_related("plan")
    )
    return [
        {
            "plan_nombre": m.plan.nombre,
            "billing_type": m.plan.billing_type,
            "fecha_fin": m.fecha_fin.strftime("%d/%m/%Y"),
        }
        for m in memberships
    ]


def _create_corporate_membership_for_client(client, group, fecha_inicio, fecha_fin, acting_user=None):
    """Crea una Membership individual para un cliente dentro del grupo corporativo."""
    membership = Membership(
        client=client,
        plan=group.plan,
        fecha_inicio=fecha_inicio,
        fecha_fin=fecha_fin,
    )
    membership.full_clean()
    membership.save()
    return membership


@transaction.atomic
def register_corporate_checkout(
    group,
    payer,
    payment_cut_day,
    payment_method,
    payment_splits=None,
    acting_user=None,
    payment_cut_motivo="",
):
    """Registra el pago del plan corporativo.

    - Crea una Membership para el suscriptor y todos los sub-afiliados activos.
    - Emite una sola Invoice a nombre del pagador (payer).
    - Actualiza la fecha de corte del grupo.
    - Activa el grupo si estaba suspendido.

    ``payer`` puede ser cualquier miembro del grupo (suscriptor o sub-afiliado).
    """
    from .services import validate_payment_for_total

    tasa = ExchangeRate.get_latest()
    if not tasa:
        raise ValidationError("No hay una tasa de cambio registrada en el sistema.")

    payment_result = apply_corporate_group_payment(
        group,
        payer,
        payment_cut_day,
        acting_user=acting_user,
        payment_cut_motivo=payment_cut_motivo,
    )
    plan = payment_result["plan"]
    payer_membership = payment_result["payer_membership"]
    fecha_inicio = payment_result["fecha_inicio"]
    fecha_fin = payment_result["fecha_fin"]
    member_count = payment_result["member_count"]

    monto_total_ves = plan.precio_usd * tasa.tasa_ves
    payment_splits = payment_splits or []
    validate_payment_for_total(payment_method, payment_splits, monto_total_ves)

    invoice = Invoice(
        client=payer,
        membership=payer_membership,
        corporate_group=group,
        plan_snapshot="{} (Corporativo, {} personas)".format(
            plan.nombre, member_count
        ),
        monto_total=monto_total_ves,
        payment_method=payment_method,
        payment_splits=payment_splits,
        nro_control="PENDING",
    )
    invoice.set_client_snapshots(payer)
    invoice.save()

    invoice.nro_control = "F-{}-{:05d}".format(
        timezone.now().strftime("%Y%m%d"),
        invoice.pk,
    )
    invoice.save(update_fields=["nro_control"])

    desc = "Cuota Corporativa {} — {} persona{} ({} al {})".format(
        plan.nombre,
        member_count,
        "s" if member_count != 1 else "",
        fecha_inicio.strftime("%d/%m/%Y"),
        fecha_fin.strftime("%d/%m/%Y"),
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        line_kind=InvoiceLine.LineKind.MEMBERSHIP,
        description=desc,
        quantity=1,
        unit_price_usd=plan.precio_usd,
        amount_ves=monto_total_ves,
        membership=payer_membership,
    )

    return invoice


def get_corporate_group_billing_context(group):
    """Contexto de facturación análogo a get_client_billing_context pero para grupos."""
    from .cycle import next_cut_on_or_after

    today = timezone.localdate()

    # Membresía que cubre hoy (puede ser solo el periodo actual, sin prepago).
    active_membership = group.subscriber.memberships.filter(
        plan=group.plan,
        fecha_inicio__lte=today,
        fecha_fin__gte=today,
    ).order_by("-fecha_fin").first()

    # Cobertura total: el prepago puede dejar membresías futuras más allá de hoy.
    last_membership = group.subscriber.memberships.filter(
        plan=group.plan,
    ).order_by("-fecha_fin").first()

    if last_membership and last_membership.fecha_fin >= today:
        covered_until = last_membership.fecha_fin
        next_cut = next_cut_on_or_after(covered_until, group.fecha_corte_dia)
        next_cut_display = next_cut.strftime("%d/%m/%Y")
        covered_until_display = covered_until.strftime("%d/%m/%Y")
        is_active = True
    elif last_membership is None:
        next_cut = next_cut_on_or_after(today, group.fecha_corte_dia)
        next_cut_display = "Requiere cobro inicial"
        covered_until_display = None
        is_active = False
    else:
        next_cut = next_cut_on_or_after(today, group.fecha_corte_dia)
        next_cut_display = next_cut.strftime("%d/%m/%Y")
        covered_until_display = None
        is_active = False

    return {
        "group": group,
        "active_membership": active_membership,
        "last_membership": last_membership,
        "fecha_corte_dia": group.fecha_corte_dia,
        "next_cut": next_cut,
        "next_cut_display": next_cut_display,
        "covered_until_display": covered_until_display,
        "is_active": is_active,
        "total_members": group.total_active_count,
        "plan": group.plan,
        "is_initial_charge": last_membership is None,
    }

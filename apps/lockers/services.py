from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.billing.models import SaleItem

from .models import Locker, LockerRental


def _periods_overlap(start_a, end_a, start_b, end_b):
    return start_a <= end_b and start_b <= end_a


def sync_locker_rental_statuses():
    today = timezone.localdate()
    LockerRental.objects.filter(
        status=LockerRental.Status.QUEUED,
        start_date__lte=today,
        end_date__gte=today,
    ).update(status=LockerRental.Status.ACTIVE)

    expired = LockerRental.objects.select_related("locker").filter(
        status=LockerRental.Status.ACTIVE,
        end_date__lt=today,
    )
    affected_lockers = []
    for rental in expired:
        rental.status = LockerRental.Status.EXPIRED
        rental.save(update_fields=["status", "updated_at"])
        affected_lockers.append(rental.locker)

    for locker in affected_lockers:
        if not _has_active_rental(locker):
            locker.status = Locker.Status.AVAILABLE
            locker.save(update_fields=["status", "updated_at"])


def expire_overdue_rentals():
    sync_locker_rental_statuses()


def _has_active_rental(locker):
    today = timezone.localdate()
    return locker.rentals.filter(
        status=LockerRental.Status.ACTIVE,
        end_date__gte=today,
    ).exists()


def get_available_lockers():
    sync_locker_rental_statuses()
    return Locker.objects.filter(status=Locker.Status.AVAILABLE).order_by("number", "id")


def get_lockers_for_checkout(client):
    sync_locker_rental_statuses()
    locker_ids = set(get_available_lockers().values_list("pk", flat=True))
    today = timezone.localdate()
    client_rental = (
        LockerRental.objects.select_related("locker")
        .filter(
            client=client,
            status__in=[LockerRental.Status.ACTIVE, LockerRental.Status.QUEUED],
        )
        .filter(
            Q(status=LockerRental.Status.ACTIVE, end_date__gte=today)
            | Q(status=LockerRental.Status.QUEUED, start_date__gt=today)
        )
        .order_by("-end_date", "-id")
        .first()
    )
    if client_rental and client_rental.locker.status != Locker.Status.INACTIVE:
        locker_ids.add(client_rental.locker_id)
    return Locker.objects.filter(pk__in=locker_ids).order_by("number", "id")


def get_current_rental_for_locker(locker):
    today = timezone.localdate()
    return (
        LockerRental.objects.select_related("client", "locker", "sale_item")
        .filter(locker=locker, status=LockerRental.Status.ACTIVE, end_date__gte=today)
        .order_by("end_date", "id")
        .first()
    )


def get_active_rental_for_client(client):
    sync_locker_rental_statuses()
    today = timezone.localdate()
    return (
        LockerRental.objects.select_related("locker", "sale_item", "invoice_line__invoice")
        .filter(client=client, status=LockerRental.Status.ACTIVE, end_date__gte=today)
        .order_by("end_date", "id")
        .first()
    )


def get_display_locker_rentals_for_client(client):
    sync_locker_rental_statuses()
    today = timezone.localdate()
    return (
        LockerRental.objects.select_related("locker", "sale_item", "invoice_line__invoice")
        .filter(client=client)
        .filter(
            Q(status=LockerRental.Status.ACTIVE, end_date__gte=today)
            | Q(status=LockerRental.Status.QUEUED, start_date__gt=today)
        )
        .order_by("start_date", "id")
    )


def get_recent_rentals_for_client(client, limit=5):
    return (
        LockerRental.objects.select_related("locker", "sale_item", "invoice_line__invoice")
        .filter(client=client)
        .order_by("-created_at", "-id")[:limit]
    )


def build_locker_checkout_metadata(locker, start_date, end_date):
    return {
        "locker_id": locker.pk,
        "locker_number": locker.number,
        "rental_start": start_date.isoformat(),
        "rental_end": end_date.isoformat(),
    }


def _resolve_rental_status(start_date):
    today = timezone.localdate()
    if start_date > today:
        return LockerRental.Status.QUEUED
    return LockerRental.Status.ACTIVE


def validate_locker_checkout(client, sale_item, locker_id, start_date, end_date):
    if not locker_id:
        raise ValidationError("Debe seleccionar un casillero disponible.")
    if start_date > end_date:
        raise ValidationError("La fecha de inicio del casillero debe ser anterior o igual al vencimiento.")

    sync_locker_rental_statuses()
    locker = Locker.objects.filter(pk=locker_id).first()
    if not locker:
        raise ValidationError("El casillero seleccionado no existe.")
    if locker.status == Locker.Status.INACTIVE:
        raise ValidationError("El casillero seleccionado no está disponible.")

    locker_item = SaleItem.get_locker_rental_item()
    if not locker_item or sale_item.pk != locker_item.pk:
        raise ValidationError("El ítem seleccionado no es la tarifa de casillero del sistema.")

    client_rental = get_active_rental_for_client(client)
    is_consecutive_renewal = (
        client_rental is not None
        and client_rental.locker_id == locker.pk
        and start_date == client_rental.end_date + timedelta(days=1)
    )

    if locker.status != Locker.Status.AVAILABLE and not is_consecutive_renewal:
        raise ValidationError("El casillero seleccionado no está disponible.")
    if client_rental and not is_consecutive_renewal:
        raise ValidationError("Este afiliado ya tiene un casillero activo.")

    overlapping = LockerRental.objects.filter(
        Q(client=client) | Q(locker=locker),
        status__in=[LockerRental.Status.ACTIVE, LockerRental.Status.QUEUED],
    )
    for rental in overlapping:
        if is_consecutive_renewal and rental.pk == client_rental.pk:
            continue
        if _periods_overlap(rental.start_date, rental.end_date, start_date, end_date):
            raise ValidationError(
                "Ya existe un alquiler de casillero que coincide con el periodo del cobro."
            )

    if _has_active_rental(locker):
        current = get_current_rental_for_locker(locker)
        if not current or current.client_id != client.pk or not is_consecutive_renewal:
            raise ValidationError("El casillero seleccionado ya está ocupado.")

    return locker


@transaction.atomic
def create_locker_rental(
    client,
    sale_item,
    locker_id,
    start_date,
    end_date,
    invoice_line=None,
    membership=None,
    user=None,
):
    locker = validate_locker_checkout(client, sale_item, locker_id, start_date, end_date)
    status = _resolve_rental_status(start_date)
    rental = LockerRental.objects.create(
        client=client,
        locker=locker,
        sale_item=sale_item,
        invoice_line=invoice_line,
        membership=membership,
        start_date=start_date,
        end_date=end_date,
        status=status,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
    if status == LockerRental.Status.ACTIVE or locker.status != Locker.Status.OCCUPIED:
        locker.status = Locker.Status.OCCUPIED
        locker.save(update_fields=["status", "updated_at"])
    return rental


@transaction.atomic
def release_locker(locker, user=None):
    rental = get_current_rental_for_locker(locker)
    if not rental:
        raise ValidationError("Este casillero no tiene un alquiler activo.")

    rental.status = LockerRental.Status.RELEASED
    rental.released_at = timezone.now()
    rental.released_by = user if getattr(user, "is_authenticated", False) else None
    rental.save(update_fields=["status", "released_at", "released_by", "updated_at"])

    locker.status = Locker.Status.AVAILABLE
    locker.save(update_fields=["status", "updated_at"])
    return rental


@transaction.atomic
def cancel_locker_rentals_for_invoice_line(invoice_line, user=None):
    """Cancela alquileres ligados a una línea al anular la factura."""
    rentals = list(
        LockerRental.objects.select_related("locker").filter(invoice_line=invoice_line)
    )
    cancelled = []
    for rental in rentals:
        if rental.status in (
            LockerRental.Status.CANCELLED,
            LockerRental.Status.RELEASED,
        ):
            continue
        was_active = rental.status == LockerRental.Status.ACTIVE
        rental.status = LockerRental.Status.CANCELLED
        rental.released_at = timezone.now()
        rental.released_by = user if getattr(user, "is_authenticated", False) else None
        rental.save(update_fields=["status", "released_at", "released_by", "updated_at"])
        if was_active:
            locker = rental.locker
            still_active = LockerRental.objects.filter(
                locker=locker,
                status=LockerRental.Status.ACTIVE,
            ).exclude(pk=rental.pk).exists()
            if not still_active:
                locker.status = Locker.Status.AVAILABLE
                locker.save(update_fields=["status", "updated_at"])
        cancelled.append(rental)
    return cancelled

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.billing.models import SaleItem

from .models import Locker, LockerRental


def expire_overdue_rentals():
    today = timezone.localdate()
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


def _has_active_rental(locker):
    today = timezone.localdate()
    return locker.rentals.filter(
        status=LockerRental.Status.ACTIVE,
        end_date__gte=today,
    ).exists()


def get_available_lockers():
    expire_overdue_rentals()
    return Locker.objects.filter(status=Locker.Status.AVAILABLE).order_by("number", "id")


def get_current_rental_for_locker(locker):
    today = timezone.localdate()
    return (
        LockerRental.objects.select_related("client", "locker", "sale_item")
        .filter(locker=locker, status=LockerRental.Status.ACTIVE, end_date__gte=today)
        .order_by("end_date", "id")
        .first()
    )


def get_active_rental_for_client(client):
    expire_overdue_rentals()
    today = timezone.localdate()
    return (
        LockerRental.objects.select_related("locker", "sale_item", "invoice_line__invoice")
        .filter(client=client, status=LockerRental.Status.ACTIVE, end_date__gte=today)
        .order_by("end_date", "id")
        .first()
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


def validate_locker_checkout(client, sale_item, locker_id, start_date, end_date):
    if not locker_id:
        raise ValidationError("Debe seleccionar un casillero disponible.")
    if start_date > end_date:
        raise ValidationError("La fecha de inicio del casillero debe ser anterior o igual al vencimiento.")

    expire_overdue_rentals()
    locker = Locker.objects.filter(pk=locker_id).first()
    if not locker:
        raise ValidationError("El casillero seleccionado no existe.")
    if locker.status != Locker.Status.AVAILABLE:
        raise ValidationError("El casillero seleccionado no está disponible.")
    if _has_active_rental(locker):
        raise ValidationError("El casillero seleccionado ya está ocupado.")
    if get_active_rental_for_client(client):
        raise ValidationError("Este afiliado ya tiene un casillero activo.")
    locker_item = SaleItem.get_locker_rental_item()
    if not locker_item or sale_item.pk != locker_item.pk:
        raise ValidationError("El ítem seleccionado no es la tarifa de casillero del sistema.")
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
    rental = LockerRental.objects.create(
        client=client,
        locker=locker,
        sale_item=sale_item,
        invoice_line=invoice_line,
        membership=membership,
        start_date=start_date,
        end_date=end_date,
        created_by=user if getattr(user, "is_authenticated", False) else None,
    )
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

from decimal import Decimal

from django.db import transaction
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.clients.models import Client, PersonCategory
from apps.billing.models import ExchangeRate, Invoice, InvoiceLine
from apps.billing.services import validate_payment_for_total

from .models import ClassRegistration, ClassSession


def _validate_session_editable(session):
    if session.status == ClassSession.Status.CANCELLED:
        raise ValidationError("La sesión está cancelada.")


def get_trainer_clients():
    return Client.objects.filter(person_category=PersonCategory.TRAINER).order_by("nombre")


def get_session_roster(session):
    return (
        session.registrations.select_related("client", "invoice_line__invoice")
        .exclude(status=ClassRegistration.Status.CANCELLED)
        .order_by("client__nombre", "id")
    )


def get_client_class_registrations(client, limit=10):
    return (
        ClassRegistration.objects.filter(client=client)
        .exclude(status=ClassRegistration.Status.CANCELLED)
        .select_related("session")
        .order_by("-session__session_date", "-session__start_time", "-id")[:limit]
    )


@transaction.atomic
def create_session(data, user=None):
    payload = dict(data)
    if "status" not in payload:
        payload["status"] = ClassSession.Status.SCHEDULED
    session = ClassSession(**payload)
    session.created_by = user
    session.full_clean()
    session.save()
    return session


@transaction.atomic
def update_session(session, data):
    for field, value in data.items():
        setattr(session, field, value)
    session.full_clean()
    session.save()
    return session


@transaction.atomic
def cancel_session(session):
    if session.status == ClassSession.Status.CANCELLED:
        return session
    session.status = ClassSession.Status.CANCELLED
    session.save(update_fields=["status", "updated_at"])
    session.registrations.filter(
        status=ClassRegistration.Status.PENDING_PAYMENT
    ).update(status=ClassRegistration.Status.CANCELLED, updated_at=timezone.now())
    return session


@transaction.atomic
def set_attendance_reported(session, count, mark_completed=False):
    _validate_session_editable(session)
    if count is None or count < 0:
        raise ValidationError("La asistencia reportada debe ser un número mayor o igual a cero.")
    session.attendance_reported = count
    update_fields = ["attendance_reported", "updated_at"]
    if mark_completed:
        session.status = ClassSession.Status.COMPLETED
        update_fields.append("status")
    session.save(update_fields=update_fields)
    return session


def _validate_member_client(client):
    if not client.is_member:
        raise ValidationError("Solo se pueden inscribir afiliados (código M-).")
    if client.is_guest:
        raise ValidationError("Los invitados no pueden inscribirse en clases de pago.")


@transaction.atomic
def add_registration(session, client, user=None):
    _validate_session_editable(session)
    if not session.is_paid:
        raise ValidationError("Las clases gratuitas no admiten inscripciones individuales.")
    _validate_member_client(client)
    if session.is_full:
        raise ValidationError("La sesión ya alcanzó el cupo máximo.")

    existing = ClassRegistration.objects.filter(
        session=session,
        client=client,
        status__in=(
            ClassRegistration.Status.PENDING_PAYMENT,
            ClassRegistration.Status.CONFIRMED,
        ),
    ).first()
    if existing:
        raise ValidationError("El afiliado ya está inscrito en esta sesión.")

    registration = ClassRegistration.objects.create(
        session=session,
        client=client,
        status=ClassRegistration.Status.PENDING_PAYMENT,
        created_by=user,
    )
    return registration


@transaction.atomic
def cancel_registration(registration, user=None):
    if registration.status == ClassRegistration.Status.CANCELLED:
        return registration
    if registration.status == ClassRegistration.Status.CONFIRMED:
        raise ValidationError("No se puede quitar una inscripción ya pagada desde aquí.")
    registration.status = ClassRegistration.Status.CANCELLED
    registration.save(update_fields=["status", "updated_at"])
    return registration


def build_class_line_description(session):
    time_label = session.start_time.strftime("%H:%M")
    if session.end_time:
        time_label = "{}–{}".format(
            session.start_time.strftime("%H:%M"),
            session.end_time.strftime("%H:%M"),
        )
    return "{} — {} {}".format(
        session.title,
        session.session_date.strftime("%d/%m/%Y"),
        time_label,
    )


@transaction.atomic
def register_class_checkout(registration, acting_user, payment_method, payment_splits=None):
    payment_splits = payment_splits or []
    session = registration.session
    client = registration.client

    if registration.status != ClassRegistration.Status.PENDING_PAYMENT:
        raise ValidationError("Esta inscripción ya no está pendiente de cobro.")
    _validate_session_editable(session)
    if not session.is_paid:
        raise ValidationError("Esta sesión no requiere cobro.")

    tasa = ExchangeRate.get_latest()
    if not tasa:
        raise ValidationError("No hay una tasa de cambio registrada en el sistema.")

    amount_ves = (session.price_usd * tasa.tasa_ves).quantize(Decimal("0.01"))
    validate_payment_for_total(payment_method, payment_splits, amount_ves)

    invoice = Invoice(
        client=client,
        membership=None,
        plan_snapshot="",
        monto_total=amount_ves,
        payment_method=payment_method,
        payment_splits=payment_splits,
        nro_control="PENDING",
    )
    invoice.set_client_snapshots(client)
    invoice.save()
    invoice.nro_control = "F-{}-{:05d}".format(
        timezone.now().strftime("%Y%m%d"),
        invoice.pk,
    )
    invoice.save(update_fields=["nro_control"])

    invoice_line = InvoiceLine.objects.create(
        invoice=invoice,
        line_kind=InvoiceLine.LineKind.CLASS,
        description=build_class_line_description(session),
        quantity=1,
        unit_price_usd=session.price_usd,
        amount_ves=amount_ves,
        class_registration=registration,
    )

    registration.status = ClassRegistration.Status.CONFIRMED
    registration.invoice_line = invoice_line
    registration.save(update_fields=["status", "invoice_line", "updated_at"])

    return invoice
